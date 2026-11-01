"""Verify that the Windows launcher has no bundled-toolchain DLL dependencies."""

from __future__ import annotations

from pathlib import Path
import struct
import sys


FORBIDDEN_PREFIXES = (
    "libgcc_s_",
    "libstdc++-",
    "libwinpthread-",
)


def _unpack_u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _unpack_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def imported_dlls(path: Path) -> list[str]:
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("not an MZ executable")
    pe_offset = _unpack_u32(data, 0x3C)
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError("missing PE signature")

    coff_offset = pe_offset + 4
    section_count = _unpack_u16(data, coff_offset + 2)
    optional_size = _unpack_u16(data, coff_offset + 16)
    optional_offset = coff_offset + 20
    optional_magic = _unpack_u16(data, optional_offset)
    if optional_magic == 0x20B:
        data_directory_offset = optional_offset + 112
    elif optional_magic == 0x10B:
        data_directory_offset = optional_offset + 96
    else:
        raise ValueError(f"unsupported PE optional header: 0x{optional_magic:x}")

    import_rva = _unpack_u32(data, data_directory_offset + 8)
    if import_rva == 0:
        raise ValueError("PE has no import directory")

    section_offset = optional_offset + optional_size
    sections = []
    for index in range(section_count):
        offset = section_offset + index * 40
        virtual_size = _unpack_u32(data, offset + 8)
        virtual_address = _unpack_u32(data, offset + 12)
        raw_size = _unpack_u32(data, offset + 16)
        raw_offset = _unpack_u32(data, offset + 20)
        sections.append((virtual_address, max(virtual_size, raw_size), raw_offset))

    def rva_to_offset(rva: int) -> int:
        for virtual_address, span, raw_offset in sections:
            if virtual_address <= rva < virtual_address + span:
                return raw_offset + rva - virtual_address
        raise ValueError(f"RVA is outside all sections: 0x{rva:x}")

    result = []
    descriptor_offset = rva_to_offset(import_rva)
    while True:
        name_rva = _unpack_u32(data, descriptor_offset + 12)
        if name_rva == 0:
            break
        name_offset = rva_to_offset(name_rva)
        end = data.index(b"\0", name_offset)
        result.append(data[name_offset:end].decode("ascii").casefold())
        descriptor_offset += 20
    return result


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify-launcher.py AlgoArchive.exe", file=sys.stderr)
        return 2
    path = Path(sys.argv[1]).resolve()
    try:
        imports = imported_dlls(path)
    except (OSError, ValueError, struct.error, UnicodeDecodeError) as exc:
        print(f"启动器检查失败：{exc}", file=sys.stderr)
        return 1
    forbidden = [
        name for name in imports if name.startswith(FORBIDDEN_PREFIXES)
    ]
    if forbidden:
        print(
            "启动器仍依赖未随包分发的 MinGW 运行库："
            + ", ".join(forbidden),
            file=sys.stderr,
        )
        return 1
    print("启动器依赖检查：通过")
    print("导入 DLL：" + ", ".join(imports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
