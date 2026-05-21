from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

from .errors import PatchIssue
from .models import NexusPatch, PatchAction, PatchOp
from .resolver import resolve_symbol
from .validator import validate_patch


@dataclass
class PlannedPatchChange:
    path: str
    content: Optional[str]
    operation: str
    original_content: Optional[str]


def plan_nexus_patch(root: Path, patch: NexusPatch, index: Any = None) -> tuple[List[PlannedPatchChange], List[dict[str, Any]], dict[str, int], List[PatchIssue]]:
    issues = validate_patch(root, patch)
    if issues:
        return [], [], {"additions": 0, "deletions": 0}, issues
    if not patch.ops:
        return [], [], {"additions": 0, "deletions": 0}, [
            PatchIssue("no_changes", "warning", "Nexus Patch contained no operations to apply.")
        ]

    planned: List[PlannedPatchChange] = []
    files_summary: List[dict[str, Any]] = []
    additions = 0
    deletions = 0

    for op in patch.ops:
        op_planned, op_summary, op_issues = _plan_op(root, op, index)
        if op_issues:
            issues.extend(op_issues)
            continue
        if op_planned:
            planned.append(op_planned)
            files_summary.append(op_summary)
            if op_planned.operation == "rename_file":
                add, delete = 0, 0
            else:
                add, delete = _count_diff(op_planned.original_content or "", op_planned.content or "")
            additions += add
            deletions += delete

    return planned, files_summary, {"additions": additions, "deletions": deletions}, issues


def _plan_op(root: Path, op: PatchOp, index: Any) -> tuple[Optional[PlannedPatchChange], dict[str, Any], List[PatchIssue]]:
    if op.type == "create_file":
        rel_path = _normalize_rel_path(op.file_path or "")
        target = root / rel_path
        if target.exists():
            return None, {}, [PatchIssue("path_exists", "error", "create_file target already exists.", op_id=op.id, path=rel_path)]
        return PlannedPatchChange(rel_path, op.content or "", "create_file", None), _summary(op, rel_path), []

    if op.type == "delete_file":
        rel_path = _normalize_rel_path(op.file_path or "")
        target = root / rel_path
        if not target.is_file():
            return None, {}, [PatchIssue("missing_path", "error", "delete_file target must exist and be a file.", op_id=op.id, path=rel_path)]
        return PlannedPatchChange(rel_path, None, "delete_file", target.read_text(encoding="utf-8")), _summary(op, rel_path), []

    if op.type == "rename_file":
        old_path = _normalize_rel_path(op.from_path or "")
        new_path = _normalize_rel_path(op.to_path or "")
        old_target = root / old_path
        new_target = root / new_path
        if not old_target.is_file():
            return None, {}, [PatchIssue("missing_path", "error", "rename_file source must exist and be a file.", op_id=op.id, path=old_path)]
        if new_target.exists():
            return None, {}, [PatchIssue("path_exists", "error", "rename_file destination already exists.", op_id=op.id, path=new_path)]
        content = old_target.read_text(encoding="utf-8")
        return PlannedPatchChange(old_path, new_path, "rename_file", content), _summary(op, f"{old_path} -> {new_path}"), []

    rel_path = _normalize_rel_path(op.file_path or "")
    target = root / rel_path
    if not target.is_file():
        return None, {}, [PatchIssue("missing_path", "error", "edit_file target must exist and be a file.", op_id=op.id, path=rel_path)]
    original = target.read_text(encoding="utf-8")
    current = original
    issues: List[PatchIssue] = []
    for action in op.actions:
        current, action_issues = _apply_action(current, rel_path, action, index)
        issues.extend(action_issues)
        if action_issues:
            break
    if issues:
        return None, {}, issues
    return PlannedPatchChange(rel_path, current, "edit_file", original), _summary(op, rel_path), []


def _apply_action(content: str, rel_path: str, action: PatchAction, index: Any) -> tuple[str, List[PatchIssue]]:
    if action.type == "replace_file":
        return action.content or "", []

    if action.type in {"insert_before_symbol", "insert_after_symbol", "replace_symbol", "delete_symbol"}:
        resolved, issues = resolve_symbol(index, rel_path, action.symbol or "")
        if issues:
            for issue in issues:
                issue.action_id = action.id
                issue.path = rel_path
            return content, issues
        assert resolved is not None
        lines = content.splitlines(keepends=True)
        start = max(0, resolved.start_line - 1)
        end = min(len(lines), resolved.end_line)
        payload = _ensure_trailing_newline(action.content or "")
        if action.type == "insert_before_symbol":
            return "".join(lines[:start]) + payload + "".join(lines[start:]), []
        if action.type == "insert_after_symbol":
            return "".join(lines[:end]) + payload + "".join(lines[end:]), []
        if action.type == "replace_symbol":
            return "".join(lines[:start]) + payload + "".join(lines[end:]), []
        if action.type == "delete_symbol":
            return "".join(lines[:start]) + "".join(lines[end:]), []

    if action.type == "insert_text":
        anchor = action.anchor_text or ""
        count = content.count(anchor)
        if count != 1:
            code = "anchor_not_found" if count == 0 else "anchor_ambiguous"
            return content, [PatchIssue(code, "error", "insert_text anchor must match exactly once.", action_id=action.id, path=rel_path, details=anchor)]
        idx = content.index(anchor)
        insert = action.content or ""
        if action.position == "after":
            idx += len(anchor)
        return content[:idx] + insert + content[idx:], []

    if action.type in {"replace_text", "delete_text"}:
        old = action.old_text or ""
        count = content.count(old)
        if count != 1:
            code = "old_text_not_found" if count == 0 else "old_text_ambiguous"
            return content, [PatchIssue(code, "error", "Text target must match exactly once.", action_id=action.id, path=rel_path, details=old)]
        new = "" if action.type == "delete_text" else (action.content or "")
        return content.replace(old, new, 1), []

    return content, [PatchIssue("unsupported_action", "error", "Unsupported action.", action_id=action.id, path=rel_path, details=action.type)]


def _summary(op: PatchOp, path: str) -> dict[str, Any]:
    return {
        "path": path,
        "op_id": op.id,
        "operation": op.type,
        "hunk_count": max(1, len(op.actions)),
        "action_count": len(op.actions),
    }


def _count_diff(before: str, after: str) -> tuple[int, int]:
    additions = 0
    deletions = 0
    diff = difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="")
    for line in diff:
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def _ensure_trailing_newline(value: str) -> str:
    if not value:
        return value
    return value if value.endswith("\n") else value + "\n"


def _normalize_rel_path(raw_path: str) -> str:
    normalized = raw_path.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized
