from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class PatchIssue:
    code: str
    severity: str
    message: str
    op_id: Optional[str] = None
    action_id: Optional[str] = None
    path: Optional[str] = None
    details: Optional[str] = None

    def as_issue(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "reason": self.code,
            "code": self.code,
            "severity": self.severity,
            "details": self.details or self.message,
            "fix_suggestion": self.message,
        }
        if self.path:
            payload["path"] = self.path
        if self.op_id:
            payload["op_id"] = self.op_id
        if self.action_id:
            payload["action_id"] = self.action_id
        return payload
