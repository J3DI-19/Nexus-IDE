from __future__ import annotations

import json
from pathlib import Path
from typing import Set

from .base import FileVerificationResult, SyntaxVerifier, VerificationDiagnostic


class JsonSyntaxVerifier(SyntaxVerifier):
    @property
    def name(self) -> str:
        return "json_parser"

    @property
    def supported_extensions(self) -> Set[str]:
        return {".json"}

    def verify(self, path: Path, content: str) -> FileVerificationResult:
        result = FileVerificationResult(path=str(path))
        try:
            json.loads(content)
            result.verified = True
        except Exception as exc:
            result.failed = True
            result.diagnostics.append(
                VerificationDiagnostic(
                    severity="error",
                    code="syntax_error",
                    message="JSON syntax validation failed.",
                    path=str(path),
                    verifier=self.name,
                    details=str(exc),
                )
            )
        return result

