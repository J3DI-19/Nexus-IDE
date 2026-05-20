from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class AndroidDiagnostic(BaseModel):
    severity: str
    code: str
    message: str
    source_path: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    details: Optional[str] = None


class AndroidIntentFilter(BaseModel):
    actions: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    data: List[Dict[str, str]] = Field(default_factory=list)
    auto_verify: bool = False
    is_launcher: bool = False


class AndroidDeepLink(BaseModel):
    scheme: Optional[str] = None
    host: Optional[str] = None
    port: Optional[str] = None
    path: Optional[str] = None
    path_prefix: Optional[str] = None
    path_pattern: Optional[str] = None
    mime_type: Optional[str] = None
    auto_verify: bool = False


class AndroidPermission(BaseModel):
    name: str
    permission_type: str
    max_sdk_version: Optional[str] = None
    uses_permission_flags: Optional[str] = None
    source_path: str


class AndroidComponent(BaseModel):
    component_type: str
    name: str
    exported: Optional[bool] = None
    enabled: Optional[bool] = None
    permission: Optional[str] = None
    process: Optional[str] = None
    source_path: str
    attributes: Dict[str, str] = Field(default_factory=dict)
    intent_filters: List[AndroidIntentFilter] = Field(default_factory=list)
    deep_links: List[AndroidDeepLink] = Field(default_factory=list)


class AndroidManifestModel(BaseModel):
    source_path: str
    package_name: Optional[str] = None
    namespace: Optional[str] = None
    application_attributes: Dict[str, str] = Field(default_factory=dict)
    activities: List[AndroidComponent] = Field(default_factory=list)
    services: List[AndroidComponent] = Field(default_factory=list)
    receivers: List[AndroidComponent] = Field(default_factory=list)
    providers: List[AndroidComponent] = Field(default_factory=list)
    permissions: List[AndroidPermission] = Field(default_factory=list)
    launcher_activity: Optional[str] = None
    malformed: bool = False
    diagnostics: List[AndroidDiagnostic] = Field(default_factory=list)


class AndroidRelationship(BaseModel):
    relationship_type: str
    source_id: str
    target_id: str
    metadata: Dict[str, str] = Field(default_factory=dict)


class AndroidProjectModel(BaseModel):
    root_path: str
    project_name: str
    manifests_discovered: int = 0
    package_names: List[str] = Field(default_factory=list)
    launcher_activities: List[str] = Field(default_factory=list)


class AndroidResourceRef(BaseModel):
    ref_type: str
    value: str
    source_path: str
    element_tag: Optional[str] = None
    attribute: Optional[str] = None


class AndroidUiElement(BaseModel):
    tag: str
    element_id: Optional[str] = None
    attributes: Dict[str, str] = Field(default_factory=dict)


class AndroidLayoutModel(BaseModel):
    source_path: str
    layout_name: str
    root_tag: Optional[str] = None
    malformed: bool = False
    resource_ids: List[str] = Field(default_factory=list)
    resource_refs: List[AndroidResourceRef] = Field(default_factory=list)
    ui_elements: List[AndroidUiElement] = Field(default_factory=list)
    diagnostics: List[AndroidDiagnostic] = Field(default_factory=list)


class AndroidUiLink(BaseModel):
    link_type: str
    source_id: str
    target_id: str
    source_path: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)


class AndroidComposeSignal(BaseModel):
    source_path: str
    confidence: float = 0.5
    evidence: List[str] = Field(default_factory=list)


class AndroidBindingSignal(BaseModel):
    source_path: str
    binding_type: str
    class_name: Optional[str] = None
    confidence: float = 0.5
    evidence: List[str] = Field(default_factory=list)


class AndroidUiSummary(BaseModel):
    layouts: List[AndroidLayoutModel] = Field(default_factory=list)
    links: List[AndroidUiLink] = Field(default_factory=list)
    compose_signals: List[AndroidComposeSignal] = Field(default_factory=list)
    binding_signals: List[AndroidBindingSignal] = Field(default_factory=list)
    diagnostics: List[AndroidDiagnostic] = Field(default_factory=list)


class AndroidDependency(BaseModel):
    notation: str
    configuration: str
    dependency_type: str
    source_path: str
    target_module: Optional[str] = None


class AndroidVariantModel(BaseModel):
    build_types: List[str] = Field(default_factory=list)
    product_flavors: List[str] = Field(default_factory=list)


class AndroidModuleModel(BaseModel):
    module_path: str
    module_dir: str
    build_file: Optional[str] = None
    manifest_paths: List[str] = Field(default_factory=list)
    layout_paths: List[str] = Field(default_factory=list)
    plugins: List[str] = Field(default_factory=list)
    namespace: Optional[str] = None
    compile_sdk: Optional[str] = None
    min_sdk: Optional[str] = None
    target_sdk: Optional[str] = None
    variants: AndroidVariantModel = Field(default_factory=AndroidVariantModel)
    dependencies: List[AndroidDependency] = Field(default_factory=list)
    diagnostics: List[AndroidDiagnostic] = Field(default_factory=list)


class AndroidGradleModel(BaseModel):
    settings_file: Optional[str] = None
    root_build_file: Optional[str] = None
    modules_discovered: int = 0
    plugins: List[str] = Field(default_factory=list)
    diagnostics: List[AndroidDiagnostic] = Field(default_factory=list)


class AndroidRetrievalSignal(BaseModel):
    signal_type: str
    weight: float
    evidence: str
    source_artifact_ids: List[str] = Field(default_factory=list)


class AndroidRetrievalContext(BaseModel):
    enabled: bool = False
    is_android_project: bool = False
    active_module: Optional[str] = None
    active_component_candidates: List[str] = Field(default_factory=list)
    related_layouts: List[str] = Field(default_factory=list)
    related_resources: List[str] = Field(default_factory=list)
    runtime_tags: List[str] = Field(default_factory=list)
    integration_tags: List[str] = Field(default_factory=list)
    integration_file_hints: List[str] = Field(default_factory=list)
    integration_module_hints: List[str] = Field(default_factory=list)
    signals: List[AndroidRetrievalSignal] = Field(default_factory=list)


class AndroidRetrievalSignalSummary(BaseModel):
    count: int = 0
    top_signals: List[AndroidRetrievalSignal] = Field(default_factory=list)


class AndroidRuntimeSignal(BaseModel):
    category: str
    severity: str
    message: str
    module: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    symbol: Optional[str] = None
    raw_excerpt: Optional[str] = None
    confidence: str = "low"


class AndroidFailureContext(BaseModel):
    failure_kind: str
    stage: str
    implicated_modules: List[str] = Field(default_factory=list)
    implicated_files: List[str] = Field(default_factory=list)
    implicated_symbols: List[str] = Field(default_factory=list)
    probable_root: Optional[str] = None
    confidence: str = "low"


class AndroidRuntimeSignalsSummary(BaseModel):
    count: int = 0
    categories: Dict[str, int] = Field(default_factory=dict)
    signals: List[AndroidRuntimeSignal] = Field(default_factory=list)
    failure_contexts: List[AndroidFailureContext] = Field(default_factory=list)
    diagnostics: List[AndroidDiagnostic] = Field(default_factory=list)


class AndroidIntegrationSignal(BaseModel):
    source: str
    category: str
    severity: str = "info"
    message: str
    module: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    evidence: Optional[str] = None


class AndroidIntegrationsSummary(BaseModel):
    enabled: bool = False
    configured_sources: List[str] = Field(default_factory=list)
    signals: List[AndroidIntegrationSignal] = Field(default_factory=list)
    diagnostics: List[AndroidDiagnostic] = Field(default_factory=list)


class AndroidSummaryResponse(BaseModel):
    enabled: bool
    is_android_project: bool
    feature_flag_source: str
    detection_reasons: List[str] = Field(default_factory=list)
    project: AndroidProjectModel
    manifests: List[AndroidManifestModel] = Field(default_factory=list)
    ui: AndroidUiSummary = Field(default_factory=AndroidUiSummary)
    relationships: List[AndroidRelationship] = Field(default_factory=list)
    retrieval_signals: AndroidRetrievalSignalSummary = Field(default_factory=AndroidRetrievalSignalSummary)
    diagnostics: List[AndroidDiagnostic] = Field(default_factory=list)
    modules: List[AndroidModuleModel] = Field(default_factory=list)
    gradle: AndroidGradleModel = Field(default_factory=AndroidGradleModel)
    runtime_signals: AndroidRuntimeSignalsSummary = Field(default_factory=AndroidRuntimeSignalsSummary)
    integrations: AndroidIntegrationsSummary = Field(default_factory=AndroidIntegrationsSummary)
