"""Windows command entry point for shortcut handling and application startup."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0].casefold() == "--create-shortcut":
        result = app.create_desktop_shortcut()
        print(result["message"], flush=True)
        arguments = arguments[1:]
    return app.main(arguments)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (app.AppError, OSError, sqlite3.Error) as error:
        print(f"启动失败: {error}", file=sys.stderr)
        raise SystemExit(1)
