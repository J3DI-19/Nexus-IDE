from abc import ABC, abstractmethod
from typing import List, Set, Optional, Dict
from ..models.symbol import Symbol, DependencyEdge
from ..models.file import FileMetadata
from ..models.artifact import FrameworkArtifact

class BaseAdapter(ABC):
    @abstractmethod
    def can_handle(self, rel_path: str) -> bool:
        """Returns True if this adapter can process the given file."""
        pass

class LanguageAdapter(BaseAdapter):
    @abstractmethod
    def get_supported_extensions(self) -> Set[str]:
        """Returns a set of file extensions this adapter handles."""
        pass

    @abstractmethod
    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        """Extracts high-level symbols from the code."""
        pass

    @abstractmethod
    def extract_dependencies(self, content: str, file_path: str) -> List[DependencyEdge]:
        """Extracts imports and other dependencies."""
        pass

class FrameworkAdapter(BaseAdapter):
    @abstractmethod
    def extract_artifacts(self, content: str, file_path: str) -> List[FrameworkArtifact]:
        """Extracts framework-specific artifacts (e.g., API routes, hooks)."""
        pass
