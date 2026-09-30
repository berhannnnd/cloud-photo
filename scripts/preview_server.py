#!/usr/bin/env python3
"""Shared loopback image relay for cloud-photo previews.

One relay process can serve several conversations. Each conversation registers
a workspace root and receives its own random token. Requests are resolved
through that token, so sharing a port does not share a workspace. The service
is loopback-only and lifecycle operations use the exact recorded PID; there is
no process-name or global kill.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import errno
import fcntl
import http.server
import json
import mimetypes
import os
import pathlib
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

MAX_FILE_BYTES = 2 * 1024 * 1024
DEFAULT_LEASE_SECONDS = 30 * 60
DEFAULT_SERVICE_ID = "cloud-photo"


def fail(message: str) -> None:
    raise ValueError(message)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def safe_name(value: str, label: str) -> str:
    value = value.strip()
    if not value or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in value):
        fail(f"{label} must contain only letters, digits, '.', '_' or '-'")
    return value


def safe_session(value: str) -> str:
    return safe_name(value, "session-id")


def safe_service(value: str) -> str:
    return safe_name(value, "service-id")


def service_paths(state_dir: pathlib.Path, service_id: str) -> tuple[pathlib.Path, pathlib.Path]:
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / f"{service_id}.service.json", state_dir / f"{service_id}.service.lock"


def read_json(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"service state not found: {path}")
    if not isinstance(value, dict):
        fail(f"invalid service state: {path}")
    return value


def read_service_state(path: pathlib.Path) -> dict:
    value = read_json(path)
    if not isinstance(value.get("pid"), int) or not isinstance(value.get("port"), int):
        fail(f"invalid service state: {path}")
    sessions = value.get("sessions", {})
    if not isinstance(sessions, dict):
        fail(f"invalid service sessions: {path}")
    return value


def atomic_write(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def acquire_lock(lock_path: pathlib.Path, *, blocking: bool = True):
    handle = lock_path.open("a+")
    flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
    try:
        fcntl.flock(handle.fileno(), flags)
    except OSError as error:
        handle.close()
        if error.errno in (errno.EACCES, errno.EAGAIN):
            fail(f"service is busy: {lock_path.stem}")
        raise
    return handle


def process_command(pid: int) -> str:
    try:
        result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], check=False, capture_output=True, text=True)
    except OSError:
        return ""
    return result.stdout.strip()


def process_matches(state: dict) -> bool:
    pid = int(state["pid"])
    command = process_command(pid)
    service_id = str(state.get("service_id", ""))
    return "preview_server.py serve" in command and f"--service-id {service_id}" in command


def session_for_token(state: dict, token: str) -> dict | None:
    for session in (state.get("sessions") or {}).values():
        if isinstance(session, dict) and secrets.compare_digest(str(session.get("token", "")), token):
            return session
    return None


class RelayServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True
    timeout = 0.5


class RelayHandler(http.server.BaseHTTPRequestHandler):
    server_version = "cloud-photo-relay/2"

    def log_message(self, _format: str, *_args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        params = parse_qs(parsed.query)
        token = params.get("token", [""])[0]
        try:
            state = read_service_state(pathlib.Path(self.server.registry_file))  # type: ignore[attr-defined]
            session = session_for_token(state, token)
        except (OSError, ValueError, json.JSONDecodeError):
            self.send_error(503, "relay registry unavailable")
            return
        if session is None:
            self.send_error(403, "invalid relay token")
            return
        if parsed.path == "/health":
            self._send_bytes(b'{"ok":true}\n', "application/json; charset=utf-8")
            return
        raw_path = unquote(parsed.path.lstrip("/"))
        if not raw_path or "\\" in raw_path:
            self.send_error(404, "image not found")
            return
        root = pathlib.Path(str(session["root"])).resolve()
        candidate = (root / raw_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            self.send_error(404, "image not found")
            return
        if not candidate.is_file():
            self.send_error(404, "image not found")
            return
        try:
            size = candidate.stat().st_size
        except OSError:
            self.send_error(404, "image not found")
            return
        if size <= 0 or size > MAX_FILE_BYTES:
            self.send_error(413, "image exceeds relay limit")
            return
        mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if not mime.startswith("image/"):
            self.send_error(415, "relay serves images only")
            return
        try:
            payload = candidate.read_bytes()
        except OSError:
            self.send_error(404, "image not found")
            return
        self._send_bytes(payload, mime)

    def _send_bytes(self, payload: bytes, mime: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)


def launch_service(state_path: pathlib.Path, log_path: pathlib.Path, service_id: str, state_dir: pathlib.Path) -> dict:
    ready_path = state_dir / f".{service_id}.ready.json"
    command = [
        sys.executable,
        str(pathlib.Path(__file__).resolve()),
        "serve",
        "--state-file", str(state_path),
        "--state-dir", str(state_dir),
        "--service-id", service_id,
        "--ready-file", str(ready_path),
    ]
    with log_path.open("ab") as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    deadline = time.monotonic() + 5
    ready = None
    while time.monotonic() < deadline:
        if ready_path.exists():
            ready = json.loads(ready_path.read_text(encoding="utf-8"))
            break
        if process.poll() is not None:
            fail(f"relay exited before becoming ready; see {log_path}")
        time.sleep(0.03)
    ready_path.unlink(missing_ok=True)
    if ready is None:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
        fail(f"relay did not become ready; see {log_path}")
    return {**ready, "pid": process.pid}


def connection(state: dict, session: dict) -> dict:
    return {
        "schema_version": state.get("schema_version", "cloud-photo/relay-v2"),
        "service_id": state["service_id"],
        "shared": True,
        "pid": state["pid"],
        "port": state["port"],
        "url": state["url"],
        "session_id": session["session_id"],
        "token": session["token"],
        "root": session["root"],
        "state_path": state["state_path"],
        "log_path": state["log_path"],
        "lease_seconds": session.get("lease_seconds", DEFAULT_LEASE_SECONDS),
    }


def start(args: argparse.Namespace) -> None:
    service_id = safe_service(args.service_id)
    session_id = safe_session(args.session_id or f"photo-{secrets.token_hex(8)}")
    root = pathlib.Path(args.root).resolve()
    if not root.is_dir():
        fail(f"relay root is not a directory: {root}")
    state_dir = pathlib.Path(args.state_dir).resolve()
    state_path, lock_path = service_paths(state_dir, service_id)
    log_path = state_dir / f"{service_id}.service.log"
    lock_handle = acquire_lock(lock_path)
    try:
        state = None
        if state_path.exists():
            candidate = read_service_state(state_path)
            if process_matches(candidate):
                state = candidate
            else:
                state_path.unlink(missing_ok=True)
        if state is None:
            ready = launch_service(state_path, log_path, service_id, state_dir)
            state = {
                "schema_version": "cloud-photo/relay-v2",
                "service_id": service_id,
                "pid": ready["pid"],
                "port": int(ready["port"]),
                "url": f"http://127.0.0.1:{ready['port']}",
                "state_path": str(state_path),
                "log_path": str(log_path),
                "started_at": now_iso(),
                "sessions": {},
            }
        sessions = state.setdefault("sessions", {})
        existing = sessions.get(session_id)
        if isinstance(existing, dict) and pathlib.Path(str(existing.get("root", ""))).resolve() == root:
            session = existing
        else:
            session = {
                "session_id": session_id,
                "token": secrets.token_urlsafe(32),
                "root": str(root),
                "attached_at": now_iso(),
                "lease_seconds": args.lease_seconds,
            }
            sessions[session_id] = session
        atomic_write(state_path, state)
        print(json.dumps(connection(state, session), ensure_ascii=False))
    finally:
        lock_handle.close()


def serve(args: argparse.Namespace) -> None:
    service_id = safe_service(args.service_id)
    state_path = pathlib.Path(args.state_file).resolve()
    state_dir = pathlib.Path(args.state_dir).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    server = None
    try:
        server = RelayServer(("127.0.0.1", 0), RelayHandler)
        server.registry_file = str(state_path)  # type: ignore[attr-defined]
        port = int(server.server_address[1])
        if args.ready_file:
            atomic_write(pathlib.Path(args.ready_file), {"pid": os.getpid(), "port": port, "service_id": service_id})
        stop_event = threading.Event()

        def stop(_signum, _frame) -> None:
            stop_event.set()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        while not stop_event.is_set():
            server.handle_request()
    finally:
        if server is not None:
            with contextlib.suppress(Exception):
                server.server_close()


def stop_session(args: argparse.Namespace) -> None:
    service_id = safe_service(args.service_id)
    session_id = safe_session(args.session_id)
    state_dir = pathlib.Path(args.state_dir).resolve()
    state_path, lock_path = service_paths(state_dir, service_id)
    lock_handle = acquire_lock(lock_path)
    try:
        state = read_service_state(state_path)
        if not process_matches(state):
            state_path.unlink(missing_ok=True)
            fail("refused to modify: recorded PID is no longer the cloud-photo relay")
        removed = (state.get("sessions") or {}).pop(session_id, None)
        atomic_write(state_path, state)
        print(json.dumps({"service_id": service_id, "session_id": session_id, "session_stopped": removed is not None, "service_running": True}, ensure_ascii=False))
    finally:
        lock_handle.close()


def terminate_service(state: dict) -> None:
    if not process_matches(state):
        fail("refused to stop: recorded PID is no longer the cloud-photo relay")
    pid = int(state["pid"])
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and process_matches(state):
        time.sleep(0.05)
    if process_matches(state):
        os.kill(pid, signal.SIGKILL)


def stop_service(args: argparse.Namespace) -> None:
    service_id = safe_service(args.service_id)
    state_dir = pathlib.Path(args.state_dir).resolve()
    state_path, lock_path = service_paths(state_dir, service_id)
    lock_handle = acquire_lock(lock_path)
    try:
        state = read_service_state(state_path)
        if state.get("sessions"):
            fail("service still has active sessions; stop each session first")
        terminate_service(state)
        state_path.unlink(missing_ok=True)
        print(json.dumps({"service_id": service_id, "service_stopped": True}, ensure_ascii=False))
    finally:
        lock_handle.close()


def status(args: argparse.Namespace) -> None:
    service_id = safe_service(args.service_id)
    state_dir = pathlib.Path(args.state_dir).resolve()
    state_path, _lock_path = service_paths(state_dir, service_id)
    if not state_path.exists():
        print(json.dumps({"service_id": service_id, "running": False, "sessions": []}, ensure_ascii=False))
        return
    state = read_service_state(state_path)
    running = process_matches(state)
    result = {"service_id": service_id, "running": running, "pid": state.get("pid"), "port": state.get("port"), "url": state.get("url"), "sessions": sorted((state.get("sessions") or {}).keys())}
    if args.session_id:
        session_id = safe_session(args.session_id)
        session = (state.get("sessions") or {}).get(session_id)
        result["session_id"] = session_id
        result["session"] = connection(state, session) if isinstance(session, dict) and running else None
    print(json.dumps(result, ensure_ascii=False))


def url(args: argparse.Namespace) -> None:
    service_id = safe_service(args.service_id)
    session_id = safe_session(args.session_id)
    state_path, _lock_path = service_paths(pathlib.Path(args.state_dir).resolve(), service_id)
    state = read_service_state(state_path)
    if not process_matches(state):
        fail("relay is not running")
    session = (state.get("sessions") or {}).get(session_id)
    if not isinstance(session, dict):
        fail(f"session is not registered: {session_id}")
    relative = args.path.strip().lstrip("/")
    if not relative or ".." in pathlib.PurePosixPath(relative).parts or "\\" in relative:
        fail("path must be a workspace-relative file without '..'")
    query = urlencode({"token": session["token"]})
    print(f"{state['url']}/{quote(relative, safe='/._-~')}?{query}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage a shared cloud-photo image relay")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start", help="start once or attach a new conversation session")
    p.add_argument("--root", required=True)
    p.add_argument("--state-dir", required=True)
    p.add_argument("--service-id", default=DEFAULT_SERVICE_ID)
    p.add_argument("--session-id")
    p.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    p.set_defaults(func=start)
    p = sub.add_parser("serve", help=argparse.SUPPRESS)
    p.add_argument("--state-file", required=True)
    p.add_argument("--state-dir", required=True)
    p.add_argument("--service-id", required=True)
    p.add_argument("--ready-file", required=True)
    p.set_defaults(func=serve)
    p = sub.add_parser("stop", help="unregister one session; leave shared service running")
    p.add_argument("--state-dir", required=True)
    p.add_argument("--service-id", default=DEFAULT_SERVICE_ID)
    p.add_argument("--session-id", required=True)
    p.set_defaults(func=stop_session)
    p = sub.add_parser("stop-service", help="stop the shared service after an explicit user close request")
    p.add_argument("--state-dir", required=True)
    p.add_argument("--service-id", default=DEFAULT_SERVICE_ID)
    p.add_argument("--confirm-close", action="store_true", required=True,
                   help="required guard; use only after the user explicitly asked to close the service")
    p.set_defaults(func=stop_service)
    p = sub.add_parser("status")
    p.add_argument("--state-dir", required=True)
    p.add_argument("--service-id", default=DEFAULT_SERVICE_ID)
    p.add_argument("--session-id")
    p.set_defaults(func=status)
    p = sub.add_parser("url")
    p.add_argument("--state-dir", required=True)
    p.add_argument("--service-id", default=DEFAULT_SERVICE_ID)
    p.add_argument("--session-id", required=True)
    p.add_argument("--path", required=True)
    p.set_defaults(func=url)
    args = parser.parse_args()
    try:
        args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
