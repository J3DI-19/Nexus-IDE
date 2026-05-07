import os
from pathlib import Path
from typing import List, Dict
from ..models.project import ProjectMetadata

class ProjectClassifier:
    FRAMEWORK_ANALYTICS = {
        "React": ["package.json", "src/App.tsx", "src/App.jsx", "public/index.html"],
        "Vite": ["vite.config.ts", "vite.config.js"],
        "Node.js": ["package.json", "node_modules"],
        "Android": ["build.gradle", "AndroidManifest.xml", "app/src/main"],
        "Java": ["pom.xml", "build.gradle", "src/main/java"],
        "C#": [".csproj", ".sln", "Program.cs", "Assets"],
        "C++": ["CMakeLists.txt", "Makefile", ".vcxproj", ".sln", "conanfile.txt", "vcpkg.json"],
    }

    def detect_frameworks(self, root_path: Path, all_files: List[str]) -> ProjectMetadata:
        detected = set()
        file_set = set(all_files)

        if self._detect_fastapi(root_path, all_files):
            detected.add("FastAPI")

        # Simple file-presence based detection
        for framework, indicators in self.FRAMEWORK_ANALYTICS.items():
            for indicator in indicators:
                if indicator in file_set or any(f.endswith(indicator) for f in all_files):
                    detected.add(framework)
                    break

        return ProjectMetadata(
            root_path=str(root_path),
            project_name=root_path.name,
            frameworks_detected=list(detected)
        )

    def _detect_fastapi(self, root_path: Path, all_files: List[str]) -> bool:
        dependency_files = {"requirements.txt", "pyproject.toml", "Pipfile"}
        for rel_path in all_files:
            if rel_path in dependency_files:
                try:
                    content = (root_path / rel_path).read_text(encoding="utf-8", errors="ignore").lower()
                    if "fastapi" in content:
                        return True
                except OSError:
                    continue

        python_files = [path for path in all_files if path.endswith(".py")]
        for rel_path in python_files[:40]:
            try:
                content = (root_path / rel_path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            if "from fastapi import" in content or "import fastapi" in content or "FastAPI(" in content:
                return True

        return False

    def classify_file(self, rel_path: str) -> str:
        """Categorizes files into functional roles."""
        parts = rel_path.lower().split('/')
        name = parts[-1]
        ext = os.path.splitext(name)[1]

        if "test" in name or "test" in parts:
            return "test"
        if name in ["package.json", "pyproject.toml", "requirements.txt", "vite.config.ts", "vite.config.js", ".gitignore", "build.gradle", "AndroidManifest.xml"]:
            return "config"
        if "api" in parts or "route" in name:
            return "route"
        if "model" in parts or "schema" in name:
            return "model"
        if "component" in parts or "ui" in parts or "layout" in parts or ext in [".tsx", ".jsx", ".html", ".css", ".xml"]:
            return "ui"
        if "utils" in parts or "helper" in name:
            return "utility"
        
        if ext in [".cpp", ".c", ".cc", ".cxx", ".h", ".hpp", ".hxx", ".hh"]:
            return "source"

        if ext in [".json", ".yaml", ".yml", ".toml"]:
            return "config"
        
        return "source"
