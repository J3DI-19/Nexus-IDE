from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Set


class VerificationMode(str, Enum):
    OFF = "off"
    WARN = "warn"
    STRICT = "strict"


class VerificationState(str, Enum):
    FULLY_VERIFIED = "FULLY_VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    FAILED = "FAILED"


@dataclass
class VerificationDiagnostic:
    severity: str
    code: str
    message: str
    path: Optional[str] = None
    verifier: Optional[str] = None
    tooling_missing: bool = False
    details: Optional[str] = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "verifier": self.verifier,
            "tooling_missing": self.tooling_missing,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass
class FileVerificationResult:
    path: str
    verified: bool = False
    failed: bool = False
    diagnostics: list[VerificationDiagnostic] = field(default_factory=list)


@dataclass
class AndroidCheckResult:
    name: str
    verified: bool = False
    failed: bool = False
    unverified: bool = False
    diagnostics: list[VerificationDiagnostic] = field(default_factory=list)
    targets_checked: int = 0


class SyntaxVerifier(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def supported_extensions(self) -> Set[str]:
        raise NotImplementedError

    @abstractmethod
    def verify(self, path: Path, content: str) -> FileVerificationResult:
        raise NotImplementedError


class AndroidConsistencyChecker(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def supported_risks(self) -> Set[str]:
        raise NotImplementedError

    @abstractmethod
    def check(self, root: Path, targets: list[Any], mode: VerificationMode) -> AndroidCheckResult:
        raise NotImplementedError
