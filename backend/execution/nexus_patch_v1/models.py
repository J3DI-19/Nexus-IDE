from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

TASK_VALUES = {"Feature", "Bugfix", "Refactor", "Analysis"}
OP_TYPES = {"create_file", "edit_file", "delete_file", "rename_file"}
ACTION_TYPES = {
    "insert_before_symbol",
    "insert_after_symbol",
    "replace_symbol",
    "delete_symbol",
    "insert_text",
    "replace_text",
    "delete_text",
    "replace_file",
}


@dataclass
class PatchAction:
    id: str
    type: str
    symbol: Optional[str] = None
    path: Optional[str] = None
    anchor_text: Optional[str] = None
    position: Optional[str] = None
    old_text: Optional[str] = None
    content: Optional[str] = None


@dataclass
class PatchOp:
    id: str
    type: str
    file_path: Optional[str] = None
    from_path: Optional[str] = None
    to_path: Optional[str] = None
    content: Optional[str] = None
    reason: Optional[str] = None
    actions: List[PatchAction] = field(default_factory=list)


@dataclass
class NexusPatch:
    task: str
    goal: str
    ops: List[PatchOp]
