"""CPH-compatible local C++ execution, implemented independently for AlgoArchive.

The test-case import/export shape and judging behavior follow the open-source
CPH project by Divyanshu Agrawal. No CPH TypeScript source is copied here.
Upstream: https://github.com/agrawal-d/cph (GPL-3.0-or-later).
"""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import threading
import time


DEFAULT_CPP_STANDARD = "gnu++14"
CPP_STANDARDS = ("gnu++11", "gnu++14", "gnu++17", "gnu++20", "c++17", "c++20")
DEFAULT_VSCODE_GXX = Path(
    r"D:\x86_64-8.1.0-release-posix-seh-rt_v6-rev0\mingw64\bin\g++.exe"
)
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_TEST_COUNT = 100
MAX_TEST_TEXT_BYTES = 1024 * 1024
MAX_CAPTURE_BYTES = 1024 * 1024
COMPILE_TIMEOUT_SECONDS = 20
_WINDOWS_ERROR_MODE_LOCK = threading.Lock()


def resolve_cpp_compiler(config=None):
    """Return (compiler_path, standard) from config, VS Code default, then PATH."""
    config = dict(config or {})
    compiler = config.get("compiler")
    compiler = dict(compiler) if isinstance(compiler, dict) else {}
    standard = str(compiler.get("cpp_standard") or DEFAULT_CPP_STANDARD)
    if standard not in CPP_STANDARDS:
        standard = DEFAULT_CPP_STANDARD
    configured = str(compiler.get("cpp_path") or "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return candidate.resolve(), standard
        return None, standard
    if DEFAULT_VSCODE_GXX.is_file():
        return DEFAULT_VSCODE_GXX.resolve(), standard
    discovered = shutil.which("g++")
    if discovered:
        return Path(discovered).resolve(), standard
    return None, standard


def compiler_version(compiler_path):
    if not compiler_path:
        return ""
    try:
        completed = subprocess.run(
            [str(compiler_path), "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW")
                else 0
            ),
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    text = completed.stdout.decode("utf-8", errors="replace").strip()
    return text.splitlines()[0] if text else ""


def _popen_without_windows_error_dialog(arguments, **kwargs):
    """Inherit a no-dialog Windows error mode for untrusted student programs."""
    if os.name != "nt":
        return subprocess.Popen(arguments, **kwargs)
    import ctypes

    # SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX
    flags = 0x0001 | 0x0002 | 0x8000
    with _WINDOWS_ERROR_MODE_LOCK:
        kernel32 = ctypes.windll.kernel32
        previous = kernel32.SetErrorMode(flags)
        try:
            return subprocess.Popen(arguments, **kwargs)
        finally:
            kernel32.SetErrorMode(previous)


def validate_test_cases(cases):
    if not isinstance(cases, list):
        raise ValueError("测试用例必须是列表")
    if len(cases) > MAX_TEST_COUNT:
        raise ValueError(f"单道题目最多保存 {MAX_TEST_COUNT} 个测试用例")
    normalized = []
    for index, item in enumerate(cases):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index + 1} 个测试用例格式不正确")
        for field, label in (("input", "输入"), ("output", "期望输出")):
            value = item.get(field, "")
            if not isinstance(value, str):
                raise ValueError(f"第 {index + 1} 个测试用例的{label}必须是文本")
            try:
                encoded = value.encode("utf-8")
            except UnicodeError:
                raise ValueError(f"第 {index + 1} 个测试用例包含无效字符") from None
            if len(encoded) > MAX_TEST_TEXT_BYTES:
                raise ValueError(
                    f"第 {index + 1} 个测试用例的{label}不能超过 1 MiB"
                )
            if "\x00" in value:
                raise ValueError(f"第 {index + 1} 个测试用例的{label}不能包含空字符")
        normalized.append(
            {"input": item.get("input", ""), "output": item.get("output", "")}
        )
    return normalized


class CppTestRunner:
    """Compile one source file and execute each case with a hard timeout."""

    def __init__(self, compiler_path, standard=DEFAULT_CPP_STANDARD, temp_root=None):
        self.compiler_path = Path(compiler_path) if compiler_path else None
        self.standard = (
            standard if standard in CPP_STANDARDS else DEFAULT_CPP_STANDARD
        )
        self.temp_root = Path(temp_root) if temp_root else None
        self._stopped = threading.Event()
        self._active_lock = threading.Lock()
        self._active_process = None

    @staticmethod
    def outputs_match(expected, actual):
        expected_lines = expected.replace("\r\n", "\n").strip().split("\n")
        actual_lines = actual.replace("\r\n", "\n").strip().split("\n")
        if len(expected_lines) != len(actual_lines):
            return False
        return all(
            expected_line.strip() == actual_line.strip()
            for expected_line, actual_line in zip(expected_lines, actual_lines)
        )

    def stop(self):
        self._stopped.set()
        with self._active_lock:
            process = self._active_process
        if process is not None:
            self._terminate_process(process)

    def _terminate_process(self, process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            process.kill()
        except OSError:
            pass

    def _execute(self, arguments, cwd, stdin_data=b"", timeout_seconds=3):
        creationflags = (
            subprocess.CREATE_NO_WINDOW
            if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW")
            else 0
        )
        started = time.monotonic()
        process = _popen_without_windows_error_dialog(
            arguments,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
        with self._active_lock:
            self._active_process = process
        buffers = [bytearray(), bytearray()]

        def collect(stream, target):
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                remaining = MAX_CAPTURE_BYTES - len(target)
                if remaining > 0:
                    target.extend(chunk[:remaining])

        readers = [
            threading.Thread(
                target=collect,
                args=(process.stdout, buffers[0]),
                daemon=True,
            ),
            threading.Thread(
                target=collect,
                args=(process.stderr, buffers[1]),
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            try:
                process.stdin.write(stdin_data)
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            try:
                return_code = process.wait(timeout=max(0.05, timeout_seconds))
            except subprocess.TimeoutExpired:
                timed_out = True
                self._terminate_process(process)
                return_code = process.wait(timeout=5)
        finally:
            with self._active_lock:
                if self._active_process is process:
                    self._active_process = None
            for reader in readers:
                reader.join(timeout=1)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        stdout = bytes(buffers[0]).decode("utf-8", errors="replace")
        stderr = bytes(buffers[1]).decode("utf-8", errors="replace")
        return {
            "return_code": return_code,
            "timed_out": timed_out,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "stdout": stdout,
            "stderr": stderr,
        }

    def run(self, code, cases, time_limit_ms=3000):
        if not isinstance(code, str):
            raise ValueError("代码必须是文本")
        encoded_code = code.encode("utf-8")
        if len(encoded_code) > MAX_SOURCE_BYTES:
            raise ValueError("单份代码不能超过 2 MiB")
        normalized_tests = validate_test_cases(cases)
        if not normalized_tests:
            raise ValueError("请先添加至少一个测试用例")
        try:
            time_limit_ms = int(time_limit_ms)
        except (TypeError, ValueError):
            raise ValueError("运行时限格式不正确") from None
        if not 50 <= time_limit_ms <= 30_000:
            raise ValueError("单个测试用例的运行时限必须在 50 到 30000 毫秒之间")
        if self.compiler_path is None or not self.compiler_path.is_file():
            return {
                "ok": False,
                "compile": {
                    "status": "compiler_missing",
                    "stdout": "",
                    "stderr": (
                        f"找不到 C++ 编译器：{self.compiler_path}"
                        if self.compiler_path
                        else "找不到可用的 g++ 编译器"
                    ),
                    "elapsed_ms": 0,
                },
                "cases": [],
                "elapsed_ms": 0,
                "cancelled": False,
            }

        base = self.temp_root or Path(tempfile.gettempdir())
        base.mkdir(parents=True, exist_ok=True)
        workdir = base / f".algoarchive-cph-{secrets.token_hex(12)}"
        workdir.mkdir()
        try:
            source = workdir / "main.cpp"
            executable = workdir / ("main.exe" if os.name == "nt" else "main")
            source.write_text(code, encoding="utf-8", newline="\n")
            try:
                compile_result = self._execute(
                    [
                        str(self.compiler_path),
                        f"-std={self.standard}",
                        "-O2",
                        "-pipe",
                        "-DCPH",
                        "-DDEBUG",
                        "-o",
                        str(executable),
                        str(source),
                    ],
                    workdir,
                    timeout_seconds=COMPILE_TIMEOUT_SECONDS,
                )
            except OSError as exc:
                return {
                    "ok": False,
                    "compile": {
                        "status": "compiler_error",
                        "stdout": "",
                        "stderr": f"无法启动 C++ 编译器：{exc}",
                        "elapsed_ms": 0,
                    },
                    "cases": [],
                    "elapsed_ms": 0,
                    "cancelled": False,
                }
            compile_status = "success"
            if compile_result["timed_out"]:
                compile_status = "timeout"
            elif compile_result["return_code"] != 0 or not executable.is_file():
                compile_status = "error"
            compile_payload = {
                "status": compile_status,
                "stdout": compile_result["stdout"],
                "stderr": compile_result["stderr"],
                "elapsed_ms": compile_result["elapsed_ms"],
            }
            if compile_status != "success":
                return {
                    "ok": False,
                    "compile": compile_payload,
                    "cases": [],
                    "elapsed_ms": compile_result["elapsed_ms"],
                    "cancelled": self._stopped.is_set()
                    or compile_status == "timeout",
                }

            case_results = []
            all_passed = True
            started = time.monotonic()
            for ordinal, test in enumerate(normalized_tests, start=1):
                if self._stopped.is_set():
                    all_passed = False
                    break
                run_result = self._execute(
                    [str(executable)],
                    workdir,
                    stdin_data=test["input"].encode("utf-8"),
                    timeout_seconds=time_limit_ms / 1000,
                )
                if self._stopped.is_set():
                    status = "cancelled"
                elif run_result["timed_out"]:
                    status = "time_limit"
                elif run_result["return_code"] != 0:
                    status = "runtime_error"
                elif self.outputs_match(test["output"], run_result["stdout"]):
                    status = "passed"
                else:
                    status = "wrong_answer"
                all_passed = all_passed and status == "passed"
                case_results.append(
                    {
                        "ordinal": ordinal,
                        "status": status,
                        "input": test["input"],
                        "expected": test["output"],
                        "stdout": run_result["stdout"],
                        "stderr": run_result["stderr"],
                        "return_code": run_result["return_code"],
                        "elapsed_ms": run_result["elapsed_ms"],
                    }
                )
            return {
                "ok": all_passed and len(case_results) == len(normalized_tests),
                "compile": compile_payload,
                "cases": case_results,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                "cancelled": self._stopped.is_set(),
            }
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
