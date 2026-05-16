import asyncio
import os
import shlex
import signal
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from fastapi import HTTPException, WebSocket, WebSocketDisconnect

from core.runtime_registry import runtime_registry
from utils.security import get_project_root

try:
    import winpty
except ImportError:  # pragma: no cover - Windows dependency
    winpty = None


def _default_shell() -> str:
    if os.name == "nt":
        return shutil.which("powershell") or shutil.which("cmd") or "cmd"
    return os.environ.get("SHELL") or shutil.which("bash") or "sh"


def _quote(path: Path) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline([str(path)])
    return shlex.quote(str(path))


def _workspace_runtime_dir() -> Path:
    return get_project_root() / "backend" / "runtimes"


def _runtime_executable(*parts: str) -> Optional[Path]:
    candidate = _workspace_runtime_dir().joinpath(*parts)
    return candidate if candidate.exists() else None


def _shell_command(*parts: str) -> Optional[str]:
    runtime = _runtime_executable(*parts)
    return _quote(runtime) if runtime else None


def _require_runtime(*parts: str, detail: str) -> str:
    runtime = _shell_command(*parts)
    if runtime:
        return runtime
    raise HTTPException(status_code=400, detail=detail)


def _run_compiled_command(compiler: str, source: Path, exe: Path, extra_flags: str = "") -> str:
    quoted_source = _quote(source)
    quoted_exe = _quote(exe)
    compile_cmd = f"{compiler} {quoted_source}{extra_flags} -o {quoted_exe}"
    if os.name == "nt":
        return f"{compile_cmd}; if ($LASTEXITCODE -eq 0) {{ & {quoted_exe} }}"
    return f"{compile_cmd} && {quoted_exe}"


def build_run_command(path: str) -> str:
    file_path = (get_project_root() / path).resolve()
    ext = file_path.suffix.lower()
    quoted = _quote(file_path)

    if ext == ".py":
        resolved = runtime_registry.resolve("python", "python/python.exe")
        python = _quote(resolved) if resolved else None
        if not python:
            raise HTTPException(status_code=400, detail="Python runtime is not bundled with Nexus IDE.")
        return f"{python} {quoted}"
    if ext in {".js", ".mjs", ".cjs"}:
        resolved = runtime_registry.resolve("node", "node/node.exe")
        node = _quote(resolved) if resolved else None
        if not node:
            raise HTTPException(status_code=400, detail="Node runtime is not bundled with Nexus IDE.")
        return f"{node} {quoted}"
    if ext == ".ts":
        node_root = runtime_registry.resolve("node", "node/node.exe")
        node_root_dir = node_root.parent if node_root else None
        tsx = None
        if node_root_dir:
            tsx = _quote(node_root_dir / "node_modules" / ".bin" / ("tsx.cmd" if os.name == "nt" else "tsx"))
        if not tsx or not Path(tsx.strip('"')).exists():
            tsx = None
        if tsx:
            return f"{tsx} {quoted}"
        ts_node = None
        if node_root_dir:
            ts_node = _quote(node_root_dir / "node_modules" / ".bin" / ("ts-node.cmd" if os.name == "nt" else "ts-node"))
        if not ts_node or not Path(ts_node.strip('"')).exists():
            ts_node = None
        if ts_node:
            return f"{ts_node} {quoted}"
        raise HTTPException(status_code=400, detail="TypeScript support is not bundled with Nexus IDE.")
    if ext == ".java":
        resolved = runtime_registry.resolve("java", "java/bin/java.exe")
        java = _quote(resolved) if resolved else None
        if not java:
            raise HTTPException(status_code=400, detail="Java runtime is not bundled with Nexus IDE.")
        return f"{java} {quoted}"
    if ext == ".c":
        exe = file_path.with_suffix(".exe" if os.name == "nt" else "")
        resolved = runtime_registry.resolve("gcc", "gcc/bin/gcc.exe")
        gcc = _quote(resolved) if resolved else None
        if not gcc:
            raise HTTPException(status_code=400, detail="C compiler is not bundled with Nexus IDE.")
        return _run_compiled_command(gcc, file_path, exe)
    if ext in {".cpp", ".cc", ".cxx"}:
        exe = file_path.with_suffix(".exe" if os.name == "nt" else "")
        resolved = runtime_registry.resolve("gpp", "gcc/bin/g++.exe") or runtime_registry.resolve("gcc", "gcc/bin/g++.exe")
        gpp = _quote(resolved) if resolved else None
        if not gpp:
            raise HTTPException(status_code=400, detail="C++ compiler is not bundled with Nexus IDE.")
        return _run_compiled_command(gpp, file_path, exe)
    if ext == ".cs":
        exe = file_path.with_suffix(".exe" if os.name == "nt" else "")
        resolved = runtime_registry.resolve("dotnet", "dotnet/sdk/csc.exe")
        csc = _quote(resolved) if resolved else None
        if not csc:
            raise HTTPException(status_code=400, detail="C# compiler is not bundled with Nexus IDE.")
        compile_cmd = f"{csc} /out:{_quote(exe)} {quoted}"
        if os.name == "nt":
            return f"{compile_cmd}; if ($LASTEXITCODE -eq 0) {{ & {_quote(exe)} }}"
        return f"{compile_cmd} && {_quote(exe)}"
    if ext in {".sh", ".bash"}:
        resolved = runtime_registry.resolve("bash", "bash/bin/bash.exe")
        bash = _quote(resolved) if resolved else None
        if not bash:
            raise HTTPException(status_code=400, detail="Bash runtime is not bundled with Nexus IDE.")
        return f"{bash} {quoted}"
    if ext == ".ps1":
        resolved = runtime_registry.resolve("powershell", "powershell/bin/powershell.exe")
        powershell = _quote(resolved) if resolved else None
        if not powershell:
            raise HTTPException(status_code=400, detail="PowerShell runtime is not bundled with Nexus IDE.")
        return f"{powershell} -NoProfile -ExecutionPolicy Bypass -File {quoted}"

    raise HTTPException(status_code=400, detail=f"No run configuration for {ext or 'this file type'}.")


class TerminalSession:
    def __init__(self, session_id: str, cwd: Path, shell: Optional[str] = None):
        if os.name == "nt" and winpty is None:
            raise HTTPException(status_code=500, detail="pywinpty is required for Windows terminal sessions.")

        self.id = session_id
        self.cwd = cwd
        self.shell = shell or _default_shell()
        self.clients: set[asyncio.Queue[str]] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.closed = False
        self._lock = threading.Lock()

        if os.name == "nt":
            self.process = winpty.PTY(cols=100, rows=30)
            self.process.spawn(
                self.shell,
                cwd=str(cwd),
            )
        else:
            from ptyprocess import PtyProcessUnicode

            self.process = PtyProcessUnicode.spawn([self.shell], cwd=str(cwd), dimensions=(30, 100))

        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def attach_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def _read_loop(self):
        while not self.closed and self.process.isalive():
            try:
                if os.name == "nt":
                    data = self.process.read(blocking=False)
                    if not data:
                        time.sleep(0.01)
                        continue
                else:
                    data = self.process.read(1024)
            except Exception:
                break

            if not data:
                continue

            if self.loop:
                for queue in list(self.clients):
                    self.loop.call_soon_threadsafe(queue.put_nowait, data)

        self.closed = True

    def write(self, data: str):
        with self._lock:
            if self.closed or not self.process.isalive():
                raise HTTPException(status_code=410, detail="Terminal session is closed.")
            self.process.write(data)

    def run(self, command: str):
        self.write(command.rstrip() + "\r\n")

    def interrupt(self):
        with self._lock:
            if not self.closed and self.process.isalive():
                if os.name == "nt":
                    self.process.write("\x03")
                else:
                    self.process.sendintr()

    def resize(self, cols: int, rows: int):
        with self._lock:
            if not self.closed and self.process.isalive():
                if os.name == "nt":
                    self.process.set_size(cols, rows)
                else:
                    self.process.setwinsize(rows, cols)

    def kill(self):
        self.closed = True
        with self._lock:
            if self.process.isalive():
                if os.name == "nt":
                    try:
                        os.kill(self.process.pid, signal.SIGTERM)
                    except Exception:
                        pass
                    try:
                        self.process.cancel_io()
                    except Exception:
                        pass
                else:
                    self.process.terminate(force=True)


class TerminalManager:
    def __init__(self):
        self.sessions: Dict[str, TerminalSession] = {}

    def create(self, shell: Optional[str] = None) -> TerminalSession:
        session_id = uuid.uuid4().hex
        session = TerminalSession(session_id, get_project_root(), shell)
        self.sessions[session_id] = session
        return session

    def get(self, session_id: str) -> TerminalSession:
        session = self.sessions.get(session_id)
        if not session or session.closed:
            raise HTTPException(status_code=404, detail="Terminal session not found.")
        return session

    def kill(self, session_id: str):
        session = self.sessions.pop(session_id, None)
        if not session:
            return
        session.kill()

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        session = self.get(session_id)
        session.attach_loop(asyncio.get_running_loop())
        queue: asyncio.Queue[str] = asyncio.Queue()
        session.clients.add(queue)

        async def sender():
            try:
                while True:
                    await websocket.send_text(await queue.get())
            except WebSocketDisconnect:
                pass

        async def receiver():
            try:
                while True:
                    message = await websocket.receive_json()
                    kind = message.get("type")
                    if kind == "input":
                        session.write(message.get("data", ""))
                    elif kind == "resize":
                        session.resize(int(message.get("cols", 100)), int(message.get("rows", 30)))
            except WebSocketDisconnect:
                pass

        sender_task = asyncio.create_task(sender())
        receiver_task = asyncio.create_task(receiver())
        try:
            done, pending = await asyncio.wait(
                {sender_task, receiver_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            await asyncio.gather(*done, return_exceptions=True)
        finally:
            session.clients.discard(queue)


terminal_manager = TerminalManager()
