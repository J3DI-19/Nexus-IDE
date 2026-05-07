import re
from typing import List
from ..base import FrameworkAdapter
from ...models.artifact import FrameworkArtifact

class ReactAdapter(FrameworkAdapter):
    def can_handle(self, rel_path: str) -> bool:
        ext = rel_path.lower().split('.')[-1]
        return ext in {"jsx", "tsx", "js", "ts"}

    def extract_artifacts(self, content: str, file_path: str) -> List[FrameworkArtifact]:
        artifacts = []
        
        # Simple regex-based detection for React components and hooks
        # A more robust solution would use a JS/TS AST parser (like esprima in JS, but we are in Python).
        # We use deterministic regex heuristics for now.
        
        lines = content.splitlines()
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Component detection: function ComponentName(props) or const ComponentName = (props) =>
            comp_match = re.search(r'(?:function|const|let|var)\s+([A-Z][a-zA-Z0-9_]*)\s*(?:=|=>|\()', line)
            if comp_match:
                name = comp_match.group(1)
                artifacts.append(FrameworkArtifact(
                    artifact_type="REACT_COMPONENT",
                    name=name,
                    rel_path=file_path,
                    start_line=line_num,
                    end_line=line_num,  # Simplification, without AST we don't know the exact end
                    metadata={}
                ))
            
            # Hook detection: useHookName
            hook_match = re.search(r'\b(use[A-Z][a-zA-Z0-9_]*)\b', line)
            if hook_match:
                name = hook_match.group(1)
                # Avoid registering standard react imports as declarations if they are just imports, 
                # but for simplicity we log hook usage.
                if "import" not in line:
                    artifacts.append(FrameworkArtifact(
                        artifact_type="REACT_HOOK_USAGE",
                        name=name,
                        rel_path=file_path,
                        start_line=line_num,
                        end_line=line_num,
                        metadata={}
                    ))
                    
        return artifacts
