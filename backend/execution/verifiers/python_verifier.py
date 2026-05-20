from __future__ import annotations

import ast
from pathlib import Path
from typing import Set

from .base import FileVerificationResult, SyntaxVerifier, VerificationDiagnostic


class PythonSyntaxVerifier(SyntaxVerifier):
    @property
    def name(self) -> str:
        return "python_ast"

    @property
    def supported_extensions(self) -> Set[str]:
        return {".py"}

    def verify(self, path: Path, content: str) -> FileVerificationResult:
        result = FileVerificationResult(path=str(path))
        try:
            ast.parse(content)
            result.verified = True
        except Exception as exc:
            result.failed = True
            result.diagnostics.append(
                VerificationDiagnostic(
                    severity="error",
                    code="syntax_error",
                    message="Python syntax validation failed.",
                    path=str(path),
                    verifier=self.name,
                    details=str(exc),
                )
            )
        return result

