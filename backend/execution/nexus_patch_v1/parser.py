from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html import escape
from typing import List, Tuple

from .errors import PatchIssue
from .models import NexusPatch, PatchAction, PatchOp


def parse_nexus_patch(raw_text: str) -> Tuple[NexusPatch | None, List[PatchIssue]]:
    text = raw_text or ""
    issues: List[PatchIssue] = []

    header = re.search(r"(?m)^\s*NEXUS_PATCH\s+v1\s*$", text)
    if not header:
        return None, [PatchIssue("parser_failed", "error", "Missing NEXUS_PATCH v1 header.")]

    task_match = re.search(r"(?m)^\s*Task:\s*(Feature|Bugfix|Refactor|Analysis)\s*$", text)
    goal_match = re.search(r"(?m)^\s*Goal:\s*(.+?)\s*$", text)
    if not task_match:
        issues.append(PatchIssue("missing_task", "error", "Task must be one of Feature, Bugfix, Refactor, or Analysis."))
    if not goal_match:
        issues.append(PatchIssue("missing_goal", "error", "Goal is required and must be non-empty."))

    patch_match = re.search(r"(?is)<Patch\b[^>]*>.*?</Patch>", text)
    if not patch_match:
        issues.append(PatchIssue("missing_patch", "error", "Patch body must be wrapped in <Patch>...</Patch>."))
        return None, issues

    if any(issue.severity == "error" for issue in issues):
        return None, issues

    xml_text = _protect_raw_content_blocks(patch_match.group(0))
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        return None, [PatchIssue("parser_failed", "error", "Malformed Nexus Patch XML-style tags.", details=str(exc))]

    ops: List[PatchOp] = []
    for op_el in list(root):
        if op_el.tag != "Op":
            issues.append(PatchIssue("unsupported_node", "error", "Only <Op> blocks may appear directly inside <Patch>.", details=op_el.tag))
            continue
        op = PatchOp(
            id=op_el.attrib.get("id", ""),
            type=op_el.attrib.get("type", ""),
        )
        for child in list(op_el):
            if child.tag == "File":
                op.file_path = child.attrib.get("path")
            elif child.tag == "From":
                op.from_path = child.attrib.get("path")
            elif child.tag == "To":
                op.to_path = child.attrib.get("path")
            elif child.tag == "Content":
                op.content = _inner_text(child)
            elif child.tag == "Reason":
                op.reason = _inner_text(child).strip()
            elif child.tag == "Action":
                op.actions.append(_parse_action(child))
            else:
                issues.append(PatchIssue("unsupported_node", "error", "Unsupported tag inside <Op>.", op_id=op.id, details=child.tag))
        ops.append(op)

    patch = NexusPatch(task=task_match.group(1), goal=goal_match.group(1).strip(), ops=ops)
    return patch, issues


def _parse_action(action_el: ET.Element) -> PatchAction:
    action = PatchAction(
        id=action_el.attrib.get("id", ""),
        type=action_el.attrib.get("type", ""),
        symbol=action_el.attrib.get("symbol"),
        path=action_el.attrib.get("path"),
        anchor_text=action_el.attrib.get("anchor_text"),
        position=action_el.attrib.get("position"),
        old_text=action_el.attrib.get("old_text"),
    )
    for child in list(action_el):
        if child.tag == "Content":
            action.content = _inner_text(child)
        elif child.tag == "OldText":
            action.old_text = _inner_text(child)
        elif child.tag == "AnchorText":
            action.anchor_text = _inner_text(child)
    return action


def _inner_text(element: ET.Element) -> str:
    return "".join(element.itertext())


def _protect_raw_content_blocks(xml_text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        open_tag, body, close_tag = match.group(1), match.group(2), match.group(3)
        if body.lstrip().startswith("<![CDATA["):
            return match.group(0)
        return f"{open_tag}{escape(body, quote=False)}{close_tag}"

    return re.sub(r"(?is)(<Content\b[^>]*>)(.*?)(</Content>)", replace, xml_text)
