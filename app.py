#!/usr/bin/env python3
"""AlgoArchive: an offline contest archive, using only Python's standard library."""
from __future__ import annotations

import argparse
import base64
import binascii
import codecs
from contextlib import closing
import getpass
import hashlib
import html
import json
import locale
import logging
from logging.handlers import RotatingFileHandler
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
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, urlunsplit, unquote
from urllib.request import urlopen
import uuid
import webbrowser

from cph_runner import (
    CPP_STANDARDS,
    CppTestRunner,
    DEFAULT_CPP_STANDARD,
    compiler_version,
    resolve_cpp_compiler,
    validate_test_cases,
)


APP_VERSION = "2.1.6"
ROOT = Path(__file__).resolve().parent
DATABASE_SCHEMA_VERSION = 8
SUPPORTED_DATABASE_VERSIONS = {1, 2, 3, 4, 5, 6, 7, 8}
PROBLEM_PLATFORM_ALIASES = {"codeforces": "codeforces", "atcoder": "atcoder"}
EXTENSIONS = {"cpp": ".cpp", "python": ".py", "java": ".java", "other": ".txt"}
SCHEMELESS_URL_PATTERN = re.compile(
    r"^(?=.{4,2048}$)"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"(?:[A-Za-z]{2,63}|xn--[A-Za-z0-9-]+)"
    r"(?::[0-9]{1,5})?(?:[/?#][^\s]*)?$"
)
FILE_LIKE_DOMAIN_SUFFIXES = frozenset(
    {
        "c",
        "cc",
        "cfg",
        "cpp",
        "css",
        "csv",
        "dll",
        "exe",
        "h",
        "hpp",
        "htm",
        "html",
        "ico",
        "ini",
        "java",
        "jpeg",
        "jpg",
        "js",
        "json",
        "jsx",
        "log",
        "md",
        "pdf",
        "png",
        "py",
        "rar",
        "svg",
        "toml",
        "ts",
        "tsx",
        "txt",
        "webp",
        "yaml",
        "yml",
        "zip",
        "7z",
    }
)
MAX_CODE_BYTES = 2 * 1024 * 1024
MAX_AVATAR_BYTES = 512 * 1024
MAX_BODY_BYTES = 4 * 1024 * 1024
MAX_BACKUP_UPLOAD_BYTES = 512 * 1024 * 1024
AVATAR_EXTENSIONS = {
    "png": (".png", "image/png"),
    "jpeg": (".jpg", "image/jpeg"),
    "webp": (".webp", "image/webp"),
}
AVATAR_PATH_PATTERN = r"avatar/avatar\.(png|jpg|webp)"
CPH_AUTHOR = "Divyanshu Agrawal"
CPH_REPOSITORY = "https://github.com/agrawal-d/cph"
CPH_LICENSE = "GPL-3.0-or-later"
CPH_REFERENCE_COMMIT = "ef8c7a70a7beff150bf5ed5e5ad8c631539a3fd6"


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
    if os.name == "nt":
        # Keep user data outside LocalAppData. Windows packaged applications can
        # redirect that location to different package-local copies.
        return Path.home() / "AlgoArchive" / "data"
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "algoarchive" / "data"


def default_config_path():
    """Return the per-user config path, independent from the selected data dir."""
    return Path.home() / "AlgoArchive" / "config.json"


def default_user_config():
    return {
        "format": 1,
        "data_dir": "",
        "browser": {
            "mode": "default",
            "custom_path": "",
            "window_mode": "tab",
        },
        "compiler": {
            "cpp_path": "",
            "cpp_standard": DEFAULT_CPP_STANDARD,
        },
    }


def _config_candidate_score(value):
    if not isinstance(value, dict):
        return 0
    configured = str(value.get("data_dir") or "").strip()
    if not configured:
        return 1
    try:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            return 0
        return 4 if path.exists() else 2
    except (OSError, ValueError):
        return 0


def _decode_user_config(raw):
    if raw.startswith(codecs.BOM_UTF8):
        encodings = ["utf-8-sig"]
    elif raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encodings = ["utf-16"]
    else:
        encodings = ["utf-8"]
        preferred = locale.getpreferredencoding(False)
        if preferred:
            encodings.append(preferred)
        if os.name == "nt":
            encodings.extend(["mbcs", "gb18030"])

    parsed = []
    failures = []
    seen = set()
    for index, encoding in enumerate(encodings):
        normalized = encoding.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            value = json.loads(raw.decode(encoding))
        except (LookupError, UnicodeError, ValueError) as exc:
            failures.append(f"{encoding}: {exc}")
            continue
        parsed.append((_config_candidate_score(value), -index, value))
    if not parsed:
        raise ValueError("; ".join(failures) or "无法确定配置文件编码")
    parsed.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return parsed[0][2]


def _normalized_user_config(value):
    if not isinstance(value, dict):
        raise AppError("用户配置文件必须是 JSON 对象", 500, "config_invalid")
    config = default_user_config()
    config.update(value)
    browser = default_user_config()["browser"]
    if isinstance(value.get("browser"), dict):
        browser.update(value["browser"])
    config["browser"] = browser
    compiler = default_user_config()["compiler"]
    if isinstance(value.get("compiler"), dict):
        compiler.update(value["compiler"])
    config["compiler"] = compiler
    return config


def load_user_config(path=None):
    path = Path(path or default_config_path()).resolve()
    if not path.exists():
        return default_user_config()
    try:
        value = _decode_user_config(path.read_bytes())
        return _normalized_user_config(value)
    except (OSError, UnicodeError, ValueError) as exc:
        raise AppError(
            f"用户配置文件无法读取或格式不正确：{path}",
            500,
            "config_invalid",
            config_path=str(path),
        ) from exc


def save_user_config(config, path=None):
    path = Path(path or default_config_path()).resolve()
    config = _normalized_user_config(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=".algoarchive-config-",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(config, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return path


def resolve_data_dir(cli_data_dir=None, config_path=None):
    if cli_data_dir:
        return Path(cli_data_dir).expanduser().resolve()
    config = load_user_config(config_path)
    configured = str(config.get("data_dir") or "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise AppError(
                "用户配置中的数据目录必须是绝对路径",
                500,
                "config_invalid",
            )
        return path.resolve()
    return default_data_dir().resolve()


def _sqlite_readonly_connection(database):
    return sqlite3.connect(
        f"{Path(database).resolve().as_uri()}?mode=ro",
        uri=True,
        timeout=5,
    )


def inspect_data_directory(path):
    """Classify a data directory without writing to its database."""
    path = Path(path).resolve()
    if not path.exists():
        return {"state": "empty", "path": str(path)}
    if not path.is_dir():
        return {"state": "incomplete", "path": str(path)}
    entries = list(path.iterdir())
    ignored_residuals = {"runtime.lock", "runtime.lock.pending"}
    if not entries or all(entry.name in ignored_residuals for entry in entries):
        return {"state": "residual", "path": str(path)}
    database = path / "archive.sqlite3"
    if not database.is_file() or database.stat().st_size == 0:
        return {"state": "incomplete", "path": str(path)}
    try:
        with closing(_sqlite_readonly_connection(database)) as db:
            integrity = db.execute("PRAGMA quick_check").fetchone()
            if not integrity or integrity[0] != "ok":
                return {"state": "corrupt", "path": str(path)}
            settings_table = db.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='settings'"
            ).fetchone()
            if not settings_table:
                return {"state": "incomplete", "path": str(path)}
            row = db.execute(
                "SELECT value FROM settings WHERE key='schema_version'"
            ).fetchone()
            if not row:
                return {"state": "incomplete", "path": str(path)}
            try:
                schema_version = int(row[0])
            except (TypeError, ValueError):
                return {"state": "incomplete", "path": str(path)}
            if schema_version not in SUPPORTED_DATABASE_VERSIONS:
                return {
                    "state": "incompatible",
                    "path": str(path),
                    "schema_version": schema_version,
                }
            pending = set()
            if db.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='pending_files'"
            ).fetchone():
                pending = {
                    item[0]
                    for item in db.execute("SELECT path FROM pending_files")
                }
            code_paths = set()
            if db.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='problems'"
            ).fetchone():
                code_paths.update(
                    item[0] for item in db.execute("SELECT code_path FROM problems")
                )
            if db.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='algorithm_snippets'"
            ).fetchone():
                code_paths.update(
                    item[0]
                    for item in db.execute("SELECT code_path FROM algorithm_snippets")
                )
            for relative in code_paths:
                if relative in pending:
                    continue
                if not re.fullmatch(
                    r"codes/[a-f0-9]{32}\.(cpp|py|java|txt)",
                    relative,
                ) or not (path / relative).is_file():
                    return {
                        "state": "incomplete",
                        "path": str(path),
                        "missing_code": relative,
                    }
            counts = {}
            for table in ("contests", "problems", "algorithms"):
                if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone():
                    counts[table] = db.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
            return {
                "state": "valid",
                "path": str(path),
                "schema_version": schema_version,
                "counts": counts,
            }
    except (OSError, sqlite3.Error):
        return {"state": "corrupt", "path": str(path)}


def prepare_user_data_dir(target, legacy_candidates=()):
    """Validate target or migrate exactly one valid legacy directory."""
    target = Path(target).resolve()
    target_state = inspect_data_directory(target)
    if target_state["state"] == "valid":
        return target_state
    if target_state["state"] not in {"empty", "residual"}:
        messages = {
            "incomplete": "目标数据目录不完整，未写入或覆盖任何数据库。",
            "corrupt": "目标数据库损坏，请先恢复备份。",
            "incompatible": "目标数据库版本高于当前程序支持范围，未执行写入。",
        }
        raise AppError(
            messages.get(target_state["state"], "目标数据目录不可用。"),
            409,
            f"data_{target_state['state']}",
            path=str(target),
        )
    valid_legacy = []
    seen = set()
    for candidate in legacy_candidates:
        candidate = Path(candidate).resolve()
        if candidate == target or candidate in seen:
            continue
        seen.add(candidate)
        state = inspect_data_directory(candidate)
        if state["state"] == "valid":
            valid_legacy.append(state)
        elif state["state"] not in {"empty"}:
            print(
                f"忽略不可用于迁移的数据目录 {candidate}: {state['state']}",
                file=sys.stderr,
                flush=True,
            )
    if len(valid_legacy) > 1:
        raise AppError(
            "发现两份可用旧数据。请通过 --data-dir 明确选择要使用的数据目录。",
            409,
            "data_conflict",
            candidates=[item["path"] for item in valid_legacy],
        )
    if valid_legacy:
        migrate_legacy_data(valid_legacy[0]["path"], target)
    return inspect_data_directory(target)


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


def browser_candidates():
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    program_files_x86 = Path(
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    )
    local_app_data = Path(
        os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
    )
    return {
        "chrome": chrome_candidates(),
        "edge": list(
            dict.fromkeys(
                [
                    program_files_x86
                    / "Microsoft"
                    / "Edge"
                    / "Application"
                    / "msedge.exe",
                    program_files
                    / "Microsoft"
                    / "Edge"
                    / "Application"
                    / "msedge.exe",
                ]
            )
        ),
        "firefox": list(
            dict.fromkeys(
                [
                    program_files
                    / "Mozilla Firefox"
                    / "firefox.exe",
                    program_files_x86
                    / "Mozilla Firefox"
                    / "firefox.exe",
                    local_app_data
                    / "Mozilla Firefox"
                    / "firefox.exe",
                ]
            )
        ),
    }


def find_browser_executable(mode, custom_path=""):
    if mode == "custom":
        value = str(custom_path or "").strip()
        if not value:
            return None
        candidate = Path(value).expanduser()
        if not candidate.is_absolute() or not candidate.is_file():
            return None
        if os.name == "nt" and candidate.suffix.casefold() not in {".exe", ".com"}:
            return None
        return candidate.resolve()
    for candidate in browser_candidates().get(mode, []):
        if candidate.is_file():
            return candidate.resolve()
    return None


def find_chrome_executable():
    return find_browser_executable("chrome")


def _system_browser_fallback(url, reason=""):
    try:
        ok = bool(webbrowser.open(url))
    except Exception:
        ok = False
    message = (
        "已使用系统默认浏览器打开。"
        if ok
        else "无法启动浏览器，请复制本地地址后手动打开。"
    )
    if reason:
        message = f"{reason} {message}"
    return {
        "ok": ok,
        "browser": "system",
        "window_mode": "tab",
        "fallback": True,
        "message": message,
    }


def launch_browser(url, settings=None):
    """Launch a validated HTTP URL with an explicit argument array."""
    parsed = urlsplit(str(url))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AppError("只能打开 http 或 https 地址", 400, "invalid_url")
    settings = dict(settings or {})
    mode = str(settings.get("mode") or "default").casefold()
    window_mode = str(settings.get("window_mode") or "tab").casefold()
    if mode not in {"default", "edge", "chrome", "firefox", "custom"}:
        mode = "default"
    if window_mode not in {"tab", "app"}:
        window_mode = "tab"
    if mode == "default":
        try:
            ok = bool(webbrowser.open(url))
        except Exception:
            ok = False
        return {
            "ok": ok,
            "browser": "system",
            "window_mode": "tab",
            "fallback": False,
            "message": "已请求系统默认浏览器打开。" if ok else "系统默认浏览器启动失败。",
        }
    executable = find_browser_executable(
        mode,
        settings.get("custom_path", ""),
    )
    if executable is None:
        return _system_browser_fallback(url, "所选浏览器不可用。")
    effective_window_mode = window_mode
    note = ""
    if window_mode == "app" and mode in {"chrome", "edge"}:
        command = [str(executable), f"--app={url}"]
    else:
        command = [str(executable), url]
        if window_mode == "app":
            effective_window_mode = "tab"
            note = "所选浏览器不支持应用窗口模式，已回退为普通标签页。"
    try:
        subprocess.Popen(command, close_fds=True)
    except OSError:
        return _system_browser_fallback(url, f"{note}所选浏览器启动失败。".strip())
    return {
        "ok": True,
        "browser": mode,
        "window_mode": effective_window_mode,
        "fallback": False,
        "message": note or "浏览器已打开。",
    }


def open_browser(url, settings=None):
    """Backward-compatible boolean wrapper around launch_browser."""
    return launch_browser(url, settings)["ok"]


def _verify_migrated_data(path):
    state = inspect_data_directory(path)
    if state["state"] != "valid":
        raise AppError(
            "旧数据校验失败，未执行迁移。",
            500,
            "migration_failed",
            reason=state["state"],
        )
    return state


def migrate_legacy_data(legacy, target):
    """Copy legacy in-program data to the user directory, then archive it."""
    legacy = Path(legacy).resolve()
    target = Path(target).resolve()
    legacy_state = inspect_data_directory(legacy)
    target_state = inspect_data_directory(target)
    if legacy_state["state"] != "valid":
        return None
    if target_state["state"] == "valid":
        return None
    if target_state["state"] not in {"empty", "residual"}:
        raise AppError(
            "目标数据目录不完整，未执行迁移。",
            409,
            "data_incomplete",
            path=str(target),
        )

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
            for residual in ("runtime.lock", "runtime.lock.pending"):
                try:
                    (target / residual).unlink()
                except FileNotFoundError:
                    pass
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


def expand_schemeless_url(value):
    """Add HTTPS to a domain-only link without changing notes or file names."""
    if not SCHEMELESS_URL_PATTERN.fullmatch(value):
        return value
    candidate = f"https://{value}"
    try:
        parsed = urlsplit(candidate)
        if not parsed.hostname:
            return value
        parsed.port
    except ValueError:
        return value
    suffix = parsed.hostname.rsplit(".", 1)[-1].casefold()
    if suffix in FILE_LIKE_DOMAIN_SUFFIXES:
        return value
    return candidate


def normalize_external_url(value):
    """Validate a general reference URL and return a stable identity."""
    value = text_value(value, "链接", 2048, True)
    value = expand_schemeless_url(value)
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


def database_needs_upgrade(database):
    database = Path(database)
    if not database.is_file():
        return False
    try:
        with closing(_sqlite_readonly_connection(database)) as db:
            row = db.execute(
                "SELECT value FROM settings WHERE key='schema_version'"
            ).fetchone()
            if not row or int(row[0]) < DATABASE_SCHEMA_VERSION:
                return True
            problem = db.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type='table' AND name='problems'"
            ).fetchone()
            contest = db.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type='table' AND name='contests'"
            ).fetchone()
            if problem and "CHECK(platform IN" in (problem[0] or ""):
                return True
            if contest and "CHECK(platform IN" in (contest[0] or ""):
                return True
            columns = {
                item[1] for item in db.execute("PRAGMA table_info(problems)")
            }
            return "algorithm_order" not in columns or "global_order" not in columns
    except (sqlite3.Error, TypeError, ValueError):
        return False


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
        state = inspect_data_directory(self.data_dir)
        if state["state"] not in {"empty", "residual", "valid"}:
            if self.process_lock:
                self.process_lock.close()
            messages = {
                "incomplete": "数据目录不完整，已拒绝启动以避免覆盖现有文件。",
                "corrupt": "数据库完整性检查失败，已拒绝写入。请恢复备份。",
                "incompatible": "数据库版本高于当前程序支持范围，已拒绝写入。",
            }
            raise AppError(
                messages.get(state["state"], "数据目录不可用。"),
                500,
                (
                    "database_incompatible"
                    if state["state"] == "incompatible"
                    else f"data_{state['state']}"
                ),
                path=str(self.data_dir),
            )
        if state["state"] == "valid" and database_needs_upgrade(
            self.data_dir / "archive.sqlite3"
        ):
            self._backup_before_schema_upgrade()
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
            INSERT OR IGNORE INTO settings VALUES ('schema_version', '8');
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
            CREATE TABLE IF NOT EXISTS problem_tests (
                problem_id TEXT NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL,
                input TEXT NOT NULL DEFAULT '',
                output TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(problem_id, ordinal)
            );
            CREATE INDEX IF NOT EXISTS algorithms_updated ON algorithms(updated_at DESC);
            CREATE INDEX IF NOT EXISTS algorithm_snippets_algorithm
                ON algorithm_snippets(algorithm_id);
            CREATE INDEX IF NOT EXISTS algorithm_snippets_updated
                ON algorithm_snippets(updated_at DESC);
            CREATE INDEX IF NOT EXISTS algorithm_links_algorithm
                ON algorithm_links(algorithm_id);
            CREATE INDEX IF NOT EXISTS problem_tests_problem
                ON problem_tests(problem_id, ordinal);
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
        if schema_version not in {"1", "2", "3", "4", "5", "6", "7", "8"}:
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
        if int(schema_version) < 7 or order_added:
            self._initialize_algorithm_problem_orders()
        if int(schema_version) < 7 or global_order_added:
            self._initialize_problem_global_orders()
        if schema_version != "8":
            with self.db:
                self.db.execute(
                    "UPDATE settings SET value='8' WHERE key='schema_version'"
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

    def _backup_before_schema_upgrade(self):
        backup_root = self.data_dir.parent / "backups"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = backup_root / f"before-schema-upgrade-{stamp}"
        target.mkdir(parents=True, exist_ok=False)
        for name in ("archive.sqlite3", "codes", "avatar"):
            source = self.data_dir / name
            if not source.exists():
                continue
            destination = target / name
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
        (target / "manifest.json").write_text(
            json.dumps(
                {
                    "format": 1,
                    "reason": "schema-upgrade",
                    "app_version": APP_VERSION,
                    "created_at": now(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return target

    def close(self):
        with self.lock:
            self.db.close()
            if self.process_lock:
                self.process_lock.close()

    def backup_directory(self):
        return self.data_dir.parent / "backups"

    def _prune_backups(self, keep=20):
        backups = sorted(
            self.backup_directory().glob("AlgoArchive-backup-*.zip"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old in backups[keep:]:
            old.unlink(missing_ok=True)

    def create_backup(self):
        with self.lock:
            self._ready()
            backup_dir = self.backup_directory()
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            name = f"AlgoArchive-backup-{stamp}.zip"
            destination = backup_dir / name
            staging = Path(
                tempfile.mkdtemp(prefix=".algoarchive-backup-", dir=str(self.data_dir.parent))
            )
            try:
                staged_database = staging / "archive.sqlite3"
                with closing(sqlite3.connect(str(staged_database))) as target:
                    self.db.backup(target)
                    target.commit()
                for directory in ("codes", "avatar"):
                    source = self.data_dir / directory
                    if source.is_dir():
                        shutil.copytree(source, staging / directory)
                    else:
                        (staging / directory).mkdir()
                manifest = {
                    "format": 1,
                    "app_version": APP_VERSION,
                    "database_schema": DATABASE_SCHEMA_VERSION,
                    "created_at": now(),
                    "counts": {
                        table: self.db.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0]
                        for table in ("contests", "problems", "algorithms")
                    },
                }
                (staging / "manifest.json").write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                with zipfile.ZipFile(
                    destination,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
                    compresslevel=6,
                ) as archive:
                    for path in sorted(staging.rglob("*")):
                        if path.is_file():
                            archive.write(path, path.relative_to(staging).as_posix())
            except Exception:
                destination.unlink(missing_ok=True)
                raise
            finally:
                shutil.rmtree(staging, ignore_errors=True)
            self._prune_backups()
            return {
                "name": name,
                "path": str(destination),
                "size": destination.stat().st_size,
                "created_at": datetime.fromtimestamp(
                    destination.stat().st_mtime,
                    tz=timezone.utc,
                ).isoformat().replace("+00:00", "Z"),
            }

    def list_backups(self):
        backup_dir = self.backup_directory()
        if not backup_dir.exists():
            return []
        items = []
        for path in sorted(
            backup_dir.glob("AlgoArchive-backup-*.zip"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            items.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "size": path.stat().st_size,
                    "created_at": datetime.fromtimestamp(
                        path.stat().st_mtime,
                        tz=timezone.utc,
                    ).isoformat().replace("+00:00", "Z"),
                }
            )
        return items

    def import_backup_file(self, source_path, original_name=""):
        source_path = Path(source_path)
        staging = Path(
            tempfile.mkdtemp(
                prefix=".algoarchive-import-backup-",
                dir=str(self.data_dir.parent),
            )
        )
        try:
            with zipfile.ZipFile(source_path) as archive:
                self._safe_extract_backup(archive, staging)
            (staging / "codes").mkdir(exist_ok=True)
            (staging / "avatar").mkdir(exist_ok=True)
            manifest = staging / "manifest.json"
            if not manifest.is_file():
                raise AppError("备份缺少 manifest.json", 400, "backup_invalid")
            try:
                manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError) as exc:
                raise AppError("备份清单格式不正确", 400, "backup_invalid") from exc
            if manifest_data.get("format") != 1:
                raise AppError("备份格式不受支持", 400, "backup_incompatible")
            if inspect_data_directory(staging)["state"] != "valid":
                raise AppError("备份中的数据库或代码文件不完整", 400, "backup_invalid")
        except (zipfile.BadZipFile, OSError) as exc:
            raise AppError("备份文件不是有效的 ZIP", 400, "backup_invalid") from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        backup_dir = self.backup_directory()
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        safe_stem = re.sub(
            r"[^A-Za-z0-9._-]+",
            "-",
            Path(original_name or "imported").stem,
        ).strip(".-")[:60]
        destination = backup_dir / (
            f"AlgoArchive-backup-{stamp}-{safe_stem or 'imported'}.zip"
        )
        shutil.copy2(source_path, destination)
        self._prune_backups()
        return {
            "name": destination.name,
            "path": str(destination),
            "size": destination.stat().st_size,
            "created_at": datetime.fromtimestamp(
                destination.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat().replace("+00:00", "Z"),
        }

    def _safe_extract_backup(self, archive, destination):
        members = archive.infolist()
        if len(members) > 10000:
            raise AppError("备份文件包含过多文件", 400, "backup_invalid")
        total_size = 0
        allowed = re.compile(
            r"^(?:manifest\.json|archive\.sqlite3|"
            r"codes/[a-f0-9]{32}\.(?:cpp|py|java|txt)|"
            r"avatar/avatar\.(?:png|jpg|webp))$"
        )
        for member in members:
            name = member.filename.replace("\\", "/")
            if (
                name.startswith("/")
                or ".." in Path(name).parts
                or member.is_dir()
                or not allowed.fullmatch(name)
            ):
                raise AppError("备份文件包含不安全的路径", 400, "backup_invalid")
            total_size += member.file_size
            if total_size > 2 * 1024 * 1024 * 1024:
                raise AppError("备份解压后超过 2 GiB", 413, "backup_too_large")
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)

    def restore_backup(self, name, confirmed=False):
        with self.lock:
            return self._restore_backup_locked(name, confirmed)

    def _restore_backup_locked(self, name, confirmed=False):
        if confirmed is not True:
            raise AppError("恢复备份会覆盖当前数据，请再次确认", 400, "confirmation_required")
        if not isinstance(name, str) or Path(name).name != name:
            raise AppError("备份名称无效", 400, "backup_invalid")
        archive_path = self.backup_directory() / name
        if not archive_path.is_file() or archive_path.suffix.casefold() != ".zip":
            raise AppError("备份文件不存在", 404, "backup_not_found")
        staging = Path(
            tempfile.mkdtemp(prefix=".algoarchive-restore-", dir=str(self.data_dir.parent))
        )
        rollback_database = staging / "rollback.sqlite3"
        old_codes = self.data_dir / ".codes-before-restore"
        old_avatar = self.data_dir / ".avatar-before-restore"
        try:
            with zipfile.ZipFile(archive_path) as archive:
                self._safe_extract_backup(archive, staging)
            (staging / "codes").mkdir(exist_ok=True)
            (staging / "avatar").mkdir(exist_ok=True)
            manifest_path = staging / "manifest.json"
            if not manifest_path.is_file():
                raise AppError("备份缺少 manifest.json", 400, "backup_invalid")
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError) as exc:
                raise AppError("备份清单格式不正确", 400, "backup_invalid") from exc
            if manifest.get("format") != 1:
                raise AppError("备份格式不受支持", 400, "backup_incompatible")
            # Migrate the restored staging copy before swapping it into the live
            # connection, so old backups become usable without a restart.
            upgrader = Repository(staging, acquire_lock=False)
            upgrader.close()
            state = inspect_data_directory(staging)
            if state["state"] != "valid":
                raise AppError(
                    "备份中的数据库或代码文件不完整",
                    400,
                    "backup_invalid",
                )
            current_backup = self.create_backup()
            with self.lock:
                with closing(sqlite3.connect(str(rollback_database))) as rollback:
                    self.db.backup(rollback)
                    rollback.commit()
                self.db.commit()
                for old in (old_codes, old_avatar):
                    if old.exists():
                        shutil.rmtree(old)
                try:
                    os.replace(self.data_dir / "codes", old_codes)
                    os.replace(self.data_dir / "avatar", old_avatar)
                    os.replace(staging / "codes", self.data_dir / "codes")
                    os.replace(staging / "avatar", self.data_dir / "avatar")
                    with closing(
                        sqlite3.connect(str(staging / "archive.sqlite3"))
                    ) as source:
                        source.backup(self.db)
                    self.db.commit()
                    self._flush_pending()
                except Exception:
                    with closing(sqlite3.connect(str(rollback_database))) as rollback:
                        rollback.backup(self.db)
                    self.db.commit()
                    for current, old in (
                        (self.data_dir / "codes", old_codes),
                        (self.data_dir / "avatar", old_avatar),
                    ):
                        if old.exists():
                            shutil.rmtree(current, ignore_errors=True)
                            os.replace(old, current)
                    raise
                shutil.rmtree(old_codes, ignore_errors=True)
                shutil.rmtree(old_avatar, ignore_errors=True)
            return {
                "ok": True,
                "current_backup": current_backup,
                "restored_from": name,
                "counts": state.get("counts", {}),
            }
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def relocate_to(self, target):
        target = Path(target).expanduser().resolve()
        source = self.data_dir.resolve()
        if target == source:
            raise AppError("新数据目录与当前目录相同")
        if target.is_relative_to(source) or source.is_relative_to(target):
            raise AppError("新旧数据目录不能互相包含")
        state = inspect_data_directory(target)
        if state["state"] == "valid":
            raise AppError(
                "新数据目录已有有效数据，不能覆盖或合并",
                409,
                "data_conflict",
                path=str(target),
            )
        if state["state"] not in {"empty", "residual"}:
            raise AppError(
                "新数据目录不完整或不可用，请先检查",
                409,
                "data_incomplete",
                path=str(target),
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(
                prefix=".algoarchive-relocating-",
                dir=str(target.parent),
            )
        )
        backup = None
        try:
            backup = self.create_backup()
            with zipfile.ZipFile(backup["path"]) as archive:
                self._safe_extract_backup(archive, staging)
            (staging / "codes").mkdir(exist_ok=True)
            (staging / "avatar").mkdir(exist_ok=True)
            (staging / "manifest.json").unlink(missing_ok=True)
            if inspect_data_directory(staging)["state"] != "valid":
                raise AppError("迁移副本校验失败，原数据未改变", 500, "migration_failed")
            if target.exists():
                for residual in ("runtime.lock", "runtime.lock.pending"):
                    (target / residual).unlink(missing_ok=True)
                target.rmdir()
            os.replace(staging, target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return {
            "ok": True,
            "old_data_dir": str(source),
            "new_data_dir": str(target),
            "backup": backup,
        }

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
        row["tests"] = self._problem_tests(identifier)
        return row

    def _problem_tests(self, identifier):
        return [
            {
                "ordinal": row["ordinal"],
                "input": row["input"],
                "output": row["output"],
            }
            for row in self.db.execute(
                "SELECT ordinal,input,output FROM problem_tests "
                "WHERE problem_id=? ORDER BY ordinal",
                (identifier,),
            )
        ]

    def replace_problem_tests(self, identifier, payload):
        if not isinstance(payload, dict):
            raise AppError("测试用例请求格式不正确")
        try:
            tests = validate_test_cases(payload.get("tests"))
        except ValueError as exc:
            raise AppError(str(exc)) from None
        with self.lock:
            self._ready()
            self._row("problems", identifier)
            timestamp = now()
            with self.db:
                self.db.execute(
                    "DELETE FROM problem_tests WHERE problem_id=?",
                    (identifier,),
                )
                self.db.executemany(
                    "INSERT INTO problem_tests "
                    "(problem_id,ordinal,input,output,updated_at) "
                    "VALUES (?,?,?,?,?)",
                    [
                        (
                            identifier,
                            ordinal,
                            item["input"],
                            item["output"],
                            timestamp,
                        )
                        for ordinal, item in enumerate(tests)
                    ],
                )
            return self._problem_tests(identifier)

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
        url = expand_schemeless_url(
            text_value(payload.get("url"), "题目链接", 2048, True)
        )
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
            url = expand_schemeless_url(
                text_value(payload.get("url"), "比赛链接", 2048, True)
            )
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
            url = expand_schemeless_url(
                text_value(values.get("url"), "比赛链接", 2048, True)
            )
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

    def __init__(
        self,
        address,
        repo,
        web_dir=ROOT / "web",
        config_path=None,
        config=None,
    ):
        self.repo = repo
        self.web_dir = Path(web_dir).resolve()
        self.config_path = Path(config_path or default_config_path()).resolve()
        self.config = _normalized_user_config(
            config if config is not None else load_user_config(self.config_path)
        )
        self.csrf_token = secrets.token_urlsafe(32)
        self.user_name = getpass.getuser()
        self.project_id = hashlib.sha256(str(repo.data_dir).encode("utf-8")).hexdigest()
        self.started_at = time.time()
        self.log_path = self.config_path.parent / "logs" / "algoarchive.log"
        self.maintenance = False
        self.active_test_runs = {}
        self.active_test_runs_lock = threading.RLock()
        self.compiler_version_cache = None
        super().__init__(address, RequestHandler)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(
            f"algoarchive.{os.getpid()}.{self.server_address[1]}"
        )
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        file_handler = RotatingFileHandler(
            self.log_path,
            maxBytes=1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(stream_handler)
        self.logger.addHandler(file_handler)

    def server_close(self):
        logger = getattr(self, "logger", None)
        if logger is not None:
            for handler in list(logger.handlers):
                handler.flush()
                handler.close()
                logger.removeHandler(handler)
        super().server_close()

    @property
    def local_address(self):
        return f"http://127.0.0.1:{self.server_address[1]}"

    def settings_payload(self):
        compiler = self.compiler_payload()
        return {
            "version": APP_VERSION,
            "address": self.local_address,
            "data_dir": str(self.repo.data_dir),
            "default_data_dir": str(default_data_dir().resolve()),
            "config_path": str(self.config_path),
            "log_path": str(self.log_path),
            "backup_dir": str(self.repo.backup_directory()),
            "browser": dict(self.config.get("browser") or {}),
            "started_at": datetime.fromtimestamp(
                self.started_at,
                tz=timezone.utc,
            ).isoformat().replace("+00:00", "Z"),
            "database_schema": DATABASE_SCHEMA_VERSION,
            "compiler": compiler,
            "cph": {
                "author": CPH_AUTHOR,
                "repository": CPH_REPOSITORY,
                "license": CPH_LICENSE,
                "reference_commit": CPH_REFERENCE_COMMIT,
            },
        }

    def compiler_payload(self):
        compiler_path, standard = resolve_cpp_compiler(self.config)
        if self.compiler_version_cache is None or (
            self.compiler_version_cache.get("path") != str(compiler_path or "")
        ):
            self.compiler_version_cache = {
                "path": str(compiler_path or ""),
                "version": compiler_version(compiler_path),
            }
        return {
            "path": str(compiler_path or ""),
            "configured_path": str(
                (self.config.get("compiler") or {}).get("cpp_path") or ""
            ),
            "standard": standard,
            "standards": list(CPP_STANDARDS),
            "available": bool(compiler_path and compiler_path.is_file()),
            "version": self.compiler_version_cache["version"],
            "auto_detected": not bool(
                (self.config.get("compiler") or {}).get("cpp_path")
            ),
        }

    def update_compiler_settings(self, payload):
        cpp_path = str(payload.get("cpp_path") or "").strip()
        standard = str(payload.get("standard") or DEFAULT_CPP_STANDARD)
        if standard not in CPP_STANDARDS:
            raise AppError("C++ 标准不受支持")
        if len(cpp_path) > 2048:
            raise AppError("编译器路径过长")
        if cpp_path:
            candidate = Path(cpp_path).expanduser()
            if not candidate.is_absolute() or not candidate.is_file():
                raise AppError("C++ 编译器路径不存在或不是文件")
            if os.name == "nt" and candidate.suffix.casefold() not in {
                ".exe",
                ".com",
            }:
                raise AppError("Windows C++ 编译器必须是可执行文件")
            cpp_path = str(candidate.resolve())
            if not compiler_version(candidate):
                raise AppError("无法执行所选 C++ 编译器")
        self.config["compiler"] = {
            "cpp_path": cpp_path,
            "cpp_standard": standard,
        }
        save_user_config(self.config, self.config_path)
        self.compiler_version_cache = None
        return self.compiler_payload()

    def test_compiler_capabilities(self, payload=None):
        payload = dict(payload or {})
        config = dict(self.config)
        compiler = dict(config.get("compiler") or {})
        if "cpp_path" in payload:
            compiler["cpp_path"] = str(payload.get("cpp_path") or "").strip()
        if "standard" in payload:
            compiler["cpp_standard"] = str(
                payload.get("standard") or DEFAULT_CPP_STANDARD
            )
        if compiler["cpp_standard"] not in CPP_STANDARDS:
            raise AppError("C++ 标准不受支持")
        configured_path = str(compiler.get("cpp_path") or "").strip()
        if configured_path:
            candidate = Path(configured_path).expanduser()
            if not candidate.is_absolute() or not candidate.is_file():
                raise AppError("C++ 编译器路径不存在或不是文件")
        config["compiler"] = compiler
        compiler_path, standard = resolve_cpp_compiler(config)
        if not compiler_path:
            raise AppError("未找到可用的 g++ 编译器", 503, "compiler_missing")
        runner = CppTestRunner(compiler_path, standard)
        source = r"""
#include <bits/stdc++.h>
using namespace std;
int main() {
    __int128 value = 1;
    value <<= 100;
    multiset<int> ordered{2, 1};
    unordered_map<int, int> mapped{{1, 20}};
    if (value <= 0 || *ordered.begin() != 1 || mapped[1] != 20) return 1;
    cout << "CPH_OK\n";
}
"""
        result = runner.run(
            source,
            [{"input": "", "output": "CPH_OK\n"}],
            time_limit_ms=3000,
        )
        return {
            "ok": bool(result.get("ok")),
            "compiler": str(compiler_path),
            "standard": standard,
            "checks": {
                "__int128": result.get("ok", False),
                "multiset": result.get("ok", False),
                "unordered_map": result.get("ok", False),
            },
            "result": result,
        }

    def run_cpp_tests(self, payload):
        run_id = payload.get("run_id")
        if (
            not isinstance(run_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", run_id)
        ):
            raise AppError("测试运行标识不正确")
        compiler_path, standard = resolve_cpp_compiler(self.config)
        runner = CppTestRunner(compiler_path, standard)
        with self.active_test_runs_lock:
            if run_id in self.active_test_runs:
                raise AppError("该测试任务已在运行")
            self.active_test_runs[run_id] = runner
        try:
            return runner.run(
                payload.get("code", ""),
                payload.get("tests"),
                payload.get("time_limit_ms", 3000),
            )
        except ValueError as exc:
            raise AppError(str(exc)) from None
        finally:
            with self.active_test_runs_lock:
                self.active_test_runs.pop(run_id, None)

    def run_problem_tests(self, problem_id, payload):
        self.repo.get_problem(problem_id)
        return self.run_cpp_tests(payload)

    def stop_problem_tests(self, run_id):
        if not isinstance(run_id, str):
            raise AppError("测试运行标识不正确")
        with self.active_test_runs_lock:
            runner = self.active_test_runs.get(run_id)
        if runner is None:
            return {"ok": False, "message": "没有找到正在运行的测试任务"}
        runner.stop()
        return {"ok": True, "message": "已请求停止测试运行"}

    def update_browser_settings(self, payload):
        mode = str(payload.get("mode") or "default").casefold()
        window_mode = str(payload.get("window_mode") or "tab").casefold()
        custom_path = str(payload.get("custom_path") or "").strip()
        if mode not in {"default", "edge", "chrome", "firefox", "custom"}:
            raise AppError("浏览器类型无效")
        if window_mode not in {"tab", "app"}:
            raise AppError("窗口模式无效")
        if len(custom_path) > 2048:
            raise AppError("浏览器路径过长")
        if mode == "custom":
            if not custom_path:
                raise AppError("请填写自定义浏览器可执行文件路径")
            if find_browser_executable("custom", custom_path) is None:
                raise AppError("自定义浏览器路径不存在或不是可执行文件")
            custom_path = str(Path(custom_path).expanduser().resolve())
        else:
            custom_path = ""
        self.config["browser"] = {
            "mode": mode,
            "window_mode": window_mode,
            "custom_path": custom_path,
        }
        save_user_config(self.config, self.config_path)
        return dict(self.config["browser"])


class RequestHandler(BaseHTTPRequestHandler):
    server_version = f"AlgoArchive/{APP_VERSION}"
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

    def _receive_backup_upload(self):
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type not in {"application/zip", "application/octet-stream"}:
            raise AppError("备份上传必须使用 ZIP 文件", 415, "invalid_content_type")
        if self.headers.get("Transfer-Encoding"):
            raise AppError("不支持此请求编码", 400, "invalid_request")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise AppError("请求长度无效") from None
        if length <= 0 or length > MAX_BACKUP_UPLOAD_BYTES:
            raise AppError("备份文件为空或超过 512 MiB", 413, "too_large")
        fd, name = tempfile.mkstemp(
            prefix=".algoarchive-upload-",
            suffix=".zip",
            dir=str(self.server.repo.data_dir.parent),
        )
        try:
            remaining = length
            with os.fdopen(fd, "wb") as stream:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise AppError("备份上传未完成", 400, "upload_incomplete")
                    stream.write(chunk)
                    remaining -= len(chunk)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            try:
                os.unlink(name)
            except OSError:
                pass
            raise
        return Path(name)

    def _dispatch(self):
        mutation = self.command in {"POST", "PUT", "DELETE"}
        self._guard(mutation)
        path = urlsplit(self.path).path
        repo = self.server.repo
        if self.command in {"GET", "HEAD"}:
            if path == "/api/health":
                with repo.lock:
                    database = repo.db.execute("PRAGMA database_list").fetchone()
                    database_counts = {
                        table: repo.db.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0]
                        for table in ("contests", "problems", "algorithms")
                    }
                    page_count = repo.db.execute("PRAGMA page_count").fetchone()[0]
                return self._json({
                    "app": "AlgoArchive",
                    "version": APP_VERSION,
                    "project_id": self.server.project_id,
                    "data_dir": str(self.server.repo.data_dir),
                    "database_file": database["file"],
                    "database_counts": database_counts,
                    "database_page_count": page_count,
                })
            if path == "/api/state":
                return self._json(repo.state())
            if path == "/api/settings":
                return self._json({"settings": self.server.settings_payload()})
            if path == "/api/backups":
                return self._json(
                    {
                        "backup_dir": str(repo.backup_directory()),
                        "backups": repo.list_backups(),
                    }
                )
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
        if self.command == "POST" and path == "/api/backups/upload":
            upload = self._receive_backup_upload()
            try:
                backup = repo.import_backup_file(
                    upload,
                    unquote(self.headers.get("X-Backup-Filename", "")),
                )
            finally:
                upload.unlink(missing_ok=True)
            return self._json({"backup": backup}, 201)
        body = self._body()
        if self.command == "PUT" and path == "/api/settings/browser":
            return self._json(
                {"browser": self.server.update_browser_settings(body)}
            )
        if self.command == "PUT" and path == "/api/settings/compiler":
            return self._json(
                {"compiler": self.server.update_compiler_settings(body)}
            )
        if self.command == "POST" and path == "/api/settings/browser/test":
            settings = {
                key: body.get(key, "")
                for key in ("mode", "window_mode", "custom_path")
            }
            return self._json(
                {"launch": launch_browser(self.server.local_address, settings)}
            )
        if self.command == "POST" and path == "/api/settings/compiler/test":
            return self._json(
                {"diagnostic": self.server.test_compiler_capabilities(body)}
            )
        if self.command == "POST" and path == "/api/backups/create":
            return self._json({"backup": repo.create_backup()}, 201)
        if self.command == "POST" and path == "/api/backups/restore":
            return self._json(
                repo.restore_backup(
                    body.get("name"),
                    confirmed=body.get("confirmed") is True,
                )
            )
        if self.command == "POST" and path == "/api/data-directory":
            value = body.get("data_dir")
            if not isinstance(value, str) or not value.strip():
                raise AppError("请填写新的数据目录")
            target = Path(value).expanduser()
            if not target.is_absolute():
                raise AppError("数据目录必须是绝对路径")
            migrated = repo.relocate_to(target)
            self.server.config["data_dir"] = migrated["new_data_dir"]
            save_user_config(self.server.config, self.server.config_path)
            self._json(
                {
                    **migrated,
                    "restart_required": True,
                    "message": "数据已迁移，程序即将退出。请重新打开算法档案。",
                }
            )
            threading.Timer(0.5, self.server.shutdown).start()
            return
        if self.command == "POST" and path == "/api/open-data-folder":
            try:
                if os.name == "nt":
                    os.startfile(str(repo.data_dir))
                else:
                    subprocess.Popen(
                        ["xdg-open", str(repo.data_dir)],
                        close_fds=True,
                    )
            except OSError as exc:
                raise AppError(
                    "无法打开数据文件夹，请根据设置页显示的路径手动打开。",
                    503,
                    "open_folder_failed",
                ) from exc
            return self._json({"ok": True, "path": str(repo.data_dir)})
        if self.command == "POST" and path == "/api/open-log-folder":
            log_dir = self.server.log_path.parent
            log_dir.mkdir(parents=True, exist_ok=True)
            try:
                if os.name == "nt":
                    os.startfile(str(log_dir))
                else:
                    subprocess.Popen(
                        ["xdg-open", str(log_dir)],
                        close_fds=True,
                    )
            except OSError as exc:
                raise AppError(
                    "无法打开日志文件夹，请根据诊断页显示的路径手动打开。",
                    503,
                    "open_folder_failed",
                ) from exc
            return self._json({"ok": True, "path": str(log_dir)})
        if self.command == "POST" and path == "/api/shutdown":
            self._json({"ok": True})
            threading.Timer(0.3, self.server.shutdown).start()
            return
        if self.command == "PUT" and path == "/api/profile":
            return self._json({"profile": repo.update_profile(body)})
        if self.command == "POST" and path == "/api/contests":
            return self._json({"contest": repo.create_contest(body)}, 201)
        if self.command == "POST" and path == "/api/problems":
            return self._json({"problem": repo.create_problem(body)}, 201)
        if self.command == "POST" and path == "/api/problems/import":
            return self._json(repo.import_problems(body), 201)
        match = re.fullmatch(
            r"/api/problems/([a-f0-9]{32})/tests", path
        )
        if self.command == "PUT" and match:
            return self._json(
                {"tests": repo.replace_problem_tests(match[1], body)}
            )
        match = re.fullmatch(
            r"/api/problems/([a-f0-9]{32})/run", path
        )
        if self.command == "POST" and match:
            return self._json(
                self.server.run_problem_tests(match[1], body)
            )
        match = re.fullmatch(
            r"/api/problems/([a-f0-9]{32})/run/stop", path
        )
        if self.command == "POST" and match:
            return self._json(
                self.server.stop_problem_tests(body.get("run_id"))
            )
        if self.command == "POST" and path == "/api/compiler/run":
            return self._json(self.server.run_cpp_tests(body))
        if self.command == "POST" and path == "/api/compiler/run/stop":
            return self._json(
                self.server.stop_problem_tests(body.get("run_id"))
            )
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
            self.server.logger.exception("Unhandled request error: %s", exc)
            self._json({"error": "本地服务发生错误，请查看启动窗口。数据目录请保留。", "code": "internal_error"}, 500)

    do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = _handle

    def do_OPTIONS(self):
        self._json({"error": "不允许跨站请求", "code": "forbidden_origin"}, 403)

    def log_request(self, code="-", size="-"):
        try:
            status = int(code)
        except (TypeError, ValueError):
            status = 0
        method = str(self.command or "").upper()
        is_write = method in {"POST", "PUT", "PATCH", "DELETE"}
        if status < 400 and not is_write:
            return
        level = logging.WARNING if status >= 400 else logging.INFO
        self.server.logger.log(
            level,
            '"%s" %s %s',
            self.requestline,
            code,
            size,
        )

    def log_message(self, fmt, *args):
        # Malformed-request messages bypass log_request, so keep them visible.
        self.server.logger.warning(fmt, *args)


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
    parser.add_argument("--config-path")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port 必须介于 0 和 65535")
    explicit_data_dir = args.data_dir is not None
    config_path = Path(args.config_path or default_config_path()).resolve()
    config = load_user_config(config_path)
    args.config_path = str(config_path)
    args.config = config
    data_dir = resolve_data_dir(args.data_dir, config_path)
    args.data_dir = str(data_dir)
    if not explicit_data_dir:
        legacy_candidates = [ROOT / "data"]
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            legacy_candidates.append(Path(local_app_data) / "AlgoArchive" / "data")
        legacy_candidates.append(
            Path.home() / "AppData" / "Local" / "AlgoArchive" / "data"
        )
        before = inspect_data_directory(data_dir)
        prepare_user_data_dir(data_dir, legacy_candidates)
        after = inspect_data_directory(data_dir)
        if before["state"] != after["state"] and after["state"] == "valid":
            print(f"旧数据已迁移到: {data_dir}", flush=True)
        config["data_dir"] = str(data_dir)
        save_user_config(config, config_path)
    else:
        state = inspect_data_directory(data_dir)
        if state["state"] not in {"empty", "residual", "valid"}:
            raise AppError(
                "指定的数据目录不可用，未执行任何写入。",
                500,
                f"data_{state['state']}",
                path=str(data_dir),
            )
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
                            open_browser(address, config.get("browser"))
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
            server = LocalServer(
                ("127.0.0.1", port),
                repo,
                config_path=args.config_path,
                config=args.config,
            )
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
        threading.Timer(
            0.5,
            lambda: open_browser(address, args.config.get("browser")),
        ).start()
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
