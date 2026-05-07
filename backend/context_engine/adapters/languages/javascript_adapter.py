import re
from typing import List, Set
from .typescript_adapter import TypeScriptAdapter
from ...models.symbol import Symbol

class JavaScriptAdapter(TypeScriptAdapter):
    def get_supported_extensions(self) -> Set[str]:
        return {".js", ".jsx"}

    def can_handle(self, rel_path: str) -> bool:
        ext = rel_path.lower()
        return ext.endswith(".js") or ext.endswith(".jsx")

    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        # Reuse TypeScript logic but maybe filter out TS-specific things if needed.
        # For now, it's safe to use the same logic as JS is mostly a subset.
        symbols = super().extract_symbols(content, file_path)
        # Filter out interface symbols for pure JS (optional, but good for accuracy if we can distinguish)
        return [s for s in symbols if s.type != "interface"]
