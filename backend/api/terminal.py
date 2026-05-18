from fastapi import APIRouter, WebSocket
from pydantic import BaseModel
from typing import Optional

from core.terminal_manager import build_run_command, terminal_manager

router = APIRouter()


class TerminalCreateRequest(BaseModel):
    shell: Optional[str] = None


class TerminalInputRequest(BaseModel):
    session_id: str
    data: str


class TerminalRunRequest(BaseModel):
    session_id: str
    path: str


class TerminalResizeRequest(BaseModel):
    session_id: str
    cols: int
    rows: int


@router.post("/terminal/session")
async def create_terminal(req: TerminalCreateRequest):
    session = terminal_manager.create(req.shell)
    return {"session_id": session.id, "cwd": str(session.cwd), "shell": session.shell}


@router.websocket("/terminal/ws/{session_id}")
async def terminal_ws(websocket: WebSocket, session_id: str):
    await terminal_manager.connect(session_id, websocket)


@router.post("/terminal/input")
async def terminal_input(req: TerminalInputRequest):
    terminal_manager.get(req.session_id).write(req.data)
    return {"status": "success"}


@router.post("/terminal/run")
async def terminal_run(req: TerminalRunRequest):
    run_spec = build_run_command(req.path)
    terminal_manager.get(req.session_id).run(run_spec["command"])
    return {
        "status": "success",
        "command": run_spec["command"],
        "provenance": run_spec["provenance"],
    }


@router.post("/terminal/interrupt")
async def terminal_interrupt(req: TerminalInputRequest):
    terminal_manager.get(req.session_id).interrupt()
    return {"status": "success"}


@router.post("/terminal/resize")
async def terminal_resize(req: TerminalResizeRequest):
    terminal_manager.get(req.session_id).resize(req.cols, req.rows)
    return {"status": "success"}


@router.post("/terminal/kill")
async def terminal_kill(req: TerminalInputRequest):
    terminal_manager.kill(req.session_id)
    return {"status": "success"}
