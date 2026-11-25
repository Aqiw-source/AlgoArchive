"""Run an isolated API smoke test with a packaged Python interpreter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    root = args.root.resolve()
    app_source = (root / "app.py").read_text(encoding="utf-8")
    version_match = re.search(
        r'(?m)^APP_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"\s*$', app_source
    )
    if not version_match:
        raise SystemExit("发布包无法从 app.py 读取 APP_VERSION")
    expected_version = version_match.group(1)
    interpreter = root / "runtime" / "python.exe"
    for required in (interpreter, root / "run.py", root / "app.py", root / "web" / "index.html"):
        if not required.is_file():
            raise SystemExit(f"发布包缺少烟测文件: {required.relative_to(root)}")

    with tempfile.TemporaryDirectory(prefix="algo-release-api-smoke-") as folder:
        temp_root = Path(folder)
        data_dir = temp_root / "data"
        config_path = temp_root / "config.json"
        process = subprocess.Popen(
            [
                str(interpreter), "-X", "utf8", "-u", str(root / "run.py"),
                "--data-dir", str(data_dir), "--config-path", str(config_path),
                "--port", "0", "--no-browser",
            ],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        lines: queue.Queue[str] = queue.Queue()

        def collect_output() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                lines.put(line)

        threading.Thread(target=collect_output, daemon=True).start()
        output = []
        base = None
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            if process.poll() is not None and lines.empty():
                break
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                continue
            output.append(line)
            match = re.search(r"本地地址:\s*(http://127\.0\.0\.1:\d+)", line)
            if match:
                base = match.group(1)
                break
        if not base:
            stop_process(process)
            raise RuntimeError("包内 Python 服务未启动:\n" + "".join(output))

        token = None

        def request(method: str, path: str, payload=None, expected=(200,)):
            body = None if payload is None else json.dumps(
                payload, ensure_ascii=False
            ).encode("utf-8")
            headers = {"X-CSRF-Token": token} if token else {}
            if body is not None:
                headers["Content-Type"] = "application/json"
            req = Request(base + path, body, headers, method=method)
            try:
                response = urlopen(req, timeout=5)
            except HTTPError as error:
                response = error
            with response:
                status = response.status
                raw = response.read()
            if status not in expected:
                raise RuntimeError(
                    f"{method} {path} returned HTTP {status}: "
                    + raw.decode("utf-8", errors="replace")
                )
            return None if not raw else json.loads(raw.decode("utf-8"))

        try:
            with urlopen(base + "/", timeout=5) as response:
                page = response.read().decode("utf-8")
            csrf = re.search(
                r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)',
                page,
            )
            if not csrf or csrf.group(1) == "__CSRF_TOKEN__":
                raise RuntimeError("服务首页没有有效 CSRF token")
            token = csrf.group(1)

            health = request("GET", "/api/health")
            if health.get("app") != "AlgoArchive":
                raise RuntimeError(f"health app 标识异常: {health!r}")
            version = health.get("version")
            if version != expected_version:
                raise RuntimeError(
                    f"health 版本 {version!r} 与 app.py 版本 {expected_version!r} 不一致"
                )

            created = request("POST", "/api/problems", {
                "platform": "codeforces",
                "number": "AA-RELEASE-SMOKE",
                "name": "Release package smoke test",
                "url": "https://codeforces.com/contest/999999/problem/A",
                "language": "cpp",
                "code": "int main() { return 0; }\n",
                "contest_id": None,
            }, expected=(201,))
            problem = created["problem"]
            problem_path = f"/api/problems/{problem['id']}"
            code_file = data_dir / problem["code_path"]
            if not code_file.is_file():
                raise RuntimeError("创建题目后没有写入源码文件")

            updated = request("PUT", problem_path, {
                "platform": problem["platform"],
                "number": problem["number"],
                "name": "Release package smoke test updated",
                "url": problem["url"],
                "language": problem["language"],
                "code": "int main() { return 1; }\n",
                "contest_id": problem["contest_id"],
                "version": problem["version"],
            })["problem"]
            if updated["name"] != "Release package smoke test updated":
                raise RuntimeError("题目更新未保存")
            if code_file.read_text(encoding="utf-8") != "int main() { return 1; }\n":
                raise RuntimeError("题目更新后的源码文件内容异常")

            request("DELETE", problem_path, {
                "version": updated["version"],
                "confirmed": True,
            })
            state = request("GET", "/api/state")
            if any(item["id"] == problem["id"] for item in state["problems"]):
                raise RuntimeError("题目删除后仍存在于状态 API")
            if code_file.exists():
                raise RuntimeError("删除题目后源码文件仍存在")

            shutdown = request("POST", "/api/shutdown", {}, expected=(200,))
            if shutdown.get("ok") is not True:
                raise RuntimeError(f"正常关停 API 返回异常: {shutdown!r}")
            try:
                return_code = process.wait(timeout=8)
            except subprocess.TimeoutExpired as error:
                stop_process(process)
                raise RuntimeError("服务收到关停请求后未正常退出") from error
            if return_code != 0:
                raise RuntimeError(
                    f"服务退出码为 {return_code}:\n" + "".join(output)
                )
            print(f"包内 Python API 烟测通过：health/version={version}，题目 CRUD，正常关停")
            return 0
        except (OSError, URLError, ValueError, KeyError, RuntimeError) as error:
            stop_process(process)
            raise SystemExit(f"发布包 API 烟测失败: {error}\n" + "".join(output)) from error


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
