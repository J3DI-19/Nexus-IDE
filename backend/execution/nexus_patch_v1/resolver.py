from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from .errors import PatchIssue


@dataclass
class ResolvedSymbol:
    file_path: str
    name: str
    start_line: int
    end_line: int


def resolve_symbol(index: Any, file_path: Optional[str], symbol_name: str) -> tuple[Optional[ResolvedSymbol], List[PatchIssue]]:
    if not index:
        return None, [PatchIssue("symbol_index_unavailable", "error", "Symbol index is unavailable; refresh project context before applying symbol edits.")]

    candidates: List[ResolvedSymbol] = []
    if file_path:
        for sym in index.get_symbols_for_file(_normalize_rel_path(file_path)):
            if _matches_symbol(sym, symbol_name):
                candidates.append(_as_resolved(_normalize_rel_path(file_path), sym))
    else:
        for rel_path, symbols in getattr(index, "symbols", {}).items():
            for sym in symbols:
                if _matches_symbol(sym, symbol_name):
                    candidates.append(_as_resolved(rel_path, sym))

    if not candidates:
        return None, [PatchIssue("symbol_not_found", "error", "Symbol target could not be found; Nexus will not guess.", path=file_path, details=symbol_name)]
    if len(candidates) > 1:
        details = ", ".join(f"{item.file_path}:{item.name}" for item in candidates[:8])
        return None, [PatchIssue("symbol_ambiguous", "error", "Symbol target is ambiguous; include a File path or more specific symbol.", path=file_path, details=details)]
    return candidates[0], []


def _matches_symbol(sym: Any, target: str) -> bool:
    name = getattr(sym, "name", "")
    parent_id = getattr(sym, "parent_id", None)
    qualified = f"{parent_id}.{name}" if parent_id else name
    return target in {name, qualified}


def _as_resolved(path: str, sym: Any) -> ResolvedSymbol:
    return ResolvedSymbol(
        file_path=path,
        name=getattr(sym, "name", ""),
        start_line=int(getattr(sym, "start_line", 1)),
        end_line=int(getattr(sym, "end_line", 1)),
    )


def _normalize_rel_path(raw_path: str) -> str:
    normalized = raw_path.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized
