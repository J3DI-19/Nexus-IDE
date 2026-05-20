from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple

from .models import (
    AndroidDependency,
    AndroidDiagnostic,
    AndroidGradleModel,
    AndroidModuleModel,
    AndroidVariantModel,
)


MODULE_INCLUDE_RE = re.compile(r"include\s*\(([^)]*)\)|include\s+([^\n]+)")
PLUGIN_ID_RE = re.compile(r"id\s*\(?\s*[\"']([A-Za-z0-9_.-]+)[\"']\s*\)?")
COMPILE_SDK_RE = re.compile(r"\bcompileSdk(?:Version)?\s*=?\s*([A-Za-z0-9_.\"']+)")
MIN_SDK_RE = re.compile(r"\bminSdk(?:Version)?\s*=?\s*([A-Za-z0-9_.\"']+)")
TARGET_SDK_RE = re.compile(r"\btargetSdk(?:Version)?\s*=?\s*([A-Za-z0-9_.\"']+)")
NAMESPACE_RE = re.compile(r"\bnamespace\s*=?\s*[\"']([A-Za-z0-9_.]+)[\"']")
DEPENDENCY_CALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*(.+)\s*\)$")
DEPENDENCY_LITERAL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s+[\"'](.+)[\"']$")
PROJECT_DEP_RE = re.compile(r"project\s*\(\s*[\"'](:[A-Za-z0-9:_-]+)[\"']\s*\)")
FLAVOR_START_RE = re.compile(r"\bproductFlavors\b")
BUILD_TYPES_START_RE = re.compile(r"\bbuildTypes\b")
BLOCK_NAME_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\{")


def analyze_gradle_project(
    root_path: Path,
    file_paths: List[str],
    manifest_paths: List[str],
    layout_paths: List[str],
) -> Tuple[List[AndroidModuleModel], AndroidGradleModel, List[AndroidDiagnostic]]:
    diagnostics: List[AndroidDiagnostic] = []
    settings_file = _pick_first(file_paths, ("settings.gradle.kts", "settings.gradle"))
    root_build_file = _pick_first(file_paths, ("build.gradle.kts", "build.gradle"))

    module_map = _discover_modules(root_path, settings_file, file_paths, diagnostics)
    module_map = _enrich_modules_from_build_files(file_paths, module_map)

    for module_path, module in module_map.items():
        module.manifest_paths = sorted(_paths_for_module(module_path, module.module_dir, manifest_paths))
        module.layout_paths = sorted(_paths_for_module(module_path, module.module_dir, layout_paths))
        if module.build_file:
            _populate_module_build_metadata(root_path, module, diagnostics)

    modules = sorted(module_map.values(), key=lambda item: item.module_path)
    gradle_model = AndroidGradleModel(
        settings_file=settings_file,
        root_build_file=root_build_file,
        modules_discovered=len(modules),
        plugins=sorted(_collect_root_plugins(root_path, root_build_file)),
        diagnostics=sorted(diagnostics, key=lambda d: (d.code, d.source_path or "")),
    )
    return modules, gradle_model, diagnostics


def _pick_first(file_paths: List[str], names: Tuple[str, str]) -> Optional[str]:
    for candidate in names:
        if candidate in file_paths:
            return candidate
    return None


def _discover_modules(
    root_path: Path,
    settings_file: Optional[str],
    file_paths: List[str],
    diagnostics: List[AndroidDiagnostic],
) -> Dict[str, AndroidModuleModel]:
    modules: Dict[str, AndroidModuleModel] = {}
    if settings_file:
        settings_abs = root_path / settings_file
        try:
            content = settings_abs.read_text(encoding="utf-8", errors="ignore")
            for module_path in _extract_settings_modules(content):
                module_dir = module_path.lstrip(":").replace(":", "/")
                modules[module_path] = AndroidModuleModel(
                    module_path=module_path,
                    module_dir=module_dir,
                )
        except OSError as exc:
            diagnostics.append(
                AndroidDiagnostic(
                    severity="warning",
                    code="settings_gradle_read_error",
                    message="Could not read settings.gradle for module discovery.",
                    source_path=settings_file,
                    details=str(exc),
                )
            )

    if not modules:
        fallback_modules = _infer_modules_from_paths(file_paths)
        for module_dir in fallback_modules:
            module_path = ":" + module_dir.replace("/", ":")
            modules[module_path] = AndroidModuleModel(
                module_path=module_path,
                module_dir=module_dir,
            )
    return modules


def _extract_settings_modules(content: str) -> Set[str]:
    modules: Set[str] = set()
    for match in MODULE_INCLUDE_RE.finditer(content):
        values = [value for value in match.groups() if value]
        for group in values:
            for token in group.split(","):
                cleaned = token.strip().strip("\"'")
                if cleaned.startswith(":"):
                    modules.add(cleaned)
    return modules


def _infer_modules_from_paths(file_paths: List[str]) -> Set[str]:
    modules: Set[str] = set()
    for rel_path in file_paths:
        parts = rel_path.split("/")
        if len(parts) < 2:
            continue
        if parts[1] == "src" and parts[0]:
            modules.add(parts[0])
        if rel_path.endswith("build.gradle") or rel_path.endswith("build.gradle.kts"):
            if "/" in rel_path:
                modules.add(rel_path.rsplit("/", 1)[0])
    return modules


def _enrich_modules_from_build_files(
    file_paths: List[str],
    modules: Dict[str, AndroidModuleModel],
) -> Dict[str, AndroidModuleModel]:
    updated = dict(modules)
    for rel_path in sorted(file_paths):
        if not (rel_path.endswith("build.gradle") or rel_path.endswith("build.gradle.kts")):
            continue
        if "/" not in rel_path:
            continue
        module_dir = rel_path.rsplit("/", 1)[0]
        module_path = ":" + module_dir.replace("/", ":")
        if module_path not in updated:
            updated[module_path] = AndroidModuleModel(module_path=module_path, module_dir=module_dir)
        updated[module_path].build_file = rel_path
    return updated


def _paths_for_module(module_path: str, module_dir: str, target_paths: List[str]) -> List[str]:
    prefix = f"{module_dir}/"
    return [path for path in target_paths if path.startswith(prefix)]


def _populate_module_build_metadata(
    root_path: Path,
    module: AndroidModuleModel,
    diagnostics: List[AndroidDiagnostic],
) -> None:
    if not module.build_file:
        return
    abs_path = root_path / module.build_file
    try:
        content = abs_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        diag = AndroidDiagnostic(
            severity="warning",
            code="module_build_read_error",
            message="Could not read module build file.",
            source_path=module.build_file,
            details=str(exc),
        )
        module.diagnostics.append(diag)
        diagnostics.append(diag)
        return

    module.plugins = sorted(set(PLUGIN_ID_RE.findall(content)))
    module.namespace = _clean_scalar(_extract_first(NAMESPACE_RE, content))
    module.compile_sdk = _clean_scalar(_extract_first(COMPILE_SDK_RE, content))
    module.min_sdk = _clean_scalar(_extract_first(MIN_SDK_RE, content))
    module.target_sdk = _clean_scalar(_extract_first(TARGET_SDK_RE, content))
    module.dependencies = _extract_dependencies(content, module.build_file)
    module.variants = AndroidVariantModel(
        build_types=_extract_named_block_entries(content, BUILD_TYPES_START_RE),
        product_flavors=_extract_named_block_entries(content, FLAVOR_START_RE),
    )


def _extract_first(pattern: re.Pattern, content: str) -> Optional[str]:
    match = pattern.search(content)
    if not match:
        return None
    return match.group(1)


def _clean_scalar(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.strip().strip("\"'")


def _extract_dependencies(content: str, source_path: str) -> List[AndroidDependency]:
    dependencies: List[AndroidDependency] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue

        config = ""
        expr = ""
        call_match = DEPENDENCY_CALL_RE.match(line)
        literal_match = DEPENDENCY_LITERAL_RE.match(line)
        if call_match:
            config = call_match.group(1).strip()
            expr = call_match.group(2).strip()
        elif literal_match:
            config = literal_match.group(1).strip()
            expr = literal_match.group(2).strip()
        else:
            continue

        project_match = PROJECT_DEP_RE.search(expr)
        if project_match:
            target_module = project_match.group(1)
            dependencies.append(
                AndroidDependency(
                    notation=f"project({target_module})",
                    configuration=config,
                    dependency_type="module",
                    target_module=target_module,
                    source_path=source_path,
                )
            )
            continue

        cleaned = expr.strip().strip("\"'")
        if cleaned:
            dependencies.append(
                AndroidDependency(
                    notation=cleaned,
                    configuration=config,
                    dependency_type="external",
                    source_path=source_path,
                )
            )

    return sorted(
        dependencies,
        key=lambda item: (item.dependency_type, item.configuration, item.notation),
    )


def _extract_named_block_entries(content: str, block_start_pattern: re.Pattern) -> List[str]:
    start_match = block_start_pattern.search(content)
    if not start_match:
        return []

    start_index = content.find("{", start_match.start())
    if start_index < 0:
        return []

    block_content = _extract_braced_block(content, start_index)
    if not block_content:
        return []

    names: Set[str] = set()
    for line in block_content.splitlines():
        match = BLOCK_NAME_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        if name not in {"all", "create", "maybeCreate", "getByName"}:
            names.add(name)
    return sorted(names)


def _extract_braced_block(content: str, brace_start_index: int) -> str:
    depth = 0
    start = brace_start_index
    for index in range(brace_start_index, len(content)):
        ch = content[index]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return content[start + 1:index]
    return ""


def _collect_root_plugins(root_path: Path, root_build_file: Optional[str]) -> Set[str]:
    if not root_build_file:
        return set()
    try:
        content = (root_path / root_build_file).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    return set(PLUGIN_ID_RE.findall(content))
