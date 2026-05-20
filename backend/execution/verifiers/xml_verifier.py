from __future__ import annotations

from pathlib import Path
from typing import Set
from xml.etree import ElementTree

from .base import FileVerificationResult, SyntaxVerifier, VerificationDiagnostic


class XmlSyntaxVerifier(SyntaxVerifier):
    @property
    def name(self) -> str:
        return "xml_parser"

    @property
    def supported_extensions(self) -> Set[str]:
        return {".xml"}

    def verify(self, path: Path, content: str) -> FileVerificationResult:
        result = FileVerificationResult(path=str(path))
        try:
            ElementTree.fromstring(content)
            result.verified = True
        except Exception as exc:
            result.failed = True
            result.diagnostics.append(
                VerificationDiagnostic(
                    severity="error",
                    code="syntax_error",
                    message="XML syntax validation failed.",
                    path=str(path),
                    verifier=self.name,
                    details=str(exc),
                )
            )
        return result

