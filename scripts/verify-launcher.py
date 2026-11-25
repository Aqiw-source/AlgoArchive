"""Verify the native launcher's PE metadata, icon, imports, and argument flow."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time


FORBIDDEN_PREFIXES = ("libgcc_s_", "libstdc++-", "libwinpthread-")


def unpack_u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def unpack_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


class PEImage:
    def __init__(self, path: Path):
        self.data = path.read_bytes()
        if len(self.data) < 0x40 or self.data[:2] != b"MZ":
            raise ValueError("not an MZ executable")
        pe_offset = unpack_u32(self.data, 0x3C)
        if self.data[pe_offset : pe_offset + 4] != b"PE\0\0":
            raise ValueError("missing PE signature")
        coff = pe_offset + 4
        section_count = unpack_u16(self.data, coff + 2)
        optional_size = unpack_u16(self.data, coff + 16)
        optional = coff + 20
        magic = unpack_u16(self.data, optional)
        if magic == 0x20B:
            directories = optional + 112
        elif magic == 0x10B:
            directories = optional + 96
        else:
            raise ValueError(f"unsupported PE optional header: 0x{magic:x}")
        section_offset = optional + optional_size
        self.sections = []
        for index in range(section_count):
            offset = section_offset + index * 40
            self.sections.append((
                unpack_u32(self.data, offset + 12),
                max(unpack_u32(self.data, offset + 8), unpack_u32(self.data, offset + 16)),
                unpack_u32(self.data, offset + 20),
            ))
        self.directories = directories

    def directory(self, index: int) -> tuple[int, int]:
        offset = self.directories + index * 8
        return unpack_u32(self.data, offset), unpack_u32(self.data, offset + 4)

    def rva_to_offset(self, rva: int) -> int:
        for virtual_address, span, raw_offset in self.sections:
            if virtual_address <= rva < virtual_address + span:
                offset = raw_offset + rva - virtual_address
                if offset >= len(self.data):
                    break
                return offset
        raise ValueError(f"RVA is outside file sections: 0x{rva:x}")

    def imported_dlls(self) -> list[str]:
        import_rva, _ = self.directory(1)
        if import_rva == 0:
            raise ValueError("PE has no import directory")
        offset = self.rva_to_offset(import_rva)
        result = []
        while True:
            name_rva = unpack_u32(self.data, offset + 12)
            if name_rva == 0:
                break
            name_offset = self.rva_to_offset(name_rva)
            end = self.data.index(b"\0", name_offset)
            result.append(self.data[name_offset:end].decode("ascii").casefold())
            offset += 20
        return result

    def resources(self) -> dict[tuple[int | str, int | str, int | str], bytes]:
        resource_rva, resource_size = self.directory(2)
        if resource_rva == 0 or resource_size == 0:
            raise ValueError("PE has no resource directory")
        base = self.rva_to_offset(resource_rva)
        results = {}

        def walk(relative: int, path: tuple[int | str, ...], depth: int) -> None:
            if depth > 3 or relative >= resource_size:
                raise ValueError("invalid PE resource tree")
            directory = base + relative
            named = unpack_u16(self.data, directory + 12)
            ids = unpack_u16(self.data, directory + 14)
            count = named + ids
            if count > 4096 or directory + 16 + count * 8 > len(self.data):
                raise ValueError("invalid PE resource entries")
            for index in range(count):
                name_field, target = struct.unpack_from(
                    "<II", self.data, directory + 16 + index * 8
                )
                if name_field & 0x80000000:
                    name_offset = base + (name_field & 0x7FFFFFFF)
                    length = unpack_u16(self.data, name_offset)
                    start = name_offset + 2
                    name = self.data[start : start + length * 2].decode("utf-16le")
                else:
                    name = name_field & 0xFFFF
                next_path = path + (name,)
                target_offset = target & 0x7FFFFFFF
                if target & 0x80000000:
                    walk(target_offset, next_path, depth + 1)
                    continue
                if len(next_path) != 3:
                    continue
                entry = base + target_offset
                data_rva = unpack_u32(self.data, entry)
                size = unpack_u32(self.data, entry + 4)
                data_offset = self.rva_to_offset(data_rva)
                results[next_path] = self.data[data_offset : data_offset + size]

        walk(0, (), 0)
        return results

    def version(self) -> str:
        versions = [data for key, data in self.resources().items() if key[0] == 16]
        for data in versions:
            key = "VS_VERSION_INFO\0".encode("utf-16le")
            position = 6
            while position + 2 <= len(data) and data[position : position + 2] != b"\0\0":
                position += 2
            position = (position + 4) & ~3
            if data[6:position].find(key) < 0 or position + 24 > len(data):
                continue
            (
                signature,
                _structure_version,
                file_ms,
                file_ls,
                product_ms,
                product_ls,
            ) = struct.unpack_from(
                "<IIIIII", data, position
            )
            if signature != 0xFEEF04BD:
                continue
            file_version = (
                file_ms >> 16, file_ms & 0xFFFF, file_ls >> 16, file_ls & 0xFFFF
            )
            product_version = (
                product_ms >> 16, product_ms & 0xFFFF,
                product_ls >> 16, product_ls & 0xFFFF,
            )
            if file_version != product_version:
                raise ValueError("launcher file and product versions differ")
            return ".".join(str(part) for part in file_version[:3])
        raise ValueError("launcher has no valid VS_VERSION_INFO resource")


def verify_icon(image: PEImage, icon_path: Path) -> None:
    data = icon_path.read_bytes()
    reserved, icon_type, count = struct.unpack_from("<HHH", data)
    if reserved != 0 or icon_type != 1 or count == 0:
        raise ValueError("reference file is not a valid ICO")
    resources = image.resources()
    groups = [
        resource for (kind, name, _language), resource in resources.items()
        if kind == 14 and name == 101
    ]
    icon_resources = {
        name: resource
        for (kind, name, _language), resource in resources.items()
        if kind == 3 and isinstance(name, int)
    }
    if not groups or not icon_resources:
        raise ValueError("launcher is missing its embedded application icon")
    entries = []
    for index in range(count):
        offset = 6 + index * 16
        metadata = data[offset : offset + 8]
        size, image_offset = struct.unpack_from("<II", data, offset + 8)
        payload = data[image_offset : image_offset + size]
        if len(payload) != size:
            raise ValueError("truncated ICO image")
        entries.append((metadata, size, payload))
    for group in groups:
        if len(group) < 6:
            continue
        group_reserved, group_type, group_count = struct.unpack_from("<HHH", group)
        if (
            group_reserved != 0
            or group_type != 1
            or group_count != count
            or len(group) != 6 + group_count * 14
        ):
            continue
        matched = True
        matched_entries = set()
        for index in range(group_count):
            offset = 6 + index * 14
            metadata = group[offset : offset + 8]
            size, resource_id = struct.unpack_from("<IH", group, offset + 8)
            payload = icon_resources.get(resource_id)
            match = next((
                ico_index
                for ico_index, (ico_metadata, ico_size, ico_payload) in enumerate(entries)
                if ico_metadata[:4] == metadata[:4]
                and ico_metadata[6:8] == metadata[6:8]
                and ico_size == size
                and ico_payload == payload
            ), None)
            if match is None or match in matched_entries:
                matched = False
                break
            matched_entries.add(match)
        if matched and len(matched_entries) == count:
            return
    raise ValueError("embedded icon does not match the requested ICO")


def verify_argument_source(source: Path) -> None:
    text = source.read_text(encoding="utf-8")
    required = (
        "CommandLineToArgvW(",
        "QuoteArgument(arguments[index])",
        "arguments.empty() ? nullptr : arguments.c_str()",
        "start_script.c_str()",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError("launcher source no longer forwards arguments correctly: " + ", ".join(missing))


def smoke_arguments(executable: Path) -> None:
    if sys.platform != "win32":
        raise ValueError("argument-forwarding smoke test requires Windows")
    with tempfile.TemporaryDirectory(prefix="algo-launcher-smoke-") as folder:
        directory = Path(folder)
        target = directory / executable.name
        shutil.copy2(executable, target)
        result_file = directory / "forwarded-args.txt"
        (directory / "start.bat").write_text(
            '@echo off\r\n> "%~dp0forwarded-args.txt" echo %*\r\n',
            encoding="ascii",
            newline="",
        )
        subprocess.Popen(
            [str(target), "--algoarchive-launcher-smoke", "two words"],
            cwd=directory,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if result_file.is_file():
                actual = result_file.read_text(encoding="ascii").strip()
                expected = '--algoarchive-launcher-smoke "two words"'
                if actual != expected:
                    raise ValueError(f"launcher changed forwarded arguments: {actual!r}")
                return
            time.sleep(0.05)
        raise ValueError("launcher did not execute the argument-recording start.bat")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--icon", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--smoke-arguments", action="store_true")
    args = parser.parse_args()
    path = args.executable.resolve()
    try:
        image = PEImage(path)
        imports = image.imported_dlls()
        forbidden = [name for name in imports if name.startswith(FORBIDDEN_PREFIXES)]
        if forbidden:
            raise ValueError("launcher imports unbundled MinGW DLLs: " + ", ".join(forbidden))
        if args.version and image.version() != args.version:
            raise ValueError(f"launcher version {image.version()} does not match {args.version}")
        if args.icon:
            verify_icon(image, args.icon.resolve())
        if args.source:
            verify_argument_source(args.source.resolve())
        if args.smoke_arguments:
            smoke_arguments(path)
    except (OSError, ValueError, struct.error, UnicodeDecodeError, subprocess.SubprocessError) as exc:
        print(f"启动器检查失败：{exc}", file=sys.stderr)
        return 1
    print("启动器检查通过")
    if args.version:
        print(f"文件与产品版本：{args.version}")
    if args.icon:
        print("嵌入图标：与发行 ICO 匹配")
    if args.source:
        print("参数转发源码：通过")
    print("导入 DLL：" + ", ".join(imports))
    if args.smoke_arguments:
        print("参数转发运行烟测：通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
