#!/usr/bin/env python3
"""AlgoArchive: an offline contest archive, using only Python's standard library."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote
from urllib.request import urlopen
import uuid
import webbrowser


APP_VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent
PLATFORMS = {"codeforces", "atcoder"}
EXTENSIONS = {"cpp": ".cpp", "python": ".py", "java": ".java", "other": ".txt"}
MAX_CODE_BYTES = 2 * 1024 * 1024
MAX_BODY_BYTES = 4 * 1024 * 1024


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


def platform_value(value):
    if not isinstance(value, str) or value not in PLATFORMS:
        raise AppError("请选择 Codeforces 或 AtCoder")
    return value


def normalize_url(platform, value, kind="problem"):
    """Normalize official problem URLs, including the CF problemset alias."""
    platform_value(platform)
    value = text_value(value, "链接", 2048, True)
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme.lower() not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError()
        if parsed.port not in {None, 80, 443}:
            raise ValueError()
    except ValueError:
        raise AppError("请填写有效的 http/https 官方平台链接") from None
    path = unquote(parsed.path).rstrip("/")
    if platform == "codeforces":
        if host not in {"codeforces.com", "www.codeforces.com"}:
            raise AppError("Codeforces 链接必须来自 codeforces.com")
        if kind == "contest":
            match = re.fullmatch(r"/(contest|gym)/(\d+)", path, re.I)
            if match:
                return f"https://codeforces.com/{match[1].lower()}/{int(match[2])}"
        else:
            match = re.fullmatch(r"/(contest|gym)/(\d+)/problem/([A-Za-z][A-Za-z0-9]*)", path, re.I)
            if match:
                return f"https://codeforces.com/{match[1].lower()}/{int(match[2])}/problem/{match[3].upper()}"
            match = re.fullmatch(r"/problemset/problem/(\d+)/([A-Za-z][A-Za-z0-9]*)", path, re.I)
            if match:
                return f"https://codeforces.com/contest/{int(match[1])}/problem/{match[2].upper()}"
    else:
        if host not in {"atcoder.jp", "www.atcoder.jp"}:
            raise AppError("AtCoder 链接必须来自 atcoder.jp")
        if kind == "contest":
            match = re.fullmatch(r"/contests/([a-zA-Z0-9_-]+)", path)
            if match:
                return f"https://atcoder.jp/contests/{match[1].lower()}"
        else:
            match = re.fullmatch(r"/contests/([a-zA-Z0-9_-]+)/tasks/([a-zA-Z0-9_-]+)", path)
            if match:
                return f"https://atcoder.jp/contests/{match[1].lower()}/tasks/{match[2].lower()}"
    label = "比赛" if kind == "contest" else "题目"
    raise AppError(f"链接格式不正确，请复制官方{label}页面的完整链接")


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
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(self.data_dir / "archive.sqlite3"), check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT OR IGNORE INTO settings VALUES ('schema_version', '1');
            CREATE TABLE IF NOT EXISTS contests (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL CHECK(platform IN ('codeforces','atcoder')),
                title TEXT NOT NULL, url TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS problems (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL CHECK(platform IN ('codeforces','atcoder')),
                number TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL, normalized_url TEXT NOT NULL,
                language TEXT NOT NULL CHECK(language IN ('cpp','python','java','other')),
                contest_id TEXT REFERENCES contests(id) ON DELETE SET NULL,
                code_path TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                UNIQUE(platform, normalized_url)
            );
            CREATE INDEX IF NOT EXISTS problems_contest ON problems(contest_id);
            CREATE INDEX IF NOT EXISTS problems_updated ON problems(updated_at DESC);
            CREATE TABLE IF NOT EXISTS pending_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL CHECK(action IN ('write','delete')),
                path TEXT NOT NULL,
                content BLOB
            );
        """)
        if self.db.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0] != "1":
            raise AppError("数据库版本不兼容，请使用较新版本程序", 500, "schema_version")
        self._flush_pending()

    def close(self):
        with self.lock:
            self.db.close()
            if self.process_lock:
                self.process_lock.close()

    def _path(self, relative):
        # Never use user-supplied paths, even when a database was manually edited.
        if not re.fullmatch(r"codes/[a-f0-9]{32}\.(cpp|py|java|txt)", relative):
            raise AppError("代码文件路径不合法，请恢复完整备份", 500, "storage_error")
        path = self.data_dir / relative
        if not path.resolve().is_relative_to(self.data_dir):
            raise AppError("代码文件路径超出数据目录", 500, "storage_error")
        return path

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
        if with_code:
            try:
                row["code"] = self._path(row["code_path"]).read_bytes().decode("utf-8")
            except (OSError, UnicodeError) as exc:
                raise AppError("代码文件缺失或无法读取，请检查 data/codes 或恢复备份。原记录已保留。", 500, "code_unavailable") from exc
        return row

    def _touch_contests(self, ids, timestamp):
        for identifier in set(ids) - {None}:
            self.db.execute("UPDATE contests SET updated_at=?,version=version+1 WHERE id=?", (timestamp, identifier))

    def _validate_problem(self, payload):
        platform = platform_value(payload.get("platform"))
        number = text_value(payload.get("number", ""), "题目编号", 50)
        name = text_value(payload.get("name", ""), "题目名称", 300)
        if not number and not name:
            raise AppError("请至少填写题目编号或名称")
        url = normalize_url(platform, payload.get("url"))
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
            if contest["platform"] != platform:
                raise AppError("题目与所属比赛必须来自同一平台")
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
                    language=language, contest_id=contest_id), encoded

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
            problems = [dict(r) for r in self.db.execute("""SELECT p.*, c.title AS contest_title
                FROM problems p LEFT JOIN contests c ON p.contest_id=c.id
                ORDER BY p.updated_at DESC,p.id""")]
            return {"contests": contests, "problems": problems, "stats": {
                "contest_count": len(contests), "problem_count": len(problems),
                "codeforces_count": sum(p["platform"] == "codeforces" for p in problems),
                "atcoder_count": sum(p["platform"] == "atcoder" for p in problems)}}

    def get_problem(self, identifier):
        with self.lock:
            self._ready()
            return self._problem(identifier)

    def get_contest(self, identifier):
        with self.lock:
            self._ready()
            return self._contest(identifier)

    def create_contest(self, payload):
        with self.lock:
            self._ready()
            platform = platform_value(payload.get("platform"))
            title = text_value(payload.get("title"), "比赛标题", 300, True)
            url = normalize_url(platform, payload.get("url"), "contest")
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
            platform = platform_value(values.get("platform"))
            title = text_value(values.get("title"), "比赛标题", 300, True)
            url = normalize_url(platform, values.get("url"), "contest")
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
            path = f"codes/{identifier}{EXTENSIONS[values['language']]}"
            with self.db:
                self.db.execute("""INSERT INTO problems
                    (id,platform,number,name,url,normalized_url,language,contest_id,code_path,created_at,updated_at,version)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,1)""", (identifier, values["platform"], values["number"], values["name"],
                    values["url"], values["normalized_url"], values["language"], values["contest_id"], path, timestamp, timestamp))
                self.db.execute("INSERT INTO pending_files(action,path,content) VALUES ('write',?,?)", (path, encoded))
                self._touch_contests([values["contest_id"]], timestamp)
            self._flush_pending()
            return self._problem(identifier)

    def update_problem(self, identifier, payload):
        with self.lock:
            self._ready()
            old = self._problem(identifier)
            self._version(old, payload)
            values, encoded = self._validate_problem({**old, **payload})
            self._duplicate(values, identifier)
            path = f"codes/{identifier}{EXTENSIONS[values['language']]}"
            timestamp = now()
            with self.db:
                self.db.execute("""UPDATE problems SET platform=?,number=?,name=?,url=?,normalized_url=?,language=?,
                    contest_id=?,code_path=?,updated_at=?,version=version+1 WHERE id=?""",
                    (values["platform"], values["number"], values["name"], values["url"], values["normalized_url"],
                     values["language"], values["contest_id"], path, timestamp, identifier))
                if encoded != old["code"].encode("utf-8") or path != old["code_path"]:
                    self.db.execute("INSERT INTO pending_files(action,path,content) VALUES ('write',?,?)", (path, encoded))
                if path != old["code_path"]:
                    self.db.execute("INSERT INTO pending_files(action,path,content) VALUES ('delete',?,NULL)", (old["code_path"],))
                self._touch_contests([old["contest_id"], values["contest_id"]], timestamp)
            self._flush_pending()
            return self._problem(identifier)

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
                    rows = self.db.execute("SELECT code_path FROM problems WHERE contest_id=?", (identifier,)).fetchall()
                    self.db.executemany("INSERT INTO pending_files(action,path,content) VALUES ('delete',?,NULL)", [(r[0],) for r in rows])
                    self.db.execute("DELETE FROM problems WHERE contest_id=?", (identifier,))
                self.db.execute("DELETE FROM contests WHERE id=?", (identifier,))
            self._flush_pending()
            return {"ok": True, "kept_problems": payload["keep_problems"]}


class LocalServer(ThreadingHTTPServer):
    # Wait for an in-flight atomic save before closing the SQLite connection.
    daemon_threads = False

    def __init__(self, address, repo, web_dir=ROOT / "web"):
        self.repo = repo
        self.web_dir = Path(web_dir).resolve()
        self.csrf_token = secrets.token_urlsafe(32)
        self.project_id = hashlib.sha256(str(repo.data_dir).encode("utf-8")).hexdigest()
        super().__init__(address, RequestHandler)


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "AlgoArchive/1.0"
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
            match = re.fullmatch(r"/api/(problems|contests)/([a-f0-9]{32})", path)
            if match:
                if match[1] == "problems":
                    return self._json({"problem": repo.get_problem(match[2])})
                return self._json({"contest": repo.get_contest(match[2])})
            if path.startswith("/api/"):
                raise AppError("接口不存在", 404, "not_found")
            relative = "index.html" if path in {"", "/"} else unquote(path.lstrip("/"))
            target = (self.server.web_dir / relative).resolve()
            if not target.is_relative_to(self.server.web_dir) or not target.is_file():
                raise AppError("页面不存在", 404, "not_found")
            data = target.read_bytes()
            if target.name == "index.html":
                data = data.replace(b"__CSRF_TOKEN__", self.server.csrf_token.encode("ascii"))
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
        if self.command == "POST" and path == "/api/contests":
            return self._json({"contest": repo.create_contest(body)}, 201)
        if self.command == "POST" and path == "/api/problems":
            return self._json({"problem": repo.create_problem(body)}, 201)
        match = re.fullmatch(r"/api/(problems|contests)/([a-f0-9]{32})", path)
        if match:
            kind, identifier = match.groups()
            if self.command == "PUT":
                method = repo.update_problem if kind == "problems" else repo.update_contest
                return self._json({"problem" if kind == "problems" else "contest": method(identifier, body)})
            if self.command == "DELETE":
                method = repo.delete_problem if kind == "problems" else repo.delete_contest
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
    repo = Repository(data_dir or ROOT / "data")
    try:
        return LocalServer(("127.0.0.1", port), repo, web_dir or ROOT / "web")
    except Exception:
        repo.close()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="AlgoArchive 本地算法竞赛管理")
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port 必须介于 0 和 65535")
    data_dir = Path(args.data_dir).resolve()
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
                            webbrowser.open(address)
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
        threading.Timer(0.5, lambda: webbrowser.open(address)).start()
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
