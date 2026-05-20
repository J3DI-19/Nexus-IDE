from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from utils.security import get_project_root


@dataclass
class RuntimeConfig:
    python: Optional[str] = None
    node: Optional[str] = None
    java: Optional[str] = None
    gcc: Optional[str] = None
    gpp: Optional[str] = None
    dotnet: Optional[str] = None
    bash: Optional[str] = None
    powershell: Optional[str] = None


@dataclass
class RuntimeResolution:
    key: str
    path: Optional[Path]
    source: str
    determinism: str


class RuntimeRegistry:
    RUNTIME_BUNDLED_PATHS = {
        "python": "python/python.exe",
        "node": "node/node.exe",
        "java": "java/bin/java.exe",
        "gcc": "gcc/bin/gcc.exe",
        "gpp": "gcc/bin/g++.exe",
        "dotnet": "dotnet/dotnet.exe",
        "bash": "bash/usr/bin/bash.exe",
        "powershell": "powershell/pwsh.exe",
    }
    RUNTIME_EXECUTABLE_NAMES = {
        "python": ["python", "python3"],
        "node": ["node"],
        "java": ["java"],
        "gcc": ["gcc"],
        "gpp": ["g++", "c++"],
        "dotnet": ["csc", "dotnet"],
        "bash": ["bash"],
        "powershell": ["pwsh", "powershell"],
    }

    def __init__(self):
        self.root = get_project_root()
        self.config_path = self.root / "backend" / "config" / "runtime_paths.json"
        self.bundle_root = self.root / "backend" / "runtimes"

    def load(self) -> RuntimeConfig:
        if not self.config_path.exists():
            return RuntimeConfig()
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return RuntimeConfig(**{k: data.get(k) for k in RuntimeConfig.__annotations__.keys()})
        except Exception:
            return RuntimeConfig()

    def save(self, config: RuntimeConfig) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")

    def resolve(self, key: str, bundled_relpath: str) -> Optional[Path]:
        resolution = self.resolve_with_metadata(key, bundled_relpath)
        return resolution.path

    def resolve_with_metadata(self, key: str, bundled_relpath: str) -> RuntimeResolution:
        config = self.load()
        bundled = self.bundle_root / bundled_relpath
        if bundled.exists():
            return RuntimeResolution(key=key, path=bundled, source="bundled", determinism="deterministic")

        user_path = getattr(config, key, None)
        if user_path:
            path = Path(user_path)
            if path.exists():
                return RuntimeResolution(key=key, path=path, source="configured", determinism="deterministic")

        # Last fallback: use host runtime if present in PATH.
        for executable in self.RUNTIME_EXECUTABLE_NAMES.get(key, []):
            detected = shutil.which(executable)
            if detected:
                candidate = Path(detected)
                if candidate.exists():
                    return RuntimeResolution(key=key, path=candidate, source="system", determinism="host-dependent")
        return RuntimeResolution(key=key, path=None, source="missing", determinism="unresolved")

    def runtime_status(self) -> dict[str, dict[str, Optional[str]]]:
        config = self.load()
        status: dict[str, dict[str, Optional[str]]] = {}
        for key, bundled_relpath in self.RUNTIME_BUNDLED_PATHS.items():
            configured = getattr(config, key, None)
            resolution = self.resolve_with_metadata(key, bundled_relpath)
            bundled_path = self.bundle_root / bundled_relpath
            bundled_exists = bundled_path.exists()
            status[key] = {
                "configured": configured,
                "resolved": str(resolution.path) if resolution.path else None,
                "source": resolution.source,
                "determinism": resolution.determinism,
                "bundled_path": str(bundled_path),
                "bundled_installed": bundled_exists,
            }
        return status


runtime_registry = RuntimeRegistry()
