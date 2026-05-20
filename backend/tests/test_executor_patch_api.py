from pathlib import Path
import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from main import app  # noqa: E402
from utils.security import set_project_root  # noqa: E402


def _git_available() -> bool:
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, check=False)
        return result.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _git_available(), reason="git is required")


def test_malformed_json_repaired_as_warning_and_applyable(tmp_path: Path):
    set_project_root(str(tmp_path))
    source = tmp_path / "calculator.py"
    source.write_text(
        "def main():\n"
        "    operation = input(\"Choose (+, -, *, /): \")\n",
        encoding="utf-8",
    )
    malformed = (
        '{"format":"nexus_edits_v2","edits":[{"path":"calculator.py","op":"replace_range",'
        '"old_text":"    operation = input("Choose (+, -, *, /): ")","new_text":"    operation = input("Choose (+, -, *, /, ^2): ")"}]}'
    )
    client = TestClient(app)

    preview = client.post(
        "/executor/patch/preview",
        json={"raw_text": malformed, "response_format": "nexus_edits_v2", "auto_extract": True},
    )
    assert preview.status_code == 200
    data = preview.json()["preview"]
    assert data["can_apply"] is True
    assert data["blockers"] == []
    assert any(i["reason"] == "repaired_unescaped_quotes" for i in data["warnings"])

    apply = client.post(
        "/executor/patch/apply",
        json={"raw_text": malformed, "response_format": "nexus_edits_v2", "auto_extract": True},
    )
    assert apply.status_code == 200
    body = apply.json()["apply"]
    assert body["can_apply"] is True
    assert body["verification_passed"] is True
    assert body["snapshot_created"] is True
    assert "Choose (+, -, *, /, ^2)" in source.read_text(encoding="utf-8")


def test_intent_guard_blocks_token_drift_for_squaring_task(tmp_path: Path):
    set_project_root(str(tmp_path))
    source = tmp_path / "calculator.py"
    source.write_text(
        "def main():\n"
        "    operation = input(\"Choose (+, -, *, /): \")\n"
        "    if operation == \"+\":\n"
        "        result = 1\n"
        "    elif operation == \"-\":\n"
        "        result = 2\n",
        encoding="utf-8",
    )
    wrong_payload = {
        "format": "nexus_edits_v2",
        "edits": [
            {
                "path": "calculator.py",
                "op": "replace_range",
                "old_text": "    operation = input(\"Choose (+, -, *, /): \")",
                "new_text": "    operation = input(\"Choose (+, -, *, /, ^): \")",
            }
        ],
    }
    client = TestClient(app)

    preview = client.post(
        "/executor/patch/preview",
        json={
            "raw_text": json.dumps(wrong_payload),
            "response_format": "nexus_edits_v2",
            "task": "Feature: add squaring",
            "mode": "feature",
        },
    )
    assert preview.status_code == 200
    body = preview.json()["preview"]
    assert body["can_apply"] is False
    assert body["blocked_stage"] == "intent_guard"
    assert any(i["reason"] == "intent_mismatch" for i in body["blockers"])
    assert "^2" in body["intent_checks"]["required_contains"]

    apply = client.post(
        "/executor/patch/apply",
        json={
            "raw_text": json.dumps(wrong_payload),
            "response_format": "nexus_edits_v2",
            "task": "Feature: add squaring",
            "mode": "feature",
        },
    )
    assert apply.status_code == 200
    apply_body = apply.json()["apply"]
    assert apply_body["can_apply"] is False
    assert apply_body["blocked_stage"] == "intent_guard"
    assert "Choose (+, -, *, /, ^): " not in source.read_text(encoding="utf-8")


def test_correct_squaring_token_passes_preview_apply_and_snapshots(tmp_path: Path):
    set_project_root(str(tmp_path))
    source = tmp_path / "calculator.py"
    source.write_text(
        "def main():\n"
        "    operation = input(\"Choose (+, -, *, /): \")\n"
        "    if operation == \"+\":\n"
        "        result = 1\n"
        "    elif operation == \"-\":\n"
        "        result = 2\n",
        encoding="utf-8",
    )
    good_payload = {
        "format": "nexus_edits_v2",
        "edits": [
            {
                "path": "calculator.py",
                "op": "replace_range",
                "old_text": "    operation = input(\"Choose (+, -, *, /): \")",
                "new_text": "    operation = input(\"Choose (+, -, *, /, ^2): \")",
            },
            {
                "path": "calculator.py",
                "op": "replace_range",
                "old_text": "    elif operation == \"-\":\n        result = 2\n",
                "new_text": "    elif operation == \"-\":\n        result = 2\n    elif operation == \"^2\":\n        result = a ** 2\n",
            }
        ],
    }
    client = TestClient(app)

    preview = client.post(
        "/executor/patch/preview",
        json={
            "raw_text": json.dumps(good_payload),
            "response_format": "nexus_edits_v2",
            "task": "Feature: add squaring",
            "mode": "feature",
        },
    )
    assert preview.status_code == 200
    pbody = preview.json()["preview"]
    assert pbody["can_apply"] is True
    assert pbody["blockers"] == []

    apply = client.post(
        "/executor/patch/apply",
        json={
            "raw_text": json.dumps(good_payload),
            "response_format": "nexus_edits_v2",
            "task": "Feature: add squaring",
            "mode": "feature",
        },
    )
    assert apply.status_code == 200
    abody = apply.json()["apply"]
    assert abody["can_apply"] is True
    assert abody["verification_passed"] is True
    assert abody["snapshot_created"] is True
    assert abody.get("operation_id")
    assert "Choose (+, -, *, /, ^2)" in source.read_text(encoding="utf-8")


def test_assertion_contract_blocks_when_explicit_contains_missing(tmp_path: Path):
    set_project_root(str(tmp_path))
    source = tmp_path / "a.py"
    source.write_text("x = 1\n", encoding="utf-8")
    payload = {
        "format": "nexus_edits_v2",
        "edits": [{"path": "a.py", "op": "replace_range", "old_text": "x = 1", "new_text": "x = 2"}],
    }
    client = TestClient(app)

    blocked = client.post(
        "/executor/patch/preview",
        json={
            "raw_text": json.dumps(payload),
            "response_format": "nexus_edits_v2",
            "assert_contains": ["x = 99"],
        },
    )
    assert blocked.status_code == 200
    blocked_body = blocked.json()["preview"]
    assert blocked_body["can_apply"] is False
    assert any(i["reason"] == "intent_mismatch" for i in blocked_body["blockers"])

    allowed = client.post(
        "/executor/patch/preview",
        json={
            "raw_text": json.dumps(payload),
            "response_format": "nexus_edits_v2",
            "assert_contains": ["x = 2"],
            "assert_not_contains": ["x = 1"],
        },
    )
    assert allowed.status_code == 200
    allowed_body = allowed.json()["preview"]
    assert allowed_body["can_apply"] is True


def test_schema_blocker_for_unsupported_edit_fields(tmp_path: Path):
    set_project_root(str(tmp_path))
    source = tmp_path / "a.py"
    source.write_text("x = 1\n", encoding="utf-8")
    payload = {
        "format": "nexus_edits_v2",
        "edits": [{"path": "a.py", "op": "replace_range", "old_text": "x = 1", "new_text": "x = 2", "unexpected": True}],
    }
    client = TestClient(app)
    preview = client.post("/executor/patch/preview", json={"raw_text": json.dumps(payload), "response_format": "nexus_edits_v2"})
    assert preview.status_code == 200
    body = preview.json()["preview"]
    assert body["can_apply"] is False
    assert any(i["reason"] == "unsupported_edit_field" for i in body["blockers"])


def test_verify_failure_triggers_rollback(monkeypatch, tmp_path: Path):
    set_project_root(str(tmp_path))
    source = tmp_path / "a.py"
    source.write_text("x = 1\n", encoding="utf-8")
    payload = {
        "format": "nexus_edits_v2",
        "edits": [{"path": "a.py", "op": "replace_range", "old_text": "x = 1", "new_text": "x = 2"}],
    }
    from api import executor as executor_api  # local import for monkeypatch

    def _force_verify_fail(*args, **kwargs):
        return [{"reason": "verify_failed", "details": "forced failure"}]

    monkeypatch.setattr(executor_api.patch_service, "verify_applied", _force_verify_fail)
    client = TestClient(app)
    apply = client.post("/executor/patch/apply", json={"raw_text": json.dumps(payload), "response_format": "nexus_edits_v2"})
    assert apply.status_code == 200
    body = apply.json()["apply"]
    assert body["can_apply"] is False
    assert body["blocked_stage"] == "verify"
    assert body["verification_passed"] is False
    assert body["rollback"]["attempted"] is True
    assert "x = 1" in source.read_text(encoding="utf-8")


def test_verify_syntax_failure_triggers_rollback_without_monkeypatch(tmp_path: Path):
    set_project_root(str(tmp_path))
    source = tmp_path / "config.json"
    source.write_text('{"name":"ok"}\n', encoding="utf-8")
    payload = {
        "format": "nexus_edits_v2",
        "edits": [
            {
                "path": "config.json",
                "op": "replace_range",
                "old_text": '{"name":"ok"}',
                "new_text": '{"name":',
            }
        ],
    }
    client = TestClient(app)
    apply = client.post("/executor/patch/apply", json={"raw_text": json.dumps(payload), "response_format": "nexus_edits_v2"})
    assert apply.status_code == 200
    body = apply.json()["apply"]
    assert body["can_apply"] is False
    assert body["blocked_stage"] == "verify"
    assert body["verification_passed"] is False
    assert body["rollback"]["attempted"] is True
    assert source.read_text(encoding="utf-8") == '{"name":"ok"}\n'
