from pathlib import Path
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET

from .models import (
    AndroidComponent,
    AndroidDeepLink,
    AndroidDiagnostic,
    AndroidIntentFilter,
    AndroidManifestModel,
    AndroidPermission,
)
from .taxonomy import AndroidComponentType


ANDROID_NS = "http://schemas.android.com/apk/res/android"
ANDROID_NS_KEY = f"{{{ANDROID_NS}}}"


def parse_android_manifest(root_path: Path, rel_path: str) -> AndroidManifestModel:
    manifest = AndroidManifestModel(source_path=rel_path)
    abs_path = root_path / rel_path

    try:
        tree = ET.parse(abs_path)
        manifest_root = tree.getroot()
    except ET.ParseError as exc:
        line, column = _extract_position(exc)
        manifest.malformed = True
        manifest.diagnostics.append(
            AndroidDiagnostic(
                severity="error",
                code="malformed_manifest_xml",
                message="AndroidManifest.xml is malformed and could not be parsed.",
                source_path=rel_path,
                line=line,
                column=column,
                details=str(exc),
            )
        )
        return manifest
    except OSError as exc:
        manifest.malformed = True
        manifest.diagnostics.append(
            AndroidDiagnostic(
                severity="error",
                code="manifest_read_error",
                message="AndroidManifest.xml could not be read.",
                source_path=rel_path,
                details=str(exc),
            )
        )
        return manifest

    if _local_name(manifest_root.tag) != "manifest":
        manifest.diagnostics.append(
            AndroidDiagnostic(
                severity="warning",
                code="unexpected_manifest_root",
                message=f"Expected <manifest> root but found <{_local_name(manifest_root.tag)}>.",
                source_path=rel_path,
            )
        )

    manifest.package_name = manifest_root.attrib.get("package")
    manifest.namespace = manifest_root.attrib.get("namespace")

    application = _find_child(manifest_root, "application")
    if application is not None:
        manifest.application_attributes = _normalize_attributes(application.attrib)

    manifest.permissions = _extract_permissions(manifest_root, rel_path)
    manifest.activities = _extract_components(manifest_root, rel_path, AndroidComponentType.ACTIVITY.value)
    manifest.services = _extract_components(manifest_root, rel_path, AndroidComponentType.SERVICE.value)
    manifest.receivers = _extract_components(manifest_root, rel_path, AndroidComponentType.RECEIVER.value)
    manifest.providers = _extract_components(manifest_root, rel_path, AndroidComponentType.PROVIDER.value)

    launcher_activities = [c.name for c in manifest.activities if any(f.is_launcher for f in c.intent_filters)]
    if launcher_activities:
        manifest.launcher_activity = sorted(set(launcher_activities))[0]

    return manifest


def _extract_permissions(root: ET.Element, rel_path: str) -> List[AndroidPermission]:
    permissions: List[AndroidPermission] = []
    for tag_name in ("uses-permission", "permission", "uses-permission-sdk-23"):
        for element in _find_children(root, tag_name):
            name = _attr(element, "name")
            if not name:
                continue
            permissions.append(
                AndroidPermission(
                    name=name,
                    permission_type=tag_name,
                    max_sdk_version=_attr(element, "maxSdkVersion"),
                    uses_permission_flags=_attr(element, "usesPermissionFlags"),
                    source_path=rel_path,
                )
            )
    return sorted(permissions, key=lambda item: (item.permission_type, item.name))


def _extract_components(root: ET.Element, rel_path: str, component_type: str) -> List[AndroidComponent]:
    application = _find_child(root, "application")
    if application is None:
        return []

    components: List[AndroidComponent] = []
    for element in _find_children(application, component_type):
        name = _attr(element, "name")
        if not name:
            continue
        intent_filters = _extract_intent_filters(element)
        deep_links = _extract_deep_links(intent_filters)
        component = AndroidComponent(
            component_type=component_type,
            name=name,
            exported=_parse_bool(_attr(element, "exported")),
            enabled=_parse_bool(_attr(element, "enabled")),
            permission=_attr(element, "permission"),
            process=_attr(element, "process"),
            source_path=rel_path,
            attributes=_normalize_attributes(element.attrib),
            intent_filters=intent_filters,
            deep_links=deep_links,
        )
        components.append(component)
    return sorted(components, key=lambda item: item.name)


def _extract_intent_filters(component: ET.Element) -> List[AndroidIntentFilter]:
    filters: List[AndroidIntentFilter] = []
    for element in _find_children(component, "intent-filter"):
        actions = sorted(
            {
                value for value in (_attr(action, "name") for action in _find_children(element, "action"))
                if value
            }
        )
        categories = sorted(
            {
                value for value in (_attr(category, "name") for category in _find_children(element, "category"))
                if value
            }
        )
        data_entries: List[Dict[str, str]] = []
        for data_element in _find_children(element, "data"):
            attributes = _android_attributes_only(data_element.attrib)
            if attributes:
                data_entries.append(attributes)
        data_entries = sorted(data_entries, key=lambda entry: tuple(sorted(entry.items())))

        is_launcher = (
            "android.intent.action.MAIN" in actions
            and "android.intent.category.LAUNCHER" in categories
        )
        filters.append(
            AndroidIntentFilter(
                actions=actions,
                categories=categories,
                data=data_entries,
                auto_verify=_parse_bool(_attr(element, "autoVerify")) is True,
                is_launcher=is_launcher,
            )
        )

    return sorted(filters, key=lambda item: (
        not item.is_launcher,
        ",".join(item.actions),
        ",".join(item.categories),
    ))


def _extract_deep_links(intent_filters: List[AndroidIntentFilter]) -> List[AndroidDeepLink]:
    links: List[AndroidDeepLink] = []
    for intent_filter in intent_filters:
        for data in intent_filter.data:
            scheme = data.get("scheme")
            host = data.get("host")
            port = data.get("port")
            path = data.get("path")
            path_prefix = data.get("pathPrefix")
            path_pattern = data.get("pathPattern")
            mime_type = data.get("mimeType")
            if not any([scheme, host, port, path, path_prefix, path_pattern, mime_type]):
                continue
            links.append(
                AndroidDeepLink(
                    scheme=scheme,
                    host=host,
                    port=port,
                    path=path,
                    path_prefix=path_prefix,
                    path_pattern=path_pattern,
                    mime_type=mime_type,
                    auto_verify=intent_filter.auto_verify,
                )
            )
    return sorted(
        links,
        key=lambda item: (
            item.scheme or "",
            item.host or "",
            item.path or "",
            item.path_prefix or "",
            item.path_pattern or "",
            item.mime_type or "",
        ),
    )


def _attr(element: ET.Element, name: str) -> Optional[str]:
    return element.attrib.get(f"{ANDROID_NS_KEY}{name}") or element.attrib.get(name)


def _find_child(element: ET.Element, local_name: str) -> Optional[ET.Element]:
    for child in list(element):
        if _local_name(child.tag) == local_name:
            return child
    return None


def _find_children(element: ET.Element, local_name: str) -> List[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == local_name]


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _normalize_attributes(attributes: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for key, value in sorted(attributes.items(), key=lambda item: item[0]):
        if key.startswith(ANDROID_NS_KEY):
            normalized[f"android:{key.replace(ANDROID_NS_KEY, '', 1)}"] = value
        else:
            normalized[key] = value
    return normalized


def _android_attributes_only(attributes: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for key, value in sorted(attributes.items(), key=lambda item: item[0]):
        if key.startswith(ANDROID_NS_KEY):
            normalized[key.replace(ANDROID_NS_KEY, "", 1)] = value
    return normalized


def _parse_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def _extract_position(exc: ET.ParseError) -> tuple[Optional[int], Optional[int]]:
    position = getattr(exc, "position", None)
    if not position or len(position) != 2:
        return None, None
    return int(position[0]), int(position[1])
