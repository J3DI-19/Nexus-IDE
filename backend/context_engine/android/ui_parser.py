from pathlib import Path
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET

from .manifest_parser import ANDROID_NS, ANDROID_NS_KEY
from .models import (
    AndroidDiagnostic,
    AndroidLayoutModel,
    AndroidResourceRef,
    AndroidUiElement,
)


ALLOWED_RESOURCE_PREFIXES = ("@+id/", "@id/", "@layout/", "@string/", "@drawable/")


def parse_layout_xml(root_path: Path, rel_path: str) -> AndroidLayoutModel:
    layout_name = Path(rel_path).stem
    model = AndroidLayoutModel(source_path=rel_path, layout_name=layout_name)
    abs_path = root_path / rel_path

    try:
        tree = ET.parse(abs_path)
        root_element = tree.getroot()
    except ET.ParseError as exc:
        line, column = _extract_position(exc)
        model.malformed = True
        model.diagnostics.append(
            AndroidDiagnostic(
                severity="error",
                code="malformed_layout_xml",
                message="Layout XML is malformed and could not be parsed.",
                source_path=rel_path,
                line=line,
                column=column,
                details=str(exc),
            )
        )
        return model
    except OSError as exc:
        model.malformed = True
        model.diagnostics.append(
            AndroidDiagnostic(
                severity="error",
                code="layout_read_error",
                message="Layout XML could not be read.",
                source_path=rel_path,
                details=str(exc),
            )
        )
        return model

    model.root_tag = _local_name(root_element.tag)
    ids: set[str] = set()
    refs: List[AndroidResourceRef] = []
    elements: List[AndroidUiElement] = []

    for element in root_element.iter():
        tag = _local_name(element.tag)
        normalized_attrs = _normalize_attributes(element.attrib)
        element_id = _android_attr(element, "id")
        if element_id and (element_id.startswith("@+id/") or element_id.startswith("@id/")):
            ids.add(element_id.split("/", 1)[1])

        elements.append(
            AndroidUiElement(
                tag=tag,
                element_id=element_id,
                attributes=normalized_attrs,
            )
        )

        for attr_name, attr_value in normalized_attrs.items():
            if not isinstance(attr_value, str):
                continue
            if not attr_value.startswith("@"):
                continue
            if not attr_value.startswith(ALLOWED_RESOURCE_PREFIXES):
                continue
            ref_type, ref_value = attr_value[1:].split("/", 1)
            refs.append(
                AndroidResourceRef(
                    ref_type=ref_type,
                    value=ref_value,
                    source_path=rel_path,
                    element_tag=tag,
                    attribute=attr_name,
                )
            )

    model.resource_ids = sorted(ids)
    model.resource_refs = sorted(
        refs,
        key=lambda item: (item.ref_type, item.value, item.element_tag or "", item.attribute or ""),
    )
    model.ui_elements = sorted(
        elements,
        key=lambda item: (item.tag, item.element_id or ""),
    )
    return model


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _android_attr(element: ET.Element, name: str) -> Optional[str]:
    return element.attrib.get(f"{ANDROID_NS_KEY}{name}") or element.attrib.get(name)


def _normalize_attributes(attributes: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for key, value in sorted(attributes.items(), key=lambda item: item[0]):
        if key.startswith(f"{{{ANDROID_NS}}}"):
            normalized[f"android:{key.replace(f'{{{ANDROID_NS}}}', '', 1)}"] = value
        else:
            normalized[key] = value
    return normalized


def _extract_position(exc: ET.ParseError) -> tuple[Optional[int], Optional[int]]:
    position = getattr(exc, "position", None)
    if not position or len(position) != 2:
        return None, None
    return int(position[0]), int(position[1])
