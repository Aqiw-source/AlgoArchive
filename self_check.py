"""Production smoke check using only packaged files and a temporary database."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    import app

    print(f"算法档案生产自检 / AlgoArchive {app.APP_VERSION}", flush=True)
    required_files = (
        "app.py",
        "cph_runner.py",
        "web/index.html",
        "web/app.js",
        "licenses/CPH-GPL-3.0.txt",
    )
    for relative in required_files:
        require((ROOT / relative).is_file(), f"缺少必要文件：{relative}")
    print("核心文件检查：通过", flush=True)
    bundled_runtime = ROOT / "runtime" / "python.exe"
    print(
        "运行环境：发布包" if bundled_runtime.is_file() else "运行环境：开发 Python",
        flush=True,
    )

    with tempfile.TemporaryDirectory(prefix="algoarchive-self-check-") as temp:
        repo = app.Repository(Path(temp) / "data")
        try:
            schema = repo.db.execute(
                "SELECT value FROM settings WHERE key='schema_version'"
            ).fetchone()[0]
            require(
                schema == str(app.DATABASE_SCHEMA_VERSION),
                f"数据库版本异常：{schema}",
            )
            require(repo.data_dir.is_dir(), "临时数据目录未创建")
        finally:
            repo.close()
    print("临时数据库检查：通过", flush=True)

    compiler, standard = app.resolve_cpp_compiler()
    if compiler and compiler.is_file():
        print(f"C++ 编译器：可用 · {compiler} · {standard}", flush=True)
    else:
        print(
            "C++ 编译器：未找到（不影响题库使用，代码试跑需在设置中选择 g++）",
            flush=True,
        )

    print("生产自检通过。用户数据未被读取或修改。", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"生产自检失败：{exc}", file=sys.stderr, flush=True)
        traceback.print_exc()
        raise SystemExit(1)
