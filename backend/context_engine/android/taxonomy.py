from enum import Enum


class AndroidComponentType(str, Enum):
    ACTIVITY = "activity"
    SERVICE = "service"
    RECEIVER = "receiver"
    PROVIDER = "provider"


class AndroidRelationshipType(str, Enum):
    DECLARES_COMPONENT = "declares_component"
    HAS_INTENT_FILTER = "has_intent_filter"
    HAS_DEEPLINK = "has_deeplink"
    HAS_LAUNCHER_ACTIVITY = "has_launcher_activity"
    COMPONENT_USES_LAYOUT = "component_uses_layout"
    LAYOUT_REFERENCES_RESOURCE = "layout_references_resource"
    COMPONENT_USES_VIEW_ID = "component_uses_view_id"
    COMPONENT_USES_COMPOSE = "component_uses_compose"
    MODULE_DEPENDS_ON_MODULE = "module_depends_on_module"
    MODULE_DECLARES_PLUGIN = "module_declares_plugin"
    MODULE_DECLARES_VARIANT = "module_declares_variant"
    MODULE_CONTAINS_MANIFEST = "module_contains_manifest"
    MODULE_CONTAINS_LAYOUT = "module_contains_layout"


class AndroidArtifactCategory(str, Enum):
    PROJECT = "android_project"
    MANIFEST = "android_manifest"
    COMPONENT = "android_component"
    INTENT_FILTER = "android_intent_filter"
    DEEPLINK = "android_deeplink"
    PERMISSION = "android_permission"
    LAYOUT = "android_layout"
    RESOURCE_ID = "android_resource_id"
    RESOURCE_REF = "android_resource_ref"
    COMPOSE_SIGNAL = "android_compose_signal"
    BINDING_SIGNAL = "android_binding_signal"
    MODULE = "android_module"
    GRADLE_PLUGIN = "android_gradle_plugin"
    GRADLE_DEPENDENCY = "android_gradle_dependency"
