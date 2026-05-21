from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .errors import PatchIssue
from .models import ACTION_TYPES, OP_TYPES, TASK_VALUES, NexusPatch, PatchAction, PatchOp


def validate_patch(root: Path, patch: NexusPatch) -> List[PatchIssue]:
    issues: List[PatchIssue] = []
    if patch.task not in TASK_VALUES:
        issues.append(PatchIssue("invalid_task", "error", "Task must be Feature, Bugfix, Refactor, or Analysis."))
    if not patch.goal:
        issues.append(PatchIssue("missing_goal", "error", "Goal is required."))
    seen_ids: set[str] = set()
    for op in patch.ops:
        if not op.id:
            issues.append(PatchIssue("missing_op_id", "error", "Every operation must include an id."))
        elif op.id in seen_ids:
            issues.append(PatchIssue("duplicate_op_id", "error", "Operation ids must be unique.", op_id=op.id))
        seen_ids.add(op.id)
        issues.extend(_validate_op(root, op))
    return issues


def _validate_op(root: Path, op: PatchOp) -> List[PatchIssue]:
    issues: List[PatchIssue] = []
    if op.type not in OP_TYPES:
        return [PatchIssue("unsupported_op", "error", "Unsupported Nexus Patch operation type.", op_id=op.id, details=op.type)]

    if op.type in {"create_file", "edit_file", "delete_file"}:
        issues.extend(_validate_path(root, op.file_path, op_id=op.id))
    if op.type == "rename_file":
        issues.extend(_validate_path(root, op.from_path, op_id=op.id))
        issues.extend(_validate_path(root, op.to_path, op_id=op.id))

    if op.type == "create_file":
        if op.content is None:
            issues.append(PatchIssue("missing_content", "error", "create_file requires a <Content> block.", op_id=op.id, path=op.file_path))
    elif op.type == "edit_file":
        if not op.actions:
            issues.append(PatchIssue("missing_actions", "error", "edit_file requires at least one <Action>.", op_id=op.id, path=op.file_path))
        action_ids: set[str] = set()
        for action in op.actions:
            if action.id in action_ids:
                issues.append(PatchIssue("duplicate_action_id", "error", "Action ids must be unique within a patch.", op_id=op.id, action_id=action.id))
            action_ids.add(action.id)
            issues.extend(_validate_action(op, action))
    elif op.type in {"delete_file", "rename_file"} and op.actions:
        issues.append(PatchIssue("unsupported_action_scope", "error", "Actions are only supported inside edit_file operations.", op_id=op.id))

    return issues


def _validate_action(op: PatchOp, action: PatchAction) -> List[PatchIssue]:
    issues: List[PatchIssue] = []
    if not action.id:
        issues.append(PatchIssue("missing_action_id", "error", "Every action must include an id.", op_id=op.id))
    if action.type not in ACTION_TYPES:
        issues.append(PatchIssue("unsupported_action", "error", "Unsupported Nexus Patch action type.", op_id=op.id, action_id=action.id, details=action.type))
        return issues
    if action.path:
        # Action-level paths disambiguate symbols only; they must match the file op for v1.
        if _normalize_rel_path(action.path) != _normalize_rel_path(op.file_path or ""):
            issues.append(PatchIssue("action_path_mismatch", "error", "Action path must match the containing file operation in v1.", op_id=op.id, action_id=action.id, path=action.path))
    if action.type in {"insert_before_symbol", "insert_after_symbol", "replace_symbol", "delete_symbol"} and not action.symbol:
        issues.append(PatchIssue("missing_symbol", "error", "Symbol action requires a symbol attribute.", op_id=op.id, action_id=action.id, path=op.file_path))
    if action.type in {"insert_before_symbol", "insert_after_symbol", "replace_symbol", "insert_text", "replace_text", "replace_file"} and action.content is None:
        issues.append(PatchIssue("missing_content", "error", "This action requires a <Content> block.", op_id=op.id, action_id=action.id, path=op.file_path))
    if action.type == "insert_text":
        if not action.anchor_text:
            issues.append(PatchIssue("missing_anchor_text", "error", "insert_text requires anchor_text or <AnchorText>.", op_id=op.id, action_id=action.id, path=op.file_path))
        if action.position not in {"before", "after"}:
            issues.append(PatchIssue("invalid_position", "error", "insert_text position must be before or after.", op_id=op.id, action_id=action.id, path=op.file_path))
    if action.type in {"replace_text", "delete_text"} and not action.old_text:
        issues.append(PatchIssue("missing_old_text", "error", "replace_text/delete_text requires old_text or <OldText>.", op_id=op.id, action_id=action.id, path=op.file_path))
    return issues


def _validate_path(root: Path, raw_path: Optional[str], op_id: Optional[str] = None) -> List[PatchIssue]:
    if not raw_path or not raw_path.strip():
        return [PatchIssue("missing_path", "error", "A workspace-relative path is required.", op_id=op_id)]
    normalized = _normalize_rel_path(raw_path)
    path = Path(normalized)
    has_drive_prefix = bool(path.parts and ":" in path.parts[0])
    has_colon_segment = any(":" in part for part in path.parts)
    if path.is_absolute() or has_drive_prefix:
        return [PatchIssue("unsafe_path", "error", "Absolute paths are not allowed.", op_id=op_id, path=normalized)]
    if has_colon_segment:
        return [PatchIssue("unsafe_path", "error", "Colon characters are not allowed in Nexus Patch paths.", op_id=op_id, path=normalized)]
    if any(part == ".." for part in path.parts):
        return [PatchIssue("unsafe_path", "error", "Path traversal is not allowed.", op_id=op_id, path=normalized)]
    try:
        target = (root / normalized).resolve()
        target.relative_to(root.resolve())
    except Exception:
        return [PatchIssue("unsafe_path", "error", "Path must stay inside the workspace root.", op_id=op_id, path=normalized)]
    return []


def _normalize_rel_path(raw_path: str) -> str:
    normalized = raw_path.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized
