from typing import List, Dict, Type, Optional
from .base import LanguageAdapter, FrameworkAdapter

class AdapterRegistry:
    def __init__(self):
        self._language_adapters: List[LanguageAdapter] = []
        self._framework_adapters: List[FrameworkAdapter] = []
        self._extension_map: Dict[str, LanguageAdapter] = {}

    def register_language_adapter(self, adapter: LanguageAdapter):
        self._language_adapters.append(adapter)
        for ext in adapter.get_supported_extensions():
            # In a deterministic system, first registered or most specific wins.
            # For now, we'll just map it.
            self._extension_map[ext.lower()] = adapter

    def register_framework_adapter(self, adapter: FrameworkAdapter):
        self._framework_adapters.append(adapter)

    def get_adapter_for_file(self, rel_path: str) -> Optional[LanguageAdapter]:
        import os
        ext = os.path.splitext(rel_path)[1].lower()
        return self._extension_map.get(ext)

    def get_framework_adapters_for_file(self, rel_path: str) -> List[FrameworkAdapter]:
        return [adapter for adapter in self._framework_adapters if adapter.can_handle(rel_path)]

# Global singleton for the registry
registry = AdapterRegistry()
