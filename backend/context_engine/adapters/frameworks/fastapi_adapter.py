import ast
from typing import List
from ..base import FrameworkAdapter
from ...models.artifact import FrameworkArtifact

class FastAPIAdapter(FrameworkAdapter):
    def can_handle(self, rel_path: str) -> bool:
        return rel_path.lower().endswith(".py")

    def extract_artifacts(self, content: str, file_path: str) -> List[FrameworkArtifact]:
        artifacts = []
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Check for route decorators (e.g. @app.get("/path"), @router.post("/path"))
                    for decorator in node.decorator_list:
                        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                            method = decorator.func.attr.upper()
                            if method in {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}:
                                route_path = ""
                                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                                    route_path = decorator.args[0].value
                                
                                artifacts.append(FrameworkArtifact(
                                    artifact_type="API_ROUTE",
                                    name=node.name,
                                    rel_path=file_path,
                                    start_line=node.lineno,
                                    end_line=node.end_lineno or node.lineno,
                                    metadata={
                                        "method": method,
                                        "route": route_path
                                    }
                                ))
        except Exception:
            pass
            
        return artifacts
