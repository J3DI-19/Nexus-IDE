from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional

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


class RuntimeRegistry:
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
        config = self.load()
        user_path = getattr(config, key, None)
        if user_path:
            path = Path(user_path)
            if path.exists():
                return path

        bundled = self.bundle_root / bundled_relpath
        return bundled if bundled.exists() else None


runtime_registry = RuntimeRegistry()
