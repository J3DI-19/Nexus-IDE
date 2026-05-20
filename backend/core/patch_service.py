from __future__ import annotations

import json
import re
import time
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


Issue = Dict[str, Any]


@dataclass
class PlannedChange:
    path: str
    content: Optional[str]
    operation: str
    original_content: Optional[str]


class PatchService:
    _ALLOWED_EDIT_OPS = {"replace_range", "insert_after", "insert_before", "create_file", "delete_file"}
    _ALLOWED_ROOT_KEYS = {"format", "edits", "assert_contains", "assert_not_contains"}
    _ALLOWED_EDIT_KEYS = {
        "path",
        "op",
        "old_text",
        "new_text",
        "anchor_text",
        "assert_contains",
        "assert_not_contains",
    }
    _OP_REQUIRED_KEYS = {
        "replace_range": {"path", "op", "old_text", "new_text"},
        "insert_after": {"path", "op", "anchor_text", "new_text"},
        "insert_before": {"path", "op", "anchor_text", "new_text"},
        "create_file": {"path", "op", "new_text"},
        "delete_file": {"path", "op"},
    }

    def __init__(self) -> None:
        self._metrics: Dict[str, int] = {
            "parse_fail_rate": 0,
            "intent_block_rate": 0,
            "verify_fail_rate": 0,
            "rollback_rate": 0,
            "warning_only_apply_rate": 0,
        }

    def normalize_payload(self, raw_text: str, response_format: str = "unified_diff", auto_extract: bool = False) -> dict[str, Any]:
        warnings: List[Issue] = []
        text = raw_text or ""
        detected_format = response_format

        if auto_extract:
            extracted, found = self._extract_payload(text, response_format)
            if found:
                text = extracted
                warnings.append(self._issue("auto_extracted_payload", "warning"))

        if response_format == "nexus_edits_v2":
            text, repaired = self._repair_unescaped_quotes(text)
            if repaired:
                warnings.append(self._issue("repaired_unescaped_quotes", "warning"))

            if text.strip():
                try:
                    parsed = json.loads(text)
                    normalized, compat_warnings = self._normalize_nexus_payload(parsed)
                    warnings.extend(compat_warnings)
                    text = json.dumps(normalized, ensure_ascii=False)
                except Exception:
                    pass

        return {"detected_format": detected_format, "normalized_text": text, "issues": warnings}

    def preview(
        self,
        root: Path,
        raw_text: str,
        response_format: str = "unified_diff",
        auto_extract: bool = False,
        task: Optional[str] = None,
        mode: str = "feature",
        active_file: Optional[str] = None,
        assert_contains: Optional[List[str]] = None,
        assert_not_contains: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        result = self._run_pipeline(
            root=root,
            raw_text=raw_text,
            response_format=response_format,
            auto_extract=auto_extract,
            task=task or "",
            mode=mode or "feature",
            active_file=active_file,
            explicit_assert_contains=assert_contains or [],
            explicit_assert_not_contains=assert_not_contains or [],
        )
        result.pop("_planned_changes", None)
        return result

    def apply(
        self,
        root: Path,
        raw_text: str,
        selected_paths: Optional[List[str]] = None,
        response_format: str = "unified_diff",
        auto_extract: bool = False,
        task: Optional[str] = None,
        mode: str = "feature",
        active_file: Optional[str] = None,
        assert_contains: Optional[List[str]] = None,
        assert_not_contains: Optional[List[str]] = None,
    ) -> Tuple[dict[str, Any], List[str], List[PlannedChange]]:
        pipeline = self._run_pipeline(
            root=root,
            raw_text=raw_text,
            response_format=response_format,
            auto_extract=auto_extract,
            task=task or "",
            mode=mode or "feature",
            active_file=active_file,
            explicit_assert_contains=assert_contains or [],
            explicit_assert_not_contains=assert_not_contains or [],
        )
        planned_changes: List[PlannedChange] = pipeline.pop("_planned_changes", [])
        if not pipeline["can_apply"]:
            pipeline["results"] = []
            return pipeline, [], []

        selected_set = {self._normalize_rel_path(path) for path in (selected_paths or []) if path}
        changes_to_apply = [c for c in planned_changes if not selected_set or c.path in selected_set]
        if not changes_to_apply:
            result = {
                **pipeline,
                "results": [],
                "can_apply": False,
                "blockers": [self._issue("no_selected_changes", "error")],
                "blocked_stage": "validate",
            }
            result["issues"] = result.get("warnings", []) + result.get("blockers", [])
            return result, [], []

        results: List[Dict[str, str]] = []
        changed_paths: List[str] = []
        try:
            for change in changes_to_apply:
                target = (root / change.path).resolve()
                if not self._is_within_root(root, target):
                    raise RuntimeError("unsafe path outside workspace")

                if change.content is None:
                    if target.exists():
                        target.unlink()
                    results.append({"path": change.path, "status": "deleted"})
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(change.content, encoding="utf-8")
                    status = "created" if change.operation == "create_file" else "updated"
                    results.append({"path": change.path, "status": status})
                changed_paths.append(change.path)
        except Exception as exc:
            result = {
                **pipeline,
                "results": results,
                "can_apply": False,
                "blockers": [self._issue("apply_failed", "error", details=str(exc))],
                "blocked_stage": "apply",
            }
            result["issues"] = result.get("warnings", []) + result.get("blockers", [])
            return result, [], []

        result = {**pipeline, "results": results}
        if result.get("warnings") and not result.get("blockers"):
            self._bump_metric("warning_only_apply_rate")
        return result, changed_paths, changes_to_apply

    def verify_applied(
        self,
        root: Path,
        applied_changes: List[PlannedChange],
        intent_checks: dict[str, Any],
        mode: str,
    ) -> List[Issue]:
        blockers: List[Issue] = []
        for change in applied_changes:
            target = (root / change.path).resolve()
            if change.content is None:
                if target.exists():
                    blockers.append(self._issue("verify_failed", "error", path=change.path, details="file still exists after delete"))
            else:
                if not target.exists():
                    blockers.append(self._issue("verify_failed", "error", path=change.path, details="file missing after apply"))
                elif target.is_dir():
                    blockers.append(self._issue("verify_failed", "error", path=change.path, details="path became directory"))
                else:
                    text = target.read_text(encoding="utf-8")
                    syntax_issue = self._verify_syntax_for_path(change.path, text)
                    if syntax_issue:
                        blockers.append(self._issue("verify_failed", "error", path=change.path, details=syntax_issue))

        rendered = self._collect_rendered_text(root, applied_changes)
        assertion_blockers = self._evaluate_intent(intent_checks, rendered, mode=mode)
        if assertion_blockers:
            for b in assertion_blockers:
                blockers.append(self._issue("verify_failed", "error", details=b.get("details"), path=b.get("path")))
        if blockers:
            self._bump_metric("verify_fail_rate")
        return blockers

    def rollback_changes(self, root: Path, applied_changes: List[PlannedChange]) -> bool:
        try:
            for change in applied_changes:
                target = (root / change.path).resolve()
                if change.original_content is None:
                    if target.exists():
                        target.unlink()
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(change.original_content, encoding="utf-8")
            self._bump_metric("rollback_rate")
            return True
        except Exception:
            return False

    def get_metrics(self) -> Dict[str, int]:
        return dict(self._metrics)

    def _run_pipeline(
        self,
        root: Path,
        raw_text: str,
        response_format: str,
        auto_extract: bool,
        task: str,
        mode: str,
        active_file: Optional[str],
        explicit_assert_contains: List[str],
        explicit_assert_not_contains: List[str],
    ) -> dict[str, Any]:
        stage_timings: Dict[str, float] = {}
        warnings: List[Issue] = []
        blockers: List[Issue] = []
        blocked_stage: Optional[str] = None
        planned_changes: List[PlannedChange] = []
        files_summary: List[Dict[str, Any]] = []
        stats = {"additions": 0, "deletions": 0}

        start = time.perf_counter()
        normalized = self.normalize_payload(raw_text, response_format=response_format, auto_extract=auto_extract)
        stage_timings["normalize"] = round((time.perf_counter() - start) * 1000.0, 2)
        warnings.extend(normalized.get("issues", []))
        normalized_text = normalized.get("normalized_text", "")

        start = time.perf_counter()
        parsed_payload: Optional[dict[str, Any]] = None
        if response_format == "nexus_edits_v2":
            try:
                parsed_payload = json.loads(normalized_text)
            except Exception as exc:
                blockers.append(self._issue("invalid_json", "error", details=str(exc)))
                blocked_stage = "parse"
                self._bump_metric("parse_fail_rate")
        else:
            try:
                parsed_payload = self._parse_unified_diff(normalized_text)
            except ValueError as exc:
                blockers.append(self._issue("invalid_diff", "error", details=str(exc)))
                blocked_stage = "parse"
                self._bump_metric("parse_fail_rate")
        stage_timings["parse"] = round((time.perf_counter() - start) * 1000.0, 2)

        payload_assertions = {"assert_contains": [], "assert_not_contains": []}
        validation_blockers: List[Issue] = []
        if not blockers and parsed_payload is not None:
            start = time.perf_counter()
            if response_format == "nexus_edits_v2":
                (
                    planned_changes,
                    files_summary,
                    stats,
                    validation_warnings,
                    validation_blockers,
                    payload_assertions,
                ) = self._plan_nexus_changes(root, parsed_payload)
                warnings.extend(validation_warnings)
                blockers.extend(validation_blockers)
            else:
                planned_changes, files_summary, stats, validation_blockers = self._plan_unified_diff_changes(root, parsed_payload)
                blockers.extend(validation_blockers)
            if validation_blockers:
                blocked_stage = blocked_stage or "validate"
            stage_timings["validate"] = round((time.perf_counter() - start) * 1000.0, 2)

        # Explicit simulate stage: in-memory candidate output inspection before intent checks.
        start = time.perf_counter()
        simulation_blob = "\n".join(change.content or "" for change in planned_changes)
        stage_timings["simulate"] = round((time.perf_counter() - start) * 1000.0, 2)

        assertions = self._compile_assertions(
            task=task,
            mode=mode,
            active_file=active_file,
            payload_assert_contains=payload_assertions["assert_contains"],
            payload_assert_not_contains=payload_assertions["assert_not_contains"],
            explicit_assert_contains=explicit_assert_contains,
            explicit_assert_not_contains=explicit_assert_not_contains,
        )
        warnings.extend(assertions["warnings"])

        if not blockers:
            start = time.perf_counter()
            intent_blockers = self._evaluate_intent(assertions["intent_checks"], simulation_blob, mode=mode)
            stage_timings["intent_guard"] = round((time.perf_counter() - start) * 1000.0, 2)
            if intent_blockers:
                blockers.extend(intent_blockers)
                blocked_stage = blocked_stage or "intent_guard"
                self._bump_metric("intent_block_rate")

        can_apply = len(blockers) == 0
        return {
            "files": files_summary,
            "stats": stats,
            "warnings": warnings,
            "blockers": blockers,
            "issues": warnings + blockers,
            "can_apply": can_apply,
            "intent_checks": assertions["intent_checks"],
            "blocked_stage": blocked_stage,
            "stage_timings_ms": stage_timings,
            "_planned_changes": planned_changes,
        }

    def _compile_assertions(
        self,
        task: str,
        mode: str,
        active_file: Optional[str],
        payload_assert_contains: List[str],
        payload_assert_not_contains: List[str],
        explicit_assert_contains: List[str],
        explicit_assert_not_contains: List[str],
    ) -> dict[str, Any]:
        warnings: List[Issue] = []
        derived = self._derive_task_intent_checks(task, mode, active_file)
        required_contains: List[str] = []
        required_absent: List[str] = []

        required_contains.extend(payload_assert_contains)
        required_absent.extend(payload_assert_not_contains)
        required_contains.extend(explicit_assert_contains)
        required_absent.extend(explicit_assert_not_contains)

        if derived["enforce"]:
            required_contains.extend(derived["required_contains"])
            required_absent.extend(derived["required_absent"])
        else:
            if derived["required_contains"] or derived["required_absent"]:
                warnings.append(
                    self._issue(
                        "intent_hint_non_blocking",
                        "warning",
                        details="Derived assertions were low confidence and treated as hints.",
                    )
                )

        required_contains = self._dedupe([v for v in required_contains if v])
        required_absent = self._dedupe([v for v in required_absent if v])

        intent_checks = {
            "required_contains": required_contains,
            "required_absent": required_absent,
            "provenance": {
                "derived": {
                    "required_contains": derived["required_contains"],
                    "required_absent": derived["required_absent"],
                    "confidence": derived["confidence"],
                    "enforced": derived["enforce"],
                },
                "model": {
                    "required_contains": payload_assert_contains,
                    "required_absent": payload_assert_not_contains,
                },
                "user": {
                    "required_contains": explicit_assert_contains,
                    "required_absent": explicit_assert_not_contains,
                },
            },
        }
        return {"intent_checks": intent_checks, "warnings": warnings}

    def _plan_nexus_changes(
        self,
        root: Path,
        parsed_payload: dict[str, Any],
    ) -> Tuple[List[PlannedChange], List[Dict[str, Any]], Dict[str, int], List[Issue], List[Issue], Dict[str, List[str]]]:
        warnings: List[Issue] = []
        blockers: List[Issue] = []
        normalized_payload, compat_warnings = self._normalize_nexus_payload(parsed_payload)
        warnings.extend(compat_warnings)

        for key in normalized_payload.keys():
            if key not in self._ALLOWED_ROOT_KEYS:
                blockers.append(self._issue("unsupported_root_field", "error", details=key))

        if normalized_payload.get("format") != "nexus_edits_v2":
            blockers.append(self._issue("invalid_format", "error"))
            return [], [], {"additions": 0, "deletions": 0}, warnings, blockers, {"assert_contains": [], "assert_not_contains": []}

        edits = normalized_payload.get("edits")
        if not isinstance(edits, list):
            blockers.append(self._issue("invalid_edits", "error"))
            return [], [], {"additions": 0, "deletions": 0}, warnings, blockers, {"assert_contains": [], "assert_not_contains": []}

        root_assert_contains = self._as_string_list(normalized_payload.get("assert_contains"))
        root_assert_not_contains = self._as_string_list(normalized_payload.get("assert_not_contains"))
        file_buffers: Dict[str, Optional[str]] = {}
        original_map: Dict[str, Optional[str]] = {}
        planned: Dict[str, PlannedChange] = {}
        file_hunk_counts: Dict[str, int] = {}
        additions = 0
        deletions = 0
        payload_assert_contains = list(root_assert_contains)
        payload_assert_not_contains = list(root_assert_not_contains)

        for idx, edit in enumerate(edits, start=1):
            if not isinstance(edit, dict):
                blockers.append(self._issue("invalid_edit_object", "error", line=idx))
                continue

            unknown_fields = [k for k in edit.keys() if k not in self._ALLOWED_EDIT_KEYS]
            if unknown_fields:
                blockers.append(self._issue("unsupported_edit_field", "error", line=idx, details=", ".join(sorted(unknown_fields))))
                continue

            op = edit.get("op")
            if op not in self._ALLOWED_EDIT_OPS:
                blockers.append(self._issue("unsupported_op", "error", line=idx, details=str(op)))
                continue

            required = self._OP_REQUIRED_KEYS.get(str(op), {"path", "op"})
            missing = [k for k in required if k not in edit]
            if missing:
                blockers.append(self._issue("missing_required_field", "error", line=idx, details=", ".join(sorted(missing))))
                continue

            raw_path = edit.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                blockers.append(self._issue("missing_path", "error", line=idx))
                continue
            path = self._normalize_rel_path(raw_path)
            target = (root / path).resolve()
            if not self._is_within_root(root, target):
                blockers.append(self._issue("unsafe_path", "error", path=raw_path))
                continue

            payload_assert_contains.extend(self._as_string_list(edit.get("assert_contains")))
            payload_assert_not_contains.extend(self._as_string_list(edit.get("assert_not_contains")))

            if path not in file_buffers:
                if target.exists():
                    if target.is_dir():
                        blockers.append(self._issue("path_type_mismatch", "error", path=path))
                        continue
                    file_buffers[path] = target.read_text(encoding="utf-8")
                else:
                    file_buffers[path] = None
                original_map[path] = file_buffers[path]

            current = file_buffers[path]
            next_value = current
            if op == "replace_range":
                old_text = edit.get("old_text")
                new_text = edit.get("new_text")
                if not isinstance(old_text, str) or not isinstance(new_text, str):
                    blockers.append(self._issue("invalid_replace_fields", "error", path=path))
                    continue
                if current is None:
                    blockers.append(self._issue("missing_path", "error", path=path))
                    continue
                if old_text not in current:
                    blockers.append(self._issue("edit_mismatch", "error", path=path, details="old_text not found"))
                    continue
                next_value = current.replace(old_text, new_text, 1)
                additions += max(0, new_text.count("\n") - old_text.count("\n"))
                deletions += max(0, old_text.count("\n") - new_text.count("\n"))
            elif op == "insert_after":
                anchor = edit.get("anchor_text")
                new_text = edit.get("new_text")
                if not isinstance(anchor, str) or not isinstance(new_text, str):
                    blockers.append(self._issue("invalid_insert_fields", "error", path=path))
                    continue
                if current is None:
                    blockers.append(self._issue("missing_path", "error", path=path))
                    continue
                anchor_index = current.find(anchor)
                if anchor_index < 0:
                    blockers.append(self._issue("anchor_not_found", "error", path=path))
                    continue
                insert_at = anchor_index + len(anchor)
                next_value = current[:insert_at] + new_text + current[insert_at:]
                additions += max(1, new_text.count("\n"))
            elif op == "insert_before":
                anchor = edit.get("anchor_text")
                new_text = edit.get("new_text")
                if not isinstance(anchor, str) or not isinstance(new_text, str):
                    blockers.append(self._issue("invalid_insert_fields", "error", path=path))
                    continue
                if current is None:
                    blockers.append(self._issue("missing_path", "error", path=path))
                    continue
                anchor_index = current.find(anchor)
                if anchor_index < 0:
                    blockers.append(self._issue("anchor_not_found", "error", path=path))
                    continue
                next_value = current[:anchor_index] + new_text + current[anchor_index:]
                additions += max(1, new_text.count("\n"))
            elif op == "create_file":
                new_text = edit.get("new_text")
                if not isinstance(new_text, str):
                    blockers.append(self._issue("invalid_create_fields", "error", path=path))
                    continue
                if current is not None:
                    blockers.append(self._issue("path_exists", "error", path=path))
                    continue
                next_value = new_text
                additions += max(1, new_text.count("\n"))
            elif op == "delete_file":
                if current is None:
                    blockers.append(self._issue("missing_path", "error", path=path))
                    continue
                deletions += max(1, current.count("\n"))
                next_value = None

            file_buffers[path] = next_value
            planned[path] = PlannedChange(
                path=path,
                content=next_value,
                operation=op,
                original_content=original_map.get(path),
            )
            file_hunk_counts[path] = file_hunk_counts.get(path, 0) + 1

        files = [{"path": path, "hunk_count": count} for path, count in sorted(file_hunk_counts.items())]
        stats = {"additions": additions, "deletions": deletions}
        payload_assertions = {
            "assert_contains": self._dedupe(payload_assert_contains),
            "assert_not_contains": self._dedupe(payload_assert_not_contains),
        }
        return list(planned.values()), files, stats, warnings, blockers, payload_assertions

    def _plan_unified_diff_changes(
        self,
        root: Path,
        parsed_payload: dict[str, Any],
    ) -> Tuple[List[PlannedChange], List[Dict[str, Any]], Dict[str, int], List[Issue]]:
        blockers: List[Issue] = []
        files_summary: List[Dict[str, Any]] = []
        planned_changes: List[PlannedChange] = []
        additions = 0
        deletions = 0

        for patch in parsed_payload.get("files", []):
            old_path = patch.get("old_path")
            new_path = patch.get("new_path")
            path = new_path if new_path != "/dev/null" else old_path
            if not isinstance(path, str):
                blockers.append(self._issue("missing_path", "error"))
                continue
            rel_path = self._normalize_rel_path(path)
            target = (root / rel_path).resolve()
            if not self._is_within_root(root, target):
                blockers.append(self._issue("unsafe_path", "error", path=rel_path))
                continue

            if old_path == "/dev/null":
                original_text = ""
                original_value: Optional[str] = None
                operation = "create_file"
            else:
                if not target.exists():
                    blockers.append(self._issue("missing_path", "error", path=rel_path))
                    continue
                if target.is_dir():
                    blockers.append(self._issue("path_type_mismatch", "error", path=rel_path))
                    continue
                original_text = target.read_text(encoding="utf-8")
                original_value = original_text
                operation = "replace_range"

            if new_path == "/dev/null":
                planned_changes.append(PlannedChange(path=rel_path, content=None, operation="delete_file", original_content=original_value))
                files_summary.append({"path": rel_path, "hunk_count": len(patch.get("hunks", []))})
                continue

            patched, file_blockers = self._apply_hunks_in_memory(
                original_text=original_text,
                hunks=patch.get("hunks", []),
                path=rel_path,
            )
            if file_blockers:
                blockers.extend(file_blockers)
                continue
            planned_changes.append(
                PlannedChange(path=rel_path, content=patched, operation=operation, original_content=original_value)
            )
            files_summary.append({"path": rel_path, "hunk_count": len(patch.get("hunks", []))})
            for hunk in patch.get("hunks", []):
                for line in hunk.get("lines", []):
                    if line.startswith("+"):
                        additions += 1
                    elif line.startswith("-"):
                        deletions += 1

        return planned_changes, files_summary, {"additions": additions, "deletions": deletions}, blockers

    def _apply_hunks_in_memory(self, original_text: str, hunks: List[dict[str, Any]], path: str) -> Tuple[str, List[Issue]]:
        blockers: List[Issue] = []
        lines = original_text.splitlines(keepends=False)
        offset = 0

        for hunk in hunks:
            start = int(hunk.get("old_start", 1))
            idx = max(0, start - 1 + offset)
            for raw in hunk.get("lines", []):
                if not raw:
                    blockers.append(self._issue("invalid_hunk_line", "error", path=path))
                    continue
                marker = raw[0]
                value = raw[1:]
                if marker == " ":
                    if idx >= len(lines) or lines[idx] != value:
                        blockers.append(self._issue("hunk_context_mismatch", "error", path=path))
                        break
                    idx += 1
                elif marker == "-":
                    if idx >= len(lines) or lines[idx] != value:
                        blockers.append(self._issue("hunk_remove_mismatch", "error", path=path))
                        break
                    lines.pop(idx)
                    offset -= 1
                elif marker == "+":
                    lines.insert(idx, value)
                    idx += 1
                    offset += 1
                elif marker == "\\":
                    continue
                else:
                    blockers.append(self._issue("invalid_hunk_line", "error", path=path))
                    break
            if blockers:
                break
        rendered = "\n".join(lines)
        if original_text.endswith("\n"):
            rendered += "\n"
        return rendered, blockers

    def _parse_unified_diff(self, text: str) -> dict[str, Any]:
        lines = text.splitlines()
        if not lines:
            raise ValueError("empty diff")
        files: List[Dict[str, Any]] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line.startswith("--- "):
                i += 1
                continue
            old_token = line[4:].strip()
            i += 1
            if i >= len(lines) or not lines[i].startswith("+++ "):
                raise ValueError("missing +++ marker")
            new_token = lines[i][4:].strip()
            old_path = self._normalize_diff_path(old_token)
            new_path = self._normalize_diff_path(new_token)
            i += 1
            hunks: List[Dict[str, Any]] = []
            while i < len(lines):
                current = lines[i]
                if current.startswith("--- "):
                    break
                if current.startswith("@@"):
                    header = current
                    match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", header)
                    if not match:
                        raise ValueError(f"invalid hunk header: {header}")
                    old_start = int(match.group(1))
                    old_count = int(match.group(2) or "1")
                    new_start = int(match.group(3))
                    new_count = int(match.group(4) or "1")
                    i += 1
                    hunk_lines: List[str] = []
                    while i < len(lines):
                        hline = lines[i]
                        if hline.startswith("@@") or hline.startswith("--- "):
                            break
                        if hline and hline[0] not in {" ", "+", "-", "\\"}:
                            raise ValueError(f"invalid_hunk_line@{i + 1}")
                        hunk_lines.append(hline)
                        i += 1
                    hunks.append(
                        {
                            "old_start": old_start,
                            "old_count": old_count,
                            "new_start": new_start,
                            "new_count": new_count,
                            "lines": hunk_lines,
                        }
                    )
                    continue
                i += 1
            files.append({"old_path": old_path, "new_path": new_path, "hunks": hunks})
        if not files:
            raise ValueError("no file patches found")
        return {"files": files}

    def _normalize_nexus_payload(self, payload: dict[str, Any]) -> Tuple[dict[str, Any], List[Issue]]:
        warnings: List[Issue] = []
        normalized: dict[str, Any] = {"format": payload.get("format"), "edits": []}
        if "assert_contains" in payload:
            normalized["assert_contains"] = self._as_string_list(payload.get("assert_contains"))
        if "assert_not_contains" in payload:
            normalized["assert_not_contains"] = self._as_string_list(payload.get("assert_not_contains"))

        raw_edits = payload.get("edits", [])
        if not isinstance(raw_edits, list):
            return normalized, warnings

        for entry in raw_edits:
            if not isinstance(entry, dict):
                continue
            entry_path = entry.get("path") or entry.get("file")
            if entry.get("file") and not entry.get("path"):
                warnings.append(self._issue("normalized_file_to_path", "warning"))
            nested_ops = entry.get("ops")
            if isinstance(nested_ops, list):
                warnings.append(self._issue("flattened_nested_ops", "warning"))
                for op in nested_ops:
                    if not isinstance(op, dict):
                        continue
                    if op.get("op") == "replace":
                        warnings.append(self._issue("normalized_legacy_replace_op", "warning"))
                    if "text" in op and "new_text" not in op:
                        warnings.append(self._issue("normalized_text_to_new_text", "warning"))
                    normalized_op = self._normalize_single_edit({**op, "path": entry_path})
                    normalized["edits"].append(normalized_op)
                continue
            if entry.get("op") == "replace":
                warnings.append(self._issue("normalized_legacy_replace_op", "warning"))
            if "text" in entry and "new_text" not in entry:
                warnings.append(self._issue("normalized_text_to_new_text", "warning"))
            normalized_op = self._normalize_single_edit(entry)
            normalized["edits"].append(normalized_op)
        return normalized, warnings

    def _normalize_single_edit(self, edit: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(edit)
        if "file" in normalized and "path" not in normalized:
            normalized["path"] = normalized.get("file")
        normalized.pop("file", None)
        normalized.pop("ops", None)
        if normalized.get("op") == "replace":
            normalized["op"] = "replace_range"
        if "text" in normalized and "new_text" not in normalized:
            normalized["new_text"] = normalized.get("text")
        normalized.pop("text", None)
        return normalized

    def _repair_unescaped_quotes(self, raw: str) -> Tuple[str, bool]:
        text = raw
        repaired_any = False
        for key in ("old_text", "new_text", "anchor_text"):
            text, repaired = self._repair_key_value_quotes(text, key)
            repaired_any = repaired_any or repaired
        return text, repaired_any

    def _repair_key_value_quotes(self, raw: str, key: str) -> Tuple[str, bool]:
        pattern = f"\"{key}\":\""
        idx = 0
        repaired = False
        out = raw
        while True:
            start = out.find(pattern, idx)
            if start == -1:
                break
            cursor = start + len(pattern)
            chars = list(out)
            i = cursor
            while i < len(chars):
                ch = chars[i]
                if ch == "\\":
                    i += 2
                    continue
                if ch == "\"":
                    j = i + 1
                    while j < len(chars) and chars[j].isspace():
                        j += 1
                    if j < len(chars) and chars[j] in {",", "}"}:
                        break
                    chars.insert(i, "\\")
                    repaired = True
                    i += 2
                    continue
                i += 1
            out = "".join(chars)
            idx = i + 1
        return out, repaired

    def _extract_payload(self, raw_text: str, response_format: str) -> Tuple[str, bool]:
        text = raw_text or ""
        if response_format == "unified_diff":
            match = re.search(r"(?ms)^--- .*$", text)
            if match:
                return text[match.start():].strip(), True
            return text, False
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start : end + 1].strip(), True
        return text, False

    def _derive_task_intent_checks(self, task: str, mode: str, active_file: Optional[str]) -> dict[str, Any]:
        if (mode or "").lower() != "feature":
            return {"required_contains": [], "required_absent": [], "confidence": 0.0, "enforce": False}
        lowered = (task or "").lower()
        contains: List[str] = []
        absent: List[str] = []
        confidence = 0.0

        if "squar" in lowered:
            contains.extend(["^2", 'operation == "^2"'])
            absent.append('operation == "^"')
            confidence = 0.95 if active_file and active_file.endswith(".py") else 0.9

        return {"required_contains": contains, "required_absent": absent, "confidence": confidence, "enforce": confidence >= 0.8}

    def _evaluate_intent(self, checks: dict[str, Any], post_apply_text: str, mode: str) -> List[Issue]:
        if (mode or "").lower() == "architecture":
            return []
        blockers: List[Issue] = []
        for token in checks.get("required_contains", []):
            if token and token not in post_apply_text:
                blockers.append(self._issue("intent_mismatch", "error", details=f"missing required token: {token}"))
        for token in checks.get("required_absent", []):
            if token and token in post_apply_text:
                blockers.append(self._issue("intent_mismatch", "error", details=f"forbidden token present: {token}"))
        return blockers

    def _collect_rendered_text(self, root: Path, changes: List[PlannedChange]) -> str:
        blocks: List[str] = []
        for change in changes:
            target = (root / change.path).resolve()
            if not target.exists() or target.is_dir():
                continue
            text = target.read_text(encoding="utf-8")
            blocks.append(f"### {change.path}\n{text}")
        return "\n".join(blocks)

    def _normalize_diff_path(self, token: str) -> str:
        value = token.strip()
        if value == "/dev/null":
            return value
        if value.startswith("a/") or value.startswith("b/"):
            return value[2:]
        return value

    def _normalize_rel_path(self, raw_path: str) -> str:
        normalized = raw_path.replace("\\", "/").strip()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized

    def _is_within_root(self, root: Path, target: Path) -> bool:
        try:
            target.relative_to(root.resolve())
            return True
        except Exception:
            return False

    def _as_string_list(self, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(v) for v in value if isinstance(v, str) and v]

    def _dedupe(self, values: List[str]) -> List[str]:
        seen: set[str] = set()
        ordered: List[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered

    def _issue(self, reason: str, severity: str, **kwargs: Any) -> Issue:
        issue: Issue = {"reason": reason, "code": reason, "severity": severity}
        issue.update(kwargs)
        issue["fix_suggestion"] = self._fix_suggestion(reason)
        return issue

    def _bump_metric(self, key: str) -> None:
        self._metrics[key] = self._metrics.get(key, 0) + 1

    def _verify_syntax_for_path(self, rel_path: str, text: str) -> Optional[str]:
        lower = rel_path.lower()
        try:
            if lower.endswith(".py"):
                ast.parse(text)
            elif lower.endswith(".json"):
                json.loads(text)
        except Exception as exc:
            return f"syntax check failed: {exc}"
        return None

    def _fix_suggestion(self, reason: str) -> str:
        mapping = {
            "invalid_json": "Return strict JSON only; escape quotes and newlines in string fields.",
            "invalid_diff": "Ensure unified diff has valid --- / +++ / @@ markers.",
            "unsupported_op": "Use one of: replace_range, insert_after, insert_before, create_file, delete_file.",
            "unsupported_edit_field": "Remove unknown edit keys and keep canonical nexus_edits_v2 fields only.",
            "missing_required_field": "Include all required fields for the chosen operation type.",
            "edit_mismatch": "Refresh file context and make old_text/anchor_text match the current file exactly.",
            "anchor_not_found": "Use a unique anchor_text that exists verbatim in the target file.",
            "unsafe_path": "Use workspace-relative file paths without traversal.",
            "intent_mismatch": "Align output with required intent checks from task semantics.",
            "verify_failed": "Re-run preview and correct syntax/semantic issues before applying again.",
        }
        return mapping.get(reason, "Resolve this issue and preview again.")


patch_service = PatchService()
