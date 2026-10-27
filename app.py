#!/usr/bin/env python3
"""AlgoArchive: an offline contest archive, using only Python's standard library."""
from __future__ import annotations

import argparse
import base64
import binascii
from contextlib import closing
import getpass
import hashlib
import html
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, urlunsplit, unquote
from urllib.request import urlopen
import uuid
import webbrowser


APP_VERSION = "1.5.1"
ROOT = Path(__file__).resolve().parent
PROBLEM_PLATFORM_ALIASES = {"codeforces": "codeforces", "atcoder": "atcoder"}
EXTENSIONS = {"cpp": ".cpp", "python": ".py", "java": ".java", "other": ".txt"}
MAX_CODE_BYTES = 2 * 1024 * 1024
MAX_AVATAR_BYTES = 512 * 1024
MAX_BODY_BYTES = 4 * 1024 * 1024
AVATAR_EXTENSIONS = {
    "png": (".png", "image/png"),
    "jpeg": (".jpg", "image/jpeg"),
    "webp": (".webp", "image/webp"),
}
AVATAR_PATH_PATTERN = r"avatar/avatar\.(png|jpg|webp)"


def decode_avatar_data_url(value):
    if not isinstance(value, str):
        raise AppError("头像必须是图片数据")
    if len(value) > 900_000:
        raise AppError("头像图片不能超过 512 KiB", 413, "too_large")
    match = re.fullmatch(
        r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)",
        value,
    )
    if not match:
        raise AppError("头像必须是 PNG、JPEG 或 WebP 图片")
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except (ValueError, binascii.Error):
        raise AppError("头像图片数据无效") from None
    if len(raw) > MAX_AVATAR_BYTES:
        raise AppError("头像图片不能超过 512 KiB", 413, "too_large")
    image_type = match.group(1)
    valid_header = (
        (image_type == "png" and raw.startswith(b"\x89PNG\r\n\x1a\n"))
        or (image_type == "jpeg" and raw.startswith(b"\xff\xd8\xff"))
        or (
            image_type == "webp"
            and raw.startswith(b"RIFF")
            and raw[8:12] == b"WEBP"
        )
    )
    if not valid_header:
        raise AppError("头像文件内容与图片格式不匹配")
    extension, mime = AVATAR_EXTENSIONS[image_type]
    return raw, extension, mime


def default_data_dir():
    """Return the per-user data directory used outside the program folder."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and (
        not local_app_data
        or "\\packages\\" in local_app_data.casefold().replace("/", "\\")
    ):
        local_app_data = str(Path.home() / "AppData" / "Local")
    if local_app_data:
        return Path(local_app_data) / "AlgoArchive" / "data"
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "algoarchive" / "data"


def chrome_candidates():
    """Return standard Google Chrome executable locations."""
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data)
            / "Google" / "Chrome" / "Application" / "chrome.exe"
        )
    return list(dict.fromkeys(candidates))


def find_chrome_executable():
    for candidate in chrome_candidates():
        if candidate.is_file():
            return candidate
    return None


def open_browser(url):
    """Open AlgoArchive in Chrome, falling back to the system default."""
    chrome = find_chrome_executable()
    if chrome is not None:
        try:
            subprocess.Popen([str(chrome), url], close_fds=True)
            return True
        except OSError:
            pass
    return webbrowser.open(url)


def _verify_migrated_data(path):
    database = path / "archive.sqlite3"
    with closing(sqlite3.connect(str(database))) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise AppError("旧数据库完整性检查失败，未执行迁移", 500, "migration_failed")
        pending = set()
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pending_files'"
        ).fetchone():
            pending = {row[0] for row in db.execute("SELECT path FROM pending_files")}
        code_paths = set()
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='problems'"
        ).fetchone():
            code_paths.update(
                row[0] for row in db.execute("SELECT code_path FROM problems")
            )
        if db.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='algorithm_snippets'"
        ).fetchone():
            code_paths.update(
                row[0] for row in db.execute("SELECT code_path FROM algorithm_snippets")
            )
    for relative in code_paths:
        if relative in pending:
            continue
        if not re.fullmatch(
            r"codes/[a-f0-9]{32}\.(cpp|py|java|txt)", relative
        ):
            raise AppError("旧数据包含非法代码路径，未执行迁移", 500, "migration_failed")
        target = path / relative
        if not target.is_file():
            raise AppError("旧数据缺少源代码文件，未执行迁移", 500, "migration_failed")


def migrate_legacy_data(legacy, target):
    """Copy legacy in-program data to the user directory, then archive it."""
    legacy = Path(legacy).resolve()
    target = Path(target).resolve()
    if not (legacy / "archive.sqlite3").is_file():
        return None
    if target.exists() and any(target.iterdir()):
        return None

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(
        tempfile.mkdtemp(prefix=".algoarchive-migrating-", dir=str(target.parent))
    )
    copied = temp_root / "data"
    legacy_lock = DataDirectoryLock(legacy)
    try:
        if not legacy_lock.acquired:
            raise AppError(
                "旧数据目录正在使用，无法安全迁移。请关闭旧程序后重试。",
                409,
                "migration_locked",
            )
        shutil.copytree(
            legacy,
            copied,
            ignore=shutil.ignore_patterns("runtime.lock", "runtime.lock.pending"),
        )
        _verify_migrated_data(copied)
        legacy_lock.close()
        if target.exists():
            target.rmdir()
        os.replace(copied, target)
    except Exception:
        legacy_lock.close()
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    backup_root = target.parent / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = backup_root / f"legacy-data-{stamp}"
    try:
        shutil.move(str(legacy), str(backup))
    except OSError as exc:
        print(
            f"旧数据已复制到 {target}，但原目录暂时无法归档：{exc}",
            file=sys.stderr,
            flush=True,
        )
        return None
    return backup


class AppError(Exception):
    def __init__(self, message, status=400, code="invalid", **details):
        super().__init__(message)
        self.status, self.code, self.details = status, code, details

    def payload(self):
        return {"error": str(self), "code": self.code, **self.details}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def text_value(value, label, limit, required=False):
    if not isinstance(value, str):
        raise AppError(f"{label}必须是文本")
    value = value.strip()
    if required and not value:
        raise AppError(f"请填写{label}")
    if len(value) > limit or any(ord(c) < 32 for c in value):
        raise AppError(f"{label}长度或格式不正确（最多 {limit} 个字符）")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise AppError(f"{label}包含无效字符") from None
    return value


def multiline_text_value(value, label, limit, required=False):
    if not isinstance(value, str):
        raise AppError(f"{label}必须是文本")
    value = value.strip()
    if required and not value:
        raise AppError(f"请填写{label}")
    if len(value) > limit or any(ord(c) < 32 and c not in {"\n", "\t"} for c in value):
        raise AppError(f"{label}长度或格式不正确（最多 {limit} 个字符）")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise AppError(f"{label}包含无效字符") from None
    return value


def editable_platform_value(value):
    platform = text_value(value, "所属平台", 100, True)
    return PROBLEM_PLATFORM_ALIASES.get(platform.casefold(), platform)


def normalize_external_url(value):
    """Validate a general reference URL and return a stable identity."""
    value = text_value(value, "链接", 2048, True)
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()
        if scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            raise ValueError()
        port = parsed.port
    except ValueError:
        raise AppError("请填写有效的 http/https 参考链接") from None
    host_port = host
    if port not in {None, 80, 443}:
        host_port = f"{host}:{port}"
    path = unquote(parsed.path) or "/"
    normalized = urlunsplit((scheme, host_port, path, parsed.query, ""))
    return value, normalized


class DataDirectoryLock:
    """An OS-owned lock, automatically released after a crash or window close."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "runtime.lock"
        self.stream = self.path.open("a+b")
        self.acquired = False
        self.stream.seek(0, os.SEEK_END)
        if self.stream.tell() == 0:
            self.stream.write(b" ")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.acquired = True
        except OSError:
            self.stream.close()

    def set_port(self, port):
        if self.acquired:
            # Open in append mode initially only to safely create. Rewrite using
            # a second handle after the locked first byte (Windows byte locking).
            with self.path.open("r+b") as stream:
                stream.seek(1)
                stream.write(json.dumps({"port": port, "pid": os.getpid()}).encode("ascii"))
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())

    def read_port(self):
        try:
            with self.path.open("rb") as stream:
                stream.seek(1)
                return json.loads(stream.read(2048)).get("port")
        except (OSError, ValueError):
            return None

    def close(self):
        if self.acquired:
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.acquired = False
            self.stream.close()


class Repository:
    """SQLite is the single metadata source. Actual code lives in codes/.

    The pending_files outbox joins metadata and file operations durably. A
    committed outbox is replayed before any read and before serving at startup.
    A crash at any point can therefore never silently lose a committed save.
    Code in this recovery journal is removed immediately after file writeback.
    """

    def __init__(self, data_dir, acquire_lock=True):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.process_lock = DataDirectoryLock(self.data_dir) if acquire_lock else None
        if self.process_lock is not None and not self.process_lock.acquired:
            raise AppError("此数据目录已被另一个运行中的程序使用", 409, "already_running")
        (self.data_dir / "codes").mkdir(exist_ok=True)
        self.avatar_dir = self.data_dir / "avatar"
        self.avatar_dir.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(self.data_dir / "archive.sqlite3"), check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT OR IGNORE INTO settings VALUES ('schema_version', '7');
            INSERT OR IGNORE INTO settings VALUES ('problem_order_version', '1');
            CREATE TABLE IF NOT EXISTS contests (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                title TEXT NOT NULL, url TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS problems (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                number TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL, normalized_url TEXT NOT NULL,
                language TEXT NOT NULL CHECK(language IN ('cpp','python','java','other')),
                contest_id TEXT REFERENCES contests(id) ON DELETE SET NULL,
                algorithm_id TEXT REFERENCES algorithms(id) ON DELETE SET NULL,
                algorithm_order INTEGER NOT NULL DEFAULT 0,
                global_order INTEGER NOT NULL DEFAULT 0,
                code_path TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                UNIQUE(platform, normalized_url)
            );
            CREATE TABLE IF NOT EXISTS pending_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL CHECK(action IN ('write','delete')),
                path TEXT NOT NULL,
                content BLOB
            );
            CREATE TABLE IF NOT EXISTS algorithms (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS algorithm_snippets (
                id TEXT PRIMARY KEY,
                algorithm_id TEXT NOT NULL REFERENCES algorithms(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                language TEXT NOT NULL CHECK(language IN ('cpp','python','java','other')),
                code_path TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS algorithm_links (
                id TEXT PRIMARY KEY,
                algorithm_id TEXT NOT NULL REFERENCES algorithms(id) ON DELETE CASCADE,
                title TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL,
                normalized_url TEXT NOT NULL,
                UNIQUE(algorithm_id, normalized_url)
            );
            CREATE INDEX IF NOT EXISTS algorithms_updated ON algorithms(updated_at DESC);
            CREATE INDEX IF NOT EXISTS algorithm_snippets_algorithm
                ON algorithm_snippets(algorithm_id);
            CREATE INDEX IF NOT EXISTS algorithm_snippets_updated
                ON algorithm_snippets(updated_at DESC);
            CREATE INDEX IF NOT EXISTS algorithm_links_algorithm
                ON algorithm_links(algorithm_id);
        """)
        problem_columns = {
            row["name"] for row in self.db.execute("PRAGMA table_info(problems)")
        }
        if "algorithm_id" not in problem_columns:
            with self.db:
                self.db.execute(
                    "ALTER TABLE problems ADD COLUMN algorithm_id TEXT "
                    "REFERENCES algorithms(id) ON DELETE SET NULL"
                )
        order_added = "algorithm_order" not in problem_columns
        if order_added:
            with self.db:
                self.db.execute(
                    "ALTER TABLE problems ADD COLUMN algorithm_order "
                    "INTEGER NOT NULL DEFAULT 0"
                )
        global_order_added = "global_order" not in problem_columns
        if global_order_added:
            with self.db:
                self.db.execute(
                    "ALTER TABLE problems ADD COLUMN global_order "
                    "INTEGER NOT NULL DEFAULT 0"
                )
        schema_version = self.db.execute(
            "SELECT value FROM settings WHERE key='schema_version'"
        ).fetchone()[0]
        if schema_version not in {"1", "2", "3", "4", "5", "6", "7"}:
            raise AppError("数据库版本不兼容，请使用较新版本程序", 500, "schema_version")
        problem_sql = self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='problems'"
        ).fetchone()[0]
        if "CHECK(platform IN ('codeforces','atcoder'))" in problem_sql:
            self._rebuild_problems_for_custom_platforms()
        contest_sql = self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='contests'"
        ).fetchone()[0]
        if "CHECK(platform IN ('codeforces','atcoder'))" in contest_sql:
            self._rebuild_contests_for_custom_platforms()
        if schema_version != "7" or order_added:
            self._initialize_algorithm_problem_orders()
        if schema_version != "7" or global_order_added:
            self._initialize_problem_global_orders()
        if schema_version != "7":
            with self.db:
                self.db.execute(
                    "UPDATE settings SET value='7' WHERE key='schema_version'"
                )
        self.db.executescript("""
            CREATE INDEX IF NOT EXISTS problems_contest ON problems(contest_id);
            CREATE INDEX IF NOT EXISTS problems_algorithm ON problems(algorithm_id);
            CREATE INDEX IF NOT EXISTS problems_algorithm_order
                ON problems(algorithm_id, algorithm_order, updated_at DESC);
            CREATE INDEX IF NOT EXISTS problems_global_order
                ON problems(global_order, updated_at DESC);
            CREATE INDEX IF NOT EXISTS problems_updated ON problems(updated_at DESC);
        """)
        self._flush_pending()
        self._migrate_profile_avatar()

    def close(self):
        with self.lock:
            self.db.close()
            if self.process_lock:
                self.process_lock.close()

    def _rebuild_problems_for_custom_platforms(self):
        """Remove the legacy fixed platform CHECK without losing problem rows."""
        self.db.commit()
        self.db.execute("PRAGMA foreign_keys=OFF")
        try:
            with self.db:
                self.db.execute("DROP TABLE IF EXISTS problems_schema4")
                self.db.execute("""
                    CREATE TABLE problems_schema4 (
                        id TEXT PRIMARY KEY,
                        platform TEXT NOT NULL,
                        number TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
                        url TEXT NOT NULL, normalized_url TEXT NOT NULL,
                        language TEXT NOT NULL CHECK(language IN ('cpp','python','java','other')),
                        contest_id TEXT REFERENCES contests(id) ON DELETE SET NULL,
                        algorithm_id TEXT REFERENCES algorithms(id) ON DELETE SET NULL,
                        algorithm_order INTEGER NOT NULL DEFAULT 0,
                        global_order INTEGER NOT NULL DEFAULT 0,
                        code_path TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        version INTEGER NOT NULL DEFAULT 1,
                        UNIQUE(platform, normalized_url)
                    )
                """)
                self.db.execute("""
                    INSERT INTO problems_schema4
                        (id,platform,number,name,url,normalized_url,language,
                         contest_id,algorithm_id,algorithm_order,global_order,code_path,
                         created_at,updated_at,version)
                    SELECT id,platform,number,name,url,normalized_url,language,
                           contest_id,algorithm_id,algorithm_order,global_order,code_path,
                           created_at,updated_at,version
                    FROM problems
                """)
                self.db.execute("DROP TABLE problems")
                self.db.execute("ALTER TABLE problems_schema4 RENAME TO problems")
                if self.db.execute("PRAGMA foreign_key_check").fetchone():
                    raise AppError(
                        "数据库关联数据不完整，无法升级，请先恢复最近备份",
                        500,
                        "storage_error",
                    )
        finally:
            self.db.execute("PRAGMA foreign_keys=ON")

    def _initialize_algorithm_problem_orders(self):
        rows = self.db.execute(
            "SELECT id,algorithm_id FROM problems "
            "WHERE algorithm_id IS NOT NULL "
            "ORDER BY algorithm_id,updated_at DESC,id"
        ).fetchall()
        counters = {}
        updates = []
        for row in rows:
            order = counters.get(row["algorithm_id"], 0)
            updates.append((order, row["id"]))
            counters[row["algorithm_id"]] = order + 1
        with self.db:
            self.db.executemany(
                "UPDATE problems SET algorithm_order=? WHERE id=?",
                updates,
            )

    def _initialize_problem_global_orders(self):
        rows = self.db.execute(
            "SELECT id FROM problems ORDER BY updated_at DESC,id"
        ).fetchall()
        with self.db:
            self.db.executemany(
                "UPDATE problems SET global_order=? WHERE id=?",
                [(order, row["id"]) for order, row in enumerate(rows)],
            )

    def _rebuild_contests_for_custom_platforms(self):
        """Remove the legacy fixed platform CHECK without losing contest rows."""
        self.db.commit()
        self.db.execute("PRAGMA foreign_keys=OFF")
        try:
            with self.db:
                self.db.execute("DROP TABLE IF EXISTS contests_schema5")
                self.db.execute("""
                    CREATE TABLE contests_schema5 (
                        id TEXT PRIMARY KEY,
                        platform TEXT NOT NULL,
                        title TEXT NOT NULL, url TEXT NOT NULL,
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        version INTEGER NOT NULL DEFAULT 1
                    )
                """)
                self.db.execute("""
                    INSERT INTO contests_schema5
                        (id,platform,title,url,created_at,updated_at,version)
                    SELECT id,platform,title,url,created_at,updated_at,version
                    FROM contests
                """)
                self.db.execute("DROP TABLE contests")
                self.db.execute("ALTER TABLE contests_schema5 RENAME TO contests")
                if self.db.execute("PRAGMA foreign_key_check").fetchone():
                    raise AppError(
                        "数据库关联数据不完整，无法升级，请先恢复最近备份",
                        500,
                        "storage_error",
                    )
        finally:
            self.db.execute("PRAGMA foreign_keys=ON")

    def _path(self, relative):
        # Never use user-supplied paths, even when a database was manually edited.
        if not re.fullmatch(r"codes/[a-f0-9]{32}\.(cpp|py|java|txt)", relative):
            raise AppError("代码文件路径不合法，请恢复完整备份", 500, "storage_error")
        # The strict relative-path check above prevents traversal. Avoid resolving
        # the full path because Windows may map a logical LocalAppData path to a
        # different virtualized final path for Microsoft Store-hosted processes.
        return self.data_dir / relative

    @staticmethod
    def _sync_directory(path):
        if os.name != "nt":
            fd = os.open(str(path), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def _flush_pending(self):
        try:
            for op in self.db.execute("SELECT * FROM pending_files ORDER BY id").fetchall():
                path = self._path(op["path"])
                if op["action"] == "write":
                    temp = path.with_name(path.name + ".pending")
                    with temp.open("wb") as stream:
                        stream.write(op["content"])
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temp, path)
                else:
                    path.unlink(missing_ok=True)
                self._sync_directory(path.parent)
                with self.db:
                    self.db.execute("DELETE FROM pending_files WHERE id=?", (op["id"],))
        except OSError as exc:
            raise AppError("代码文件写入尚未完成，请检查磁盘空间和目录权限，重启后会自动恢复。请勿删除 data 目录。", 503, "storage_pending") from exc

    def _ready(self):
        self._flush_pending()

    def _avatar_path(self, relative):
        if not re.fullmatch(AVATAR_PATH_PATTERN, relative):
            return None
        return self.data_dir / relative

    def _write_avatar_file(self, raw, extension):
        target = self.avatar_dir / f"avatar{extension}"
        temp = target.with_name(target.name + ".pending")
        try:
            with temp.open("wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, target)
            self._sync_directory(target.parent)
        except OSError as exc:
            raise AppError("头像文件保存失败，请检查数据目录权限", 503, "storage_error") from exc
        return target.relative_to(self.data_dir).as_posix()

    def _remove_avatar_files(self, keep=None):
        for path in self.avatar_dir.glob("avatar.*"):
            relative = path.relative_to(self.data_dir).as_posix()
            if relative != keep:
                path.unlink(missing_ok=True)

    def _migrate_profile_avatar(self):
        rows = self.db.execute(
            "SELECT key,value FROM settings WHERE key IN ('profile_avatar','profile_avatar_path')"
        ).fetchall()
        values = {row[0]: row[1] for row in rows}
        current = self._avatar_path(values.get("profile_avatar_path", ""))
        if current is not None and current.is_file():
            return
        legacy = values.get("profile_avatar", "")
        if not legacy:
            return
        try:
            raw, extension, _ = decode_avatar_data_url(legacy)
            relative = self._write_avatar_file(raw, extension)
        except AppError:
            return
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES ('profile_avatar_path',?)",
                (relative,),
            )
            self.db.execute("DELETE FROM settings WHERE key='profile_avatar'")
        self._remove_avatar_files(relative)

    def get_profile(self):
        rows = self.db.execute(
            "SELECT key,value FROM settings WHERE key IN ('profile_name','profile_avatar_path')"
        ).fetchall()
        values = {row[0]: row[1] for row in rows}
        avatar = ""
        avatar_path = self._avatar_path(values.get("profile_avatar_path", ""))
        if avatar_path is not None and avatar_path.is_file():
            try:
                version = avatar_path.stat().st_mtime_ns
            except OSError:
                version = 0
            avatar = f"/api/profile/avatar?v={version}"
        return {
            "name": values.get("profile_name", ""),
            "avatar": avatar,
        }

    def read_avatar(self):
        with self.lock:
            row = self.db.execute(
                "SELECT value FROM settings WHERE key='profile_avatar_path'"
            ).fetchone()
            if row is None:
                raise AppError("尚未设置头像", 404, "not_found")
            avatar_path = self._avatar_path(row[0])
            if avatar_path is None or not avatar_path.is_file():
                raise AppError("头像文件不存在，请重新设置头像", 404, "not_found")
            try:
                data = avatar_path.read_bytes()
            except OSError as exc:
                raise AppError("头像文件读取失败，请检查数据目录权限", 503, "storage_error") from exc
            if len(data) > MAX_AVATAR_BYTES:
                raise AppError("头像文件超过大小限制，请重新设置头像", 413, "too_large")
            mime = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".webp": "image/webp",
            }[avatar_path.suffix]
            return data, mime

    def update_profile(self, payload):
        name = text_value(payload.get("name"), "用户名", 50, True)
        avatar_supplied = "avatar" in payload
        avatar = payload.get("avatar") if avatar_supplied else None
        decoded = None
        if avatar_supplied and avatar:
            decoded = decode_avatar_data_url(avatar)
        elif avatar_supplied and not isinstance(avatar, str):
            raise AppError("头像必须是图片数据")
        with self.lock:
            self._ready()
            keep = None
            if decoded is not None:
                raw, extension, _ = decoded
                keep = self._write_avatar_file(raw, extension)
            with self.db:
                self.db.execute(
                    "INSERT OR REPLACE INTO settings(key,value) VALUES ('profile_name',?)",
                    (name,),
                )
                self.db.execute("DELETE FROM settings WHERE key='profile_avatar'")
                if avatar_supplied:
                    if keep:
                        self.db.execute(
                            "INSERT OR REPLACE INTO settings(key,value) VALUES ('profile_avatar_path',?)",
                            (keep,),
                        )
                    else:
                        self.db.execute(
                            "DELETE FROM settings WHERE key='profile_avatar_path'"
                        )
            if avatar_supplied:
                self._remove_avatar_files(keep)
        return self.get_profile()

    def _row(self, table, identifier):
        row = self.db.execute(f"SELECT * FROM {table} WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise AppError("记录不存在或已被删除", 404, "not_found")
        return dict(row)

    @staticmethod
    def _version(row, payload):
        value = payload.get("version")
        if type(value) is not int or value != row["version"]:
            raise AppError("记录已发生变化，请刷新页面后重新操作。未保存的代码请先复制保留。", 409, "version_conflict")

    def _contest(self, identifier):
        row = self._row("contests", identifier)
        row["problem_count"] = self.db.execute("SELECT COUNT(*) FROM problems WHERE contest_id=?", (identifier,)).fetchone()[0]
        return row

    def _problem(self, identifier, with_code=True):
        row = self._row("problems", identifier)
        contest = self.db.execute("SELECT title FROM contests WHERE id=?", (row["contest_id"],)).fetchone()
        row["contest_title"] = contest[0] if contest else None
        algorithm = self.db.execute(
            "SELECT name FROM algorithms WHERE id=?", (row["algorithm_id"],)
        ).fetchone()
        row["algorithm_name"] = algorithm[0] if algorithm else None
        if with_code:
            try:
                row["code"] = self._path(row["code_path"]).read_bytes().decode("utf-8")
            except (OSError, UnicodeError) as exc:
                raise AppError("代码文件缺失或无法读取，请检查 data/codes 或恢复备份。原记录已保留。", 500, "code_unavailable") from exc
        return row

    def _algorithm_links(self, identifier):
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT id,title,url,normalized_url FROM algorithm_links "
                "WHERE algorithm_id=? ORDER BY rowid",
                (identifier,),
            )
        ]

    def _algorithm_snippets(self, identifier):
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT id,algorithm_id,title,language,code_path,created_at,updated_at,version "
                "FROM algorithm_snippets WHERE algorithm_id=? "
                "ORDER BY updated_at DESC,id",
                (identifier,),
            )
        ]

    def _algorithm(self, identifier):
        row = self._row("algorithms", identifier)
        row["links"] = self._algorithm_links(identifier)
        row["snippets"] = self._algorithm_snippets(identifier)
        row["problem_count"] = self.db.execute(
            "SELECT COUNT(*) FROM problems WHERE algorithm_id=?", (identifier,)
        ).fetchone()[0]
        return row

    def _snippet(self, identifier, with_code=True):
        row = self._row("algorithm_snippets", identifier)
        algorithm = self.db.execute(
            "SELECT name FROM algorithms WHERE id=?", (row["algorithm_id"],)
        ).fetchone()
        row["algorithm_name"] = algorithm[0] if algorithm else None
        if with_code:
            try:
                row["code"] = self._path(row["code_path"]).read_bytes().decode("utf-8")
            except (OSError, UnicodeError) as exc:
                raise AppError(
                    "代码文件缺失或无法读取，请检查 data/codes 或恢复备份。原记录已保留。",
                    500,
                    "code_unavailable",
                ) from exc
        return row

    def _touch_contests(self, ids, timestamp):
        for identifier in set(ids) - {None}:
            self.db.execute("UPDATE contests SET updated_at=?,version=version+1 WHERE id=?", (timestamp, identifier))

    def _touch_algorithm(self, identifier, timestamp):
        self.db.execute(
            "UPDATE algorithms SET updated_at=? WHERE id=?", (timestamp, identifier)
        )

    def _next_algorithm_order(self, identifier):
        if identifier is None:
            return 0
        row = self.db.execute(
            "SELECT COALESCE(MAX(algorithm_order),-1)+1 "
            "FROM problems WHERE algorithm_id=?",
            (identifier,),
        ).fetchone()
        return int(row[0])

    def _next_problem_global_order(self):
        row = self.db.execute(
            "SELECT COALESCE(MAX(global_order),-1)+1 FROM problems"
        ).fetchone()
        return int(row[0])

    def _validate_problem(self, payload):
        platform = editable_platform_value(payload.get("platform"))
        number = text_value(payload.get("number", ""), "题目编号", 50)
        name = text_value(payload.get("name", ""), "题目名称", 300)
        if not number and not name:
            raise AppError("请至少填写题目编号或名称")
        url = text_value(payload.get("url"), "题目链接", 2048, True)
        language = payload.get("language")
        if not isinstance(language, str) or language not in EXTENSIONS:
            raise AppError("代码语言不受支持")
        contest_id = payload.get("contest_id")
        if contest_id == "":
            contest_id = None
        if contest_id is not None:
            if not isinstance(contest_id, str):
                raise AppError("所属比赛不正确")
            contest = self._row("contests", contest_id)
            if contest["platform"].casefold() != platform.casefold():
                raise AppError("题目与所属比赛必须来自同一平台")
        algorithm_id = payload.get("algorithm_id")
        if algorithm_id == "":
            algorithm_id = None
        if algorithm_id is not None:
            if not isinstance(algorithm_id, str):
                raise AppError("所属算法不正确")
            self._row("algorithms", algorithm_id)
        code = payload.get("code", "")
        if not isinstance(code, str):
            raise AppError("代码必须是文本")
        try:
            encoded = code.encode("utf-8")
        except UnicodeError:
            raise AppError("代码包含无效字符") from None
        if len(encoded) > MAX_CODE_BYTES:
            raise AppError("单道题目的代码不能超过 2 MiB", 413, "too_large")
        return dict(platform=platform, number=number, name=name, url=url, normalized_url=url,
                    language=language, contest_id=contest_id, algorithm_id=algorithm_id), encoded

    def _validate_algorithm(self, payload):
        name = text_value(payload.get("name"), "算法名称", 200, True)
        category = text_value(payload.get("category", ""), "算法分类", 100)
        description = multiline_text_value(
            payload.get("description", ""), "算法说明", 10_000
        )
        raw_links = payload.get("links", [])
        if not isinstance(raw_links, list):
            raise AppError("参考链接必须是列表")
        if len(raw_links) > 50:
            raise AppError("单个算法最多保存 50 条参考链接", 413, "too_large")
        links = []
        seen = set()
        for item in raw_links:
            if not isinstance(item, dict):
                raise AppError("参考链接格式不正确")
            title = text_value(item.get("title", ""), "链接标题", 300)
            url, normalized = normalize_external_url(item.get("url"))
            if normalized in seen:
                continue
            seen.add(normalized)
            links.append(
                {"title": title, "url": url, "normalized_url": normalized}
            )
        return {
            "name": name,
            "category": category,
            "description": description,
        }, links

    def _validate_snippet(self, payload):
        title = text_value(payload.get("title"), "模板名称", 300, True)
        language = payload.get("language")
        if not isinstance(language, str) or language not in EXTENSIONS:
            raise AppError("代码语言不受支持")
        code = payload.get("code", "")
        if not isinstance(code, str):
            raise AppError("代码必须是文本")
        try:
            encoded = code.encode("utf-8")
        except UnicodeError:
            raise AppError("代码包含无效字符") from None
        if len(encoded) > MAX_CODE_BYTES:
            raise AppError("单份代码不能超过 2 MiB", 413, "too_large")
        return {"title": title, "language": language}, encoded, code

    def _replace_algorithm_links(self, identifier, links):
        self.db.execute(
            "DELETE FROM algorithm_links WHERE algorithm_id=?", (identifier,)
        )
        self.db.executemany(
            "INSERT INTO algorithm_links "
            "(id,algorithm_id,title,url,normalized_url) VALUES (?,?,?,?,?)",
            [
                (uuid.uuid4().hex, identifier, item["title"], item["url"], item["normalized_url"])
                for item in links
            ],
        )

    def _duplicate(self, values, identifier=None):
        existing = self.db.execute("SELECT id FROM problems WHERE platform=? AND normalized_url=?",
                                   (values["platform"], values["normalized_url"])).fetchone()
        if existing and existing[0] != identifier:
            raise AppError("这道题目已存在，请打开已有题目进行编辑或关联比赛，代码不会重复保存。", 409,
                           "duplicate_problem", existing_id=existing[0])

    def state(self):
        with self.lock:
            self._ready()
            contests = [dict(r) for r in self.db.execute("""SELECT c.*,
                (SELECT COUNT(*) FROM problems p WHERE p.contest_id=c.id) AS problem_count
                FROM contests c ORDER BY c.updated_at DESC, c.id""")]
            problems = [dict(r) for r in self.db.execute("""SELECT p.*,
                c.title AS contest_title, a.name AS algorithm_name
                FROM problems p
                LEFT JOIN contests c ON p.contest_id=c.id
                LEFT JOIN algorithms a ON p.algorithm_id=a.id
                ORDER BY p.updated_at DESC,p.id""")]
            algorithms = [
                self._algorithm(row["id"])
                for row in self.db.execute(
                    "SELECT id FROM algorithms ORDER BY updated_at DESC,id"
                )
            ]
            snippet_count = sum(len(item["snippets"]) for item in algorithms)
            order_version = int(
                self.db.execute(
                    "SELECT value FROM settings WHERE key='problem_order_version'"
                ).fetchone()[0]
            )
            return {
                "contests": contests,
                "problems": problems,
                "algorithms": algorithms,
                "profile": self.get_profile(),
                "problem_order_version": order_version,
                "stats": {
                    "contest_count": len(contests),
                    "problem_count": len(problems),
                    "algorithm_count": len(algorithms),
                    "snippet_count": snippet_count,
                    "codeforces_count": sum(
                        p["platform"] == "codeforces" for p in problems
                    ),
                    "atcoder_count": sum(
                        p["platform"] == "atcoder" for p in problems
                    ),
                },
            }

    def get_problem(self, identifier):
        with self.lock:
            self._ready()
            return self._problem(identifier)

    def get_contest(self, identifier):
        with self.lock:
            self._ready()
            return self._contest(identifier)

    def get_algorithm(self, identifier):
        with self.lock:
            self._ready()
            return self._algorithm(identifier)

    def get_snippet(self, identifier):
        with self.lock:
            self._ready()
            return self._snippet(identifier)

    def create_contest(self, payload):
        with self.lock:
            self._ready()
            platform = editable_platform_value(payload.get("platform"))
            title = text_value(payload.get("title"), "比赛标题", 300, True)
            url = text_value(payload.get("url"), "比赛链接", 2048, True)
            identifier, timestamp = uuid.uuid4().hex, now()
            with self.db:
                self.db.execute("INSERT INTO contests VALUES (?,?,?,?,?,?,1)",
                                (identifier, platform, title, url, timestamp, timestamp))
            return self._contest(identifier)

    def update_contest(self, identifier, payload):
        with self.lock:
            self._ready()
            old = self._row("contests", identifier)
            self._version(old, payload)
            values = {**old, **payload}
            platform = editable_platform_value(values.get("platform"))
            title = text_value(values.get("title"), "比赛标题", 300, True)
            url = text_value(values.get("url"), "比赛链接", 2048, True)
            if platform != old["platform"] and self.db.execute("SELECT 1 FROM problems WHERE contest_id=? LIMIT 1", (identifier,)).fetchone():
                raise AppError("比赛已有题目，不能更换平台。请先取消这些题目的关联。")
            with self.db:
                self.db.execute("UPDATE contests SET platform=?,title=?,url=?,updated_at=?,version=version+1 WHERE id=?",
                                (platform, title, url, now(), identifier))
            return self._contest(identifier)

    def create_problem(self, payload):
        with self.lock:
            self._ready()
            values, encoded = self._validate_problem(payload)
            self._duplicate(values)
            identifier, timestamp = uuid.uuid4().hex, now()
            algorithm_order = self._next_algorithm_order(values["algorithm_id"])
            global_order = self._next_problem_global_order()
            path = f"codes/{identifier}{EXTENSIONS[values['language']]}"
            with self.db:
                self.db.execute("""INSERT INTO problems
                    (id,platform,number,name,url,normalized_url,language,contest_id,algorithm_id,algorithm_order,global_order,code_path,created_at,updated_at,version)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""", (identifier, values["platform"], values["number"], values["name"],
                    values["url"], values["normalized_url"], values["language"], values["contest_id"],
                    values["algorithm_id"], algorithm_order, global_order, path, timestamp, timestamp))
                self.db.execute("INSERT INTO pending_files(action,path,content) VALUES ('write',?,?)", (path, encoded))
                self._touch_contests([values["contest_id"]], timestamp)
                self._touch_algorithm(values["algorithm_id"], timestamp)
            self._flush_pending()
            return self._problem(identifier)

    def update_problem(self, identifier, payload):
        with self.lock:
            self._ready()
            old = self._problem(identifier)
            self._version(old, payload)
            values, encoded = self._validate_problem({**old, **payload})
            self._duplicate(values, identifier)
            algorithm_order = (
                old["algorithm_order"]
                if values["algorithm_id"] == old["algorithm_id"]
                else self._next_algorithm_order(values["algorithm_id"])
            )
            path = f"codes/{identifier}{EXTENSIONS[values['language']]}"
            timestamp = now()
            with self.db:
                self.db.execute("""UPDATE problems SET platform=?,number=?,name=?,url=?,normalized_url=?,language=?,
                    contest_id=?,algorithm_id=?,algorithm_order=?,code_path=?,updated_at=?,version=version+1 WHERE id=?""",
                    (values["platform"], values["number"], values["name"], values["url"], values["normalized_url"],
                     values["language"], values["contest_id"], values["algorithm_id"], algorithm_order,
                     path, timestamp, identifier))
                if encoded != old["code"].encode("utf-8") or path != old["code_path"]:
                    self.db.execute("INSERT INTO pending_files(action,path,content) VALUES ('write',?,?)", (path, encoded))
                if path != old["code_path"]:
                    self.db.execute("INSERT INTO pending_files(action,path,content) VALUES ('delete',?,NULL)", (old["code_path"],))
                self._touch_contests([old["contest_id"], values["contest_id"]], timestamp)
                self._touch_algorithm(old["algorithm_id"], timestamp)
                self._touch_algorithm(values["algorithm_id"], timestamp)
            self._flush_pending()
            return self._problem(identifier)

    def reorder_algorithm_problems(self, identifier, payload):
        with self.lock:
            self._ready()
            old = self._algorithm(identifier)
            self._version(old, payload)
            problem_ids = payload.get("problem_ids")
            if not isinstance(problem_ids, list) or not all(
                isinstance(item, str) for item in problem_ids
            ):
                raise AppError("题目顺序格式不正确")
            if len(problem_ids) != len(set(problem_ids)):
                raise AppError("题目顺序中不能包含重复题目")
            current_ids = [
                row[0]
                for row in self.db.execute(
                    "SELECT id FROM problems WHERE algorithm_id=?",
                    (identifier,),
                )
            ]
            if set(problem_ids) != set(current_ids):
                raise AppError(
                    "题目列表已发生变化，请刷新页面后重新调整顺序。",
                    409,
                    "problem_set_changed",
                )
            timestamp = now()
            with self.db:
                self.db.executemany(
                    "UPDATE problems SET algorithm_order=? "
                    "WHERE id=? AND algorithm_id=?",
                    [
                        (order, problem_id, identifier)
                        for order, problem_id in enumerate(problem_ids)
                    ],
                )
                self.db.execute(
                    "UPDATE algorithms SET updated_at=?,version=version+1 "
                    "WHERE id=?",
                    (timestamp, identifier),
                )
            return self._algorithm(identifier)

    def reorder_problems(self, payload):
        with self.lock:
            self._ready()
            current_version = int(
                self.db.execute(
                    "SELECT value FROM settings WHERE key='problem_order_version'"
                ).fetchone()[0]
            )
            if payload.get("version") != current_version:
                raise AppError(
                    "题目列表已发生变化，请刷新页面后重新调整顺序。",
                    409,
                    "version_conflict",
                )
            problem_ids = payload.get("problem_ids")
            if not isinstance(problem_ids, list) or not all(
                isinstance(item, str) for item in problem_ids
            ):
                raise AppError("题目顺序格式不正确")
            if len(problem_ids) != len(set(problem_ids)):
                raise AppError("题目顺序中不能包含重复题目")
            current_ids = [
                row[0] for row in self.db.execute("SELECT id FROM problems")
            ]
            if set(problem_ids) != set(current_ids):
                raise AppError(
                    "题目列表已发生变化，请刷新页面后重新调整顺序。",
                    409,
                    "problem_set_changed",
                )
            next_version = current_version + 1
            with self.db:
                self.db.executemany(
                    "UPDATE problems SET global_order=? WHERE id=?",
                    [
                        (order, problem_id)
                        for order, problem_id in enumerate(problem_ids)
                    ],
                )
                self.db.execute(
                    "UPDATE settings SET value=? "
                    "WHERE key='problem_order_version'",
                    (str(next_version),),
                )
            return {
                "problem_order_version": next_version,
                "problem_ids": problem_ids,
            }

    def import_problems(self, payload):
        with self.lock:
            self._ready()
            items = payload.get("problems")
            if not isinstance(items, list) or not items:
                raise AppError("导入文件必须包含至少一道题目")
            if len(items) > 200:
                raise AppError(
                    "单次最多导入 200 道题目",
                    413,
                    "too_large",
                )
            prepared = []
            seen = set()
            algorithm_counters = {}
            global_start = self._next_problem_global_order()
            for index, raw_item in enumerate(items):
                if not isinstance(raw_item, dict):
                    raise AppError(f"第 {index + 1} 道题目格式不正确")
                item = dict(raw_item)
                contest_name = item.pop("contest", item.pop("contest_title", None))
                algorithm_name = item.pop(
                    "algorithm", item.pop("algorithm_name", None)
                )
                contest = None
                contest_id = item.get("contest_id")
                if contest_id is not None and contest_id != "":
                    if not isinstance(contest_id, str):
                        raise AppError(
                            f"第 {index + 1} 道题目的 contest_id 不正确"
                        )
                    contest = self._row("contests", contest_id)
                elif contest_name is not None and contest_name != "":
                    title = text_value(contest_name, "比赛标题", 300, True)
                    matches = self.db.execute(
                        "SELECT * FROM contests WHERE title=? COLLATE NOCASE",
                        (title,),
                    ).fetchall()
                    if not matches:
                        raise AppError(
                            f"第 {index + 1} 道题目引用的比赛不存在：{title}"
                        )
                    if len(matches) > 1:
                        raise AppError(
                            f"第 {index + 1} 道题目的比赛标题不唯一，请改用 contest_id"
                        )
                    contest = dict(matches[0])
                if contest is not None:
                    item["contest_id"] = contest["id"]
                    if not item.get("platform"):
                        item["platform"] = contest["platform"]

                algorithm_id = item.get("algorithm_id")
                if algorithm_id is not None and algorithm_id != "":
                    if not isinstance(algorithm_id, str):
                        raise AppError(
                            f"第 {index + 1} 道题目的 algorithm_id 不正确"
                        )
                    self._row("algorithms", algorithm_id)
                elif algorithm_name is not None and algorithm_name != "":
                    name = text_value(algorithm_name, "算法名称", 200, True)
                    matches = self.db.execute(
                        "SELECT * FROM algorithms WHERE name=? COLLATE NOCASE",
                        (name,),
                    ).fetchall()
                    if not matches:
                        raise AppError(
                            f"第 {index + 1} 道题目引用的算法不存在：{name}"
                        )
                    if len(matches) > 1:
                        raise AppError(
                            f"第 {index + 1} 道题目的算法名称不唯一，请改用 algorithm_id"
                        )
                    item["algorithm_id"] = matches[0]["id"]

                item.setdefault("language", "cpp")
                item.setdefault("code", "")
                try:
                    values, encoded = self._validate_problem(item)
                    self._duplicate(values)
                except AppError as exc:
                    raise AppError(
                        f"第 {index + 1} 道题目：{exc}",
                        exc.status,
                        exc.code,
                        **exc.details,
                    ) from None
                key = (values["platform"], values["normalized_url"])
                if key in seen:
                    raise AppError(
                        f"第 {index + 1} 道题目与导入文件中的其他题目重复"
                    )
                seen.add(key)
                algorithm_id = values["algorithm_id"]
                if algorithm_id is None:
                    algorithm_order = 0
                else:
                    if algorithm_id not in algorithm_counters:
                        algorithm_counters[algorithm_id] = (
                            self._next_algorithm_order(algorithm_id)
                        )
                    algorithm_order = algorithm_counters[algorithm_id]
                    algorithm_counters[algorithm_id] += 1
                prepared.append(
                    {
                        "values": values,
                        "encoded": encoded,
                        "algorithm_order": algorithm_order,
                    }
                )

            current_version = int(
                self.db.execute(
                    "SELECT value FROM settings WHERE key='problem_order_version'"
                ).fetchone()[0]
            )
            next_version = current_version + 1
            timestamp = now()
            identifiers = []
            with self.db:
                for offset, prepared_item in enumerate(prepared):
                    values = prepared_item["values"]
                    identifier = uuid.uuid4().hex
                    path = (
                        f"codes/{identifier}"
                        f"{EXTENSIONS[values['language']]}"
                    )
                    identifiers.append(identifier)
                    self.db.execute(
                        "INSERT INTO problems "
                        "(id,platform,number,name,url,normalized_url,language,"
                        "contest_id,algorithm_id,algorithm_order,global_order,"
                        "code_path,created_at,updated_at,version) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
                        (
                            identifier,
                            values["platform"],
                            values["number"],
                            values["name"],
                            values["url"],
                            values["normalized_url"],
                            values["language"],
                            values["contest_id"],
                            values["algorithm_id"],
                            prepared_item["algorithm_order"],
                            global_start + offset,
                            path,
                            timestamp,
                            timestamp,
                        ),
                    )
                    self.db.execute(
                        "INSERT INTO pending_files(action,path,content) "
                        "VALUES ('write',?,?)",
                        (path, prepared_item["encoded"]),
                    )
                contest_ids = {
                    item["values"]["contest_id"] for item in prepared
                } - {None}
                algorithm_ids = {
                    item["values"]["algorithm_id"] for item in prepared
                } - {None}
                self._touch_contests(contest_ids, timestamp)
                for algorithm_id in algorithm_ids:
                    self._touch_algorithm(algorithm_id, timestamp)
                self.db.execute(
                    "UPDATE settings SET value=? "
                    "WHERE key='problem_order_version'",
                    (str(next_version),),
                )
            self._flush_pending()
            return {
                "count": len(identifiers),
                "problem_ids": identifiers,
                "problem_order_version": next_version,
            }

    def delete_problem(self, identifier, payload):
        with self.lock:
            self._ready()
            old = self._row("problems", identifier)
            self._version(old, payload)
            if payload.get("confirmed") is not True:
                raise AppError("删除题目会同时删除代码文件，请再次确认", 400, "confirmation_required")
            with self.db:
                self.db.execute("DELETE FROM problems WHERE id=?", (identifier,))
                self.db.execute("INSERT INTO pending_files(action,path,content) VALUES ('delete',?,NULL)", (old["code_path"],))
                self._touch_contests([old["contest_id"]], now())
                self._touch_algorithm(old["algorithm_id"], now())
            self._flush_pending()
            return {"ok": True}

    def delete_contest(self, identifier, payload):
        with self.lock:
            self._ready()
            old = self._row("contests", identifier)
            self._version(old, payload)
            if payload.get("confirmed") is not True or type(payload.get("keep_problems")) is not bool:
                raise AppError("请确认删除比赛，并选择是否保留题目和代码", 400, "confirmation_required")
            with self.db:
                if payload["keep_problems"]:
                    self.db.execute("UPDATE problems SET contest_id=NULL,updated_at=?,version=version+1 WHERE contest_id=?", (now(), identifier))
                else:
                    rows = self.db.execute(
                        "SELECT code_path,algorithm_id FROM problems WHERE contest_id=?",
                        (identifier,),
                    ).fetchall()
                    self.db.executemany("INSERT INTO pending_files(action,path,content) VALUES ('delete',?,NULL)", [(r[0],) for r in rows])
                    self.db.execute("DELETE FROM problems WHERE contest_id=?", (identifier,))
                    timestamp = now()
                    for algorithm_id in {r[1] for r in rows} - {None}:
                        self._touch_algorithm(algorithm_id, timestamp)
                self.db.execute("DELETE FROM contests WHERE id=?", (identifier,))
            self._flush_pending()
            return {"ok": True, "kept_problems": payload["keep_problems"]}

    def create_algorithm(self, payload):
        with self.lock:
            self._ready()
            values, links = self._validate_algorithm(payload)
            identifier, timestamp = uuid.uuid4().hex, now()
            with self.db:
                self.db.execute(
                    "INSERT INTO algorithms "
                    "(id,name,category,description,created_at,updated_at,version) "
                    "VALUES (?,?,?,?,?,?,1)",
                    (
                        identifier,
                        values["name"],
                        values["category"],
                        values["description"],
                        timestamp,
                        timestamp,
                    ),
                )
                self._replace_algorithm_links(identifier, links)
            return self._algorithm(identifier)

    def update_algorithm(self, identifier, payload):
        with self.lock:
            self._ready()
            old = self._algorithm(identifier)
            self._version(old, payload)
            values, links = self._validate_algorithm({**old, **payload})
            with self.db:
                self.db.execute(
                    "UPDATE algorithms SET name=?,category=?,description=?,"
                    "updated_at=?,version=version+1 WHERE id=?",
                    (
                        values["name"],
                        values["category"],
                        values["description"],
                        now(),
                        identifier,
                    ),
                )
                self._replace_algorithm_links(identifier, links)
            return self._algorithm(identifier)

    def delete_algorithm(self, identifier, payload):
        with self.lock:
            self._ready()
            old = self._row("algorithms", identifier)
            self._version(old, payload)
            if payload.get("confirmed") is not True:
                raise AppError(
                    "删除算法会同时删除全部代码文件，请再次确认",
                    400,
                    "confirmation_required",
                )
            snippets = self._algorithm_snippets(identifier)
            with self.db:
                self.db.execute(
                    "UPDATE problems SET algorithm_id=NULL,updated_at=?,version=version+1 "
                    "WHERE algorithm_id=?",
                    (now(), identifier),
                )
                self.db.executemany(
                    "INSERT INTO pending_files(action,path,content) "
                    "VALUES ('delete',?,NULL)",
                    [(item["code_path"],) for item in snippets],
                )
                self.db.execute("DELETE FROM algorithms WHERE id=?", (identifier,))
            self._flush_pending()
            return {"ok": True, "deleted_snippets": len(snippets)}

    def create_snippet(self, algorithm_id, payload):
        with self.lock:
            self._ready()
            algorithm = self._row("algorithms", algorithm_id)
            count = self.db.execute(
                "SELECT COUNT(*) FROM algorithm_snippets WHERE algorithm_id=?",
                (algorithm_id,),
            ).fetchone()[0]
            if count >= 100:
                raise AppError("单个算法最多保存 100 份代码", 413, "too_large")
            values, encoded, _ = self._validate_snippet(payload)
            identifier, timestamp = uuid.uuid4().hex, now()
            path = f"codes/{identifier}{EXTENSIONS[values['language']]}"
            with self.db:
                self.db.execute(
                    "INSERT INTO algorithm_snippets "
                    "(id,algorithm_id,title,language,code_path,created_at,updated_at,version) "
                    "VALUES (?,?,?,?,?,?,?,1)",
                    (
                        identifier,
                        algorithm_id,
                        values["title"],
                        values["language"],
                        path,
                        timestamp,
                        timestamp,
                    ),
                )
                self.db.execute(
                    "INSERT INTO pending_files(action,path,content) VALUES ('write',?,?)",
                    (path, encoded),
                )
                self._touch_algorithm(algorithm_id, timestamp)
            self._flush_pending()
            return self._snippet(identifier)

    def update_snippet(self, identifier, payload):
        with self.lock:
            self._ready()
            old = self._snippet(identifier)
            self._version(old, payload)
            values, encoded, _ = self._validate_snippet({**old, **payload})
            path = f"codes/{identifier}{EXTENSIONS[values['language']]}"
            timestamp = now()
            with self.db:
                self.db.execute(
                    "UPDATE algorithm_snippets SET title=?,language=?,code_path=?,"
                    "updated_at=?,version=version+1 WHERE id=?",
                    (
                        values["title"],
                        values["language"],
                        path,
                        timestamp,
                        identifier,
                    ),
                )
                if encoded != old["code"].encode("utf-8") or path != old["code_path"]:
                    self.db.execute(
                        "INSERT INTO pending_files(action,path,content) VALUES ('write',?,?)",
                        (path, encoded),
                    )
                if path != old["code_path"]:
                    self.db.execute(
                        "INSERT INTO pending_files(action,path,content) "
                        "VALUES ('delete',?,NULL)",
                        (old["code_path"],),
                    )
                self._touch_algorithm(old["algorithm_id"], timestamp)
            self._flush_pending()
            return self._snippet(identifier)

    def delete_snippet(self, identifier, payload):
        with self.lock:
            self._ready()
            old = self._snippet(identifier)
            self._version(old, payload)
            if payload.get("confirmed") is not True:
                raise AppError(
                    "删除代码模板会同时删除源码文件，请再次确认",
                    400,
                    "confirmation_required",
                )
            timestamp = now()
            with self.db:
                self.db.execute(
                    "DELETE FROM algorithm_snippets WHERE id=?", (identifier,)
                )
                self.db.execute(
                    "INSERT INTO pending_files(action,path,content) "
                    "VALUES ('delete',?,NULL)",
                    (old["code_path"],),
                )
                self._touch_algorithm(old["algorithm_id"], timestamp)
            self._flush_pending()
            return {"ok": True}


class LocalServer(ThreadingHTTPServer):
    # Wait for an in-flight atomic save before closing the SQLite connection.
    daemon_threads = False

    def __init__(self, address, repo, web_dir=ROOT / "web"):
        self.repo = repo
        self.web_dir = Path(web_dir).resolve()
        self.csrf_token = secrets.token_urlsafe(32)
        self.user_name = getpass.getuser()
        self.project_id = hashlib.sha256(str(repo.data_dir).encode("utf-8")).hexdigest()
        super().__init__(address, RequestHandler)


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "AlgoArchive/1.5"
    sys_version = ""

    def _headers(self, status, content_type, length):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Connection", "close")
        self.end_headers()

    def _json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(data))
        if self.command != "HEAD":
            self.wfile.write(data)

    def _guard(self, mutation=False):
        port = self.server.server_address[1]
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host", "").lower() not in allowed_hosts:
            raise AppError("仅允许通过本机地址访问", 403, "forbidden_host")
        origin = self.headers.get("Origin")
        allowed_origins = {f"http://{host}" for host in allowed_hosts}
        if origin is not None and origin not in allowed_origins:
            raise AppError("不允许跨站请求", 403, "forbidden_origin")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise AppError("不允许跨站请求", 403, "forbidden_origin")
        if mutation and not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), self.server.csrf_token):
            raise AppError("页面会话已失效，请刷新页面后重试。未保存的代码请先复制保留。", 403, "csrf_invalid")

    def _body(self):
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise AppError("请求必须使用 JSON", 415, "invalid_content_type")
        if self.headers.get("Transfer-Encoding"):
            raise AppError("不支持此请求编码", 400, "invalid_request")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise AppError("请求长度无效") from None
        if length < 0 or length > MAX_BODY_BYTES:
            raise AppError("请求内容过大", 413, "too_large")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeError):
            raise AppError("JSON 格式不正确") from None
        if not isinstance(data, dict):
            raise AppError("请求内容必须是对象")
        return data

    def _dispatch(self):
        mutation = self.command in {"POST", "PUT", "DELETE"}
        self._guard(mutation)
        path = urlsplit(self.path).path
        repo = self.server.repo
        if self.command in {"GET", "HEAD"}:
            if path == "/api/health":
                return self._json({"app": "AlgoArchive", "version": APP_VERSION, "project_id": self.server.project_id})
            if path == "/api/state":
                return self._json(repo.state())
            if path == "/api/profile/avatar":
                data, content_type = repo.read_avatar()
                self._headers(200, content_type, len(data))
                if self.command != "HEAD":
                    self.wfile.write(data)
                return
            match = re.fullmatch(
                r"/api/(problems|contests|algorithms|algorithm-snippets)/([a-f0-9]{32})",
                path,
            )
            if match:
                if match[1] == "problems":
                    return self._json({"problem": repo.get_problem(match[2])})
                if match[1] == "contests":
                    return self._json({"contest": repo.get_contest(match[2])})
                if match[1] == "algorithms":
                    return self._json({"algorithm": repo.get_algorithm(match[2])})
                return self._json({"snippet": repo.get_snippet(match[2])})
            if path.startswith("/api/"):
                raise AppError("接口不存在", 404, "not_found")
            relative = "index.html" if path in {"", "/"} else unquote(path.lstrip("/"))
            target = (self.server.web_dir / relative).resolve()
            if not target.is_relative_to(self.server.web_dir) or not target.is_file():
                raise AppError("页面不存在", 404, "not_found")
            data = target.read_bytes()
            if target.name == "index.html":
                data = data.replace(b"__CSRF_TOKEN__", self.server.csrf_token.encode("ascii"))
                data = data.replace(
                    b"__USER_NAME__",
                    html.escape(self.server.user_name, quote=True).encode("utf-8"),
                )
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if target.suffix == ".js":
                ctype = "application/javascript"
            if ctype.startswith("text/") or ctype in {"application/javascript", "application/json"}:
                ctype += "; charset=utf-8"
            self._headers(200, ctype, len(data))
            if self.command != "HEAD":
                self.wfile.write(data)
            return
        body = self._body()
        if self.command == "PUT" and path == "/api/profile":
            return self._json({"profile": repo.update_profile(body)})
        if self.command == "POST" and path == "/api/contests":
            return self._json({"contest": repo.create_contest(body)}, 201)
        if self.command == "POST" and path == "/api/problems":
            return self._json({"problem": repo.create_problem(body)}, 201)
        if self.command == "POST" and path == "/api/problems/import":
            return self._json(repo.import_problems(body), 201)
        if self.command == "PUT" and path == "/api/problems/order":
            return self._json(repo.reorder_problems(body))
        match = re.fullmatch(
            r"/api/algorithms/([a-f0-9]{32})/problems/order", path
        )
        if self.command == "PUT" and match:
            return self._json(
                {
                    "algorithm": repo.reorder_algorithm_problems(
                        match[1], body
                    )
                }
            )
        match = re.fullmatch(
            r"/api/(algorithms)/([a-f0-9]{32})/snippets", path
        )
        if self.command == "POST" and match:
            return self._json(
                {"snippet": repo.create_snippet(match[2], body)}, 201
            )
        if self.command == "POST" and path == "/api/algorithms":
            return self._json({"algorithm": repo.create_algorithm(body)}, 201)
        match = re.fullmatch(
            r"/api/(problems|contests|algorithms|algorithm-snippets)/([a-f0-9]{32})",
            path,
        )
        if match:
            kind, identifier = match.groups()
            if self.command == "PUT":
                methods = {
                    "problems": (repo.update_problem, "problem"),
                    "contests": (repo.update_contest, "contest"),
                    "algorithms": (repo.update_algorithm, "algorithm"),
                    "algorithm-snippets": (repo.update_snippet, "snippet"),
                }
                method, response_key = methods[kind]
                return self._json({response_key: method(identifier, body)})
            if self.command == "DELETE":
                methods = {
                    "problems": repo.delete_problem,
                    "contests": repo.delete_contest,
                    "algorithms": repo.delete_algorithm,
                    "algorithm-snippets": repo.delete_snippet,
                }
                method = methods[kind]
                return self._json(method(identifier, body))
        raise AppError("接口不存在", 404, "not_found")

    def _handle(self):
        self.connection.settimeout(20)
        try:
            self._dispatch()
        except AppError as exc:
            self._json(exc.payload(), exc.status)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        except Exception as exc:
            # Error details stay in the local terminal, never expose paths in HTTP.
            print(f"[{now()}] {type(exc).__name__}: {exc}", file=sys.stderr)
            self._json({"error": "本地服务发生错误，请查看启动窗口。数据目录请保留。", "code": "internal_error"}, 500)

    do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = _handle

    def do_OPTIONS(self):
        self._json({"error": "不允许跨站请求", "code": "forbidden_origin"}, 403)

    def log_message(self, fmt, *args):
        # Standard console logging contains request routes, never request bodies.
        super().log_message(fmt, *args)


def create_app(data_dir=None, port=0, web_dir=None):
    """Return a bound server for integration tests or embedding."""
    repo = Repository(data_dir or default_data_dir())
    try:
        return LocalServer(("127.0.0.1", port), repo, web_dir or ROOT / "web")
    except Exception:
        repo.close()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="AlgoArchive 本地算法档案管理")
    parser.add_argument("--data-dir")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port 必须介于 0 和 65535")
    explicit_data_dir = args.data_dir is not None
    data_dir = (
        Path(args.data_dir).resolve()
        if explicit_data_dir
        else default_data_dir().resolve()
    )
    args.data_dir = str(data_dir)
    if not explicit_data_dir:
        migrated = migrate_legacy_data(ROOT / "data", data_dir)
        if migrated is not None:
            print(f"旧数据已迁移并归档到: {migrated}", flush=True)
    directory_lock = DataDirectoryLock(data_dir)
    if not directory_lock.acquired:
        # The first launch may still be starting. Only trust a matching health
        # identity, and never open a browser based on arbitrary lock-file text.
        project_id = hashlib.sha256(str(data_dir).encode("utf-8")).hexdigest()
        for _ in range(15):
            port = directory_lock.read_port()
            if type(port) is int and 0 < port <= 65535:
                try:
                    with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.4) as response:
                        health = json.load(response)
                    if health.get("app") == "AlgoArchive" and health.get("project_id") == project_id:
                        address = f"http://127.0.0.1:{port}"
                        print(f"程序已在运行: {address}", flush=True)
                        if not args.no_browser:
                            open_browser(address)
                        return 0
                except Exception:
                    pass
            time.sleep(0.15)
        raise AppError("此数据目录已有程序在运行或正在启动，请查看原来的启动窗口。", 409, "already_running")
    try:
        return _run_server(args, directory_lock)
    finally:
        directory_lock.close()


def _run_server(args, directory_lock):
    repo = Repository(args.data_dir, acquire_lock=False)
    server = None
    candidates = [0] if args.port == 0 else list(range(args.port, min(args.port + 20, 65536))) + [0]
    for port in candidates:
        try:
            server = LocalServer(("127.0.0.1", port), repo)
            break
        except OSError:
            continue
    if server is None:
        repo.close()
        raise RuntimeError("无法建立本地服务，请检查系统端口设置")
    address = f"http://127.0.0.1:{server.server_address[1]}"
    directory_lock.set_port(server.server_address[1])
    print(f"AlgoArchive {APP_VERSION}\n本地地址: {address}\n数据目录: {repo.data_dir}\n关闭此窗口或按 Ctrl+C 停止服务。", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: open_browser(address)).start()
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\n正在关闭本地服务…", flush=True)
    finally:
        server.server_close()
        repo.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AppError, OSError, sqlite3.Error) as error:
        print(f"启动失败: {error}", file=sys.stderr)
        raise SystemExit(1)
