from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional, List

from core.patch_service import patch_service
from core.version_service import version_service
from execution.config import load_executor_verification_config
from utils.api_response import err, log_route_end, log_route_start, ok, request_id_from
from utils.security import get_project_root

router = APIRouter()
logger = logging.getLogger("nexus.executor")


class PatchPreviewRequest(BaseModel):
    raw_text: str
    response_format: str = "nexus_edits_v2"
    auto_extract: bool = False
    task: Optional[str] = None
    mode: str = "feature"
    active_file: Optional[str] = None
    assert_contains: Optional[List[str]] = None
    assert_not_contains: Optional[List[str]] = None


class PatchApplyRequest(BaseModel):
    raw_text: str
    selected_paths: Optional[List[str]] = None
    response_format: str = "nexus_edits_v2"
    auto_extract: bool = False
    task: Optional[str] = None
    mode: str = "feature"
    active_file: Optional[str] = None
    assert_contains: Optional[List[str]] = None
    assert_not_contains: Optional[List[str]] = None


class PatchAutoFetchRequest(BaseModel):
    raw_text: str
    response_format: str = "nexus_edits_v2"


@router.post("/executor/patch/preview")
async def preview_patch(request: Request, req: PatchPreviewRequest):
    rid = request_id_from(request)
    started = log_route_start("/executor/patch/preview", rid)
    try:
        root = get_project_root()
        result = patch_service.preview(
            root,
            req.raw_text,
            response_format=req.response_format,
            auto_extract=req.auto_extract,
            task=req.task,
            mode=req.mode,
            active_file=req.active_file,
            assert_contains=req.assert_contains,
            assert_not_contains=req.assert_not_contains,
        )
        logger.info(
            "executor_preview request_id=%s can_apply=%s warnings=%s blockers=%s metrics=%s",
            rid,
            result.get("can_apply"),
            len(result.get("warnings", [])),
            len(result.get("blockers", [])),
            patch_service.get_metrics(),
        )
        payload = ok({"preview": result}, request_id=rid)
        log_route_end("/executor/patch/preview", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/executor/patch/preview", rid, started, False)
        return err("patch_preview_failed", "Failed to preview patch", details=str(e), request_id=rid)


@router.post("/executor/patch/apply")
async def apply_patch(request: Request, req: PatchApplyRequest):
    rid = request_id_from(request)
    started = log_route_start("/executor/patch/apply", rid)
    try:
        root = get_project_root()
        version_service.ensure_local_repo(root)
        result, changed_paths, applied_changes = patch_service.apply(
            root,
            req.raw_text,
            req.selected_paths,
            response_format=req.response_format,
            auto_extract=req.auto_extract,
            task=req.task,
            mode=req.mode,
            active_file=req.active_file,
            assert_contains=req.assert_contains,
            assert_not_contains=req.assert_not_contains,
        )
        if not result.get("can_apply", False):
            logger.info(
                "executor_apply_blocked request_id=%s blockers=%s metrics=%s",
                rid,
                len(result.get("blockers", [])),
                patch_service.get_metrics(),
            )
            payload = ok({"apply": result}, request_id=rid)
            log_route_end("/executor/patch/apply", rid, started, True)
            return payload

        snapshot = version_service.snapshot(
            root,
            "executor_apply",
            changed_paths,
            actor="user",
            metadata={"intent_checks": result.get("intent_checks", {})},
        )
        verification_config = load_executor_verification_config(root)
        verification_report = patch_service.verify_applied_with_report(
            root,
            applied_changes,
            result.get("intent_checks", {}),
            mode=req.mode or "feature",
            verification_mode=verification_config.mode,
            config_diagnostics=verification_config.diagnostics,
            android_config=verification_config.android,
        )
        verify_blockers = verification_report.get("blockers", [])
        verify_warnings = verification_report.get("warnings", [])
        verification_payload = verification_report.get("verification", {})
        rollback_payload = {"attempted": False, "success": False}

        if verify_blockers:
            rollback_payload["attempted"] = True
            if snapshot.snapshot_created:
                try:
                    undo_result, undo_mode, undo_target = version_service.undo(root)
                    rollback_payload = {
                        "attempted": True,
                        "success": True,
                        "operation_id": undo_result.operation_id,
                        "snapshot_id": undo_result.snapshot_id,
                        "undo_mode": undo_mode,
                        "undo_target": undo_target,
                    }
                except Exception as rollback_exc:
                    logger.exception("rollback_via_undo_failed request_id=%s", rid)
                    rollback_payload = {
                        "attempted": True,
                        "success": patch_service.rollback_changes(root, applied_changes),
                        "error": str(rollback_exc),
                    }
            else:
                rollback_payload["success"] = patch_service.rollback_changes(root, applied_changes)

            apply_payload = {
                **result,
                "can_apply": False,
                "verification_passed": False,
                "blocked_stage": "verify",
                "verification": verification_payload,
                "warnings": result.get("warnings", []) + verify_warnings,
                "blockers": result.get("blockers", []) + verify_blockers,
                "issues": result.get("warnings", []) + verify_warnings + result.get("blockers", []) + verify_blockers,
                "rollback": rollback_payload,
                "operation_id": snapshot.operation_id,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_created": snapshot.snapshot_created,
            }
            payload = ok({"apply": apply_payload}, request_id=rid)
            log_route_end("/executor/patch/apply", rid, started, True)
            logger.info("executor_apply_verify_failed request_id=%s rollback=%s metrics=%s", rid, rollback_payload, patch_service.get_metrics())
            return payload

        logger.info("executor_apply_success request_id=%s snapshot=%s metrics=%s", rid, snapshot.snapshot_id, patch_service.get_metrics())
        payload = ok({
            "apply": {
                **result,
                "verification_passed": True,
                "verification": verification_payload,
                "warnings": result.get("warnings", []) + verify_warnings,
                "rollback": rollback_payload,
                "operation_id": snapshot.operation_id,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_created": snapshot.snapshot_created,
            }
        }, request_id=rid)
        log_route_end("/executor/patch/apply", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/executor/patch/apply", rid, started, False)
        return err("patch_apply_failed", "Failed to apply patch", details=str(e), request_id=rid)


@router.post("/executor/patch/autofetch")
async def autofetch_patch_payload(request: Request, req: PatchAutoFetchRequest):
    rid = request_id_from(request)
    started = log_route_start("/executor/patch/autofetch", rid)
    try:
        normalized = patch_service.normalize_payload(req.raw_text, response_format=req.response_format, auto_extract=True)
        payload = ok({"autofetch": normalized}, request_id=rid)
        log_route_end("/executor/patch/autofetch", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/executor/patch/autofetch", rid, started, False)
        return err("patch_autofetch_failed", "Failed to auto-fetch patch payload", details=str(e), request_id=rid)


@router.get("/executor/metrics")
async def executor_metrics(request: Request):
    rid = request_id_from(request)
    started = log_route_start("/executor/metrics", rid)
    try:
        payload = ok({"metrics": patch_service.get_metrics()}, request_id=rid)
        log_route_end("/executor/metrics", rid, started, True)
        return payload
    except Exception as e:
        log_route_end("/executor/metrics", rid, started, False)
        return err("executor_metrics_failed", "Failed to fetch executor metrics", details=str(e), request_id=rid)
