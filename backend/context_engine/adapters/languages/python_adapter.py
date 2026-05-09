import ast
from typing import List, Set
from ..base import LanguageAdapter
from ...models.symbol import Symbol, DependencyEdge

class PythonAdapter(LanguageAdapter):
    def get_supported_extensions(self) -> Set[str]:
        return {".py"}

    def can_handle(self, rel_path: str) -> bool:
        return rel_path.lower().endswith(".py")

    def extract_symbols(self, content: str, file_path: str) -> List[Symbol]:
        symbols = []
        try:
            tree = ast.parse(content)
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    symbols.append(Symbol(
                        name=node.name,
                        type="class",
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno
                    ))
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            symbols.append(Symbol(
                                name=item.name,
                                type="method",
                                start_line=item.lineno,
                                end_line=item.end_lineno or item.lineno,
                                parent_id=node.name
                            ))
                elif isinstance(node, ast.FunctionDef):
                    symbols.append(Symbol(
                        name=node.name,
                        type="function",
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno
                    ))
        except (SyntaxError, Exception):
            pass
        return symbols

    def extract_dependencies(self, content: str, file_path: str) -> List[DependencyEdge]:
        edges = []
        try:
            tree = ast.parse(content)
            
            # Extract Imports
            for node in tree.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        edges.append(DependencyEdge(
                            source_id=file_path,
                            target_id=alias.name,
                            raw_target=alias.name,
                            type="import",
                            is_resolved=False
                        ))
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        target = f"{module}.{alias.name}" if module else alias.name
                        edges.append(DependencyEdge(
                            source_id=file_path,
                            target_id=target,
                            raw_target=target,
                            type="import",
                            is_resolved=False
                        ))
            
            # Extract inheritance and calls
            class CallVisitor(ast.NodeVisitor):
                def __init__(self, current_file):
                    self.current_file = current_file
                    self.current_symbol = None

                def visit_ClassDef(self, node):
                    old_sym = self.current_symbol
                    self.current_symbol = node.name
                    # Extract inheritance
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            edges.append(DependencyEdge(
                                source_id=f"{self.current_file}:{node.name}",
                                target_id=base.id,
                                raw_target=base.id,
                                type="inheritance",
                                is_resolved=False
                            ))
                    self.generic_visit(node)
                    self.current_symbol = old_sym

                def visit_FunctionDef(self, node):
                    old_sym = self.current_symbol
                    self.current_symbol = node.name
                    self.generic_visit(node)
                    self.current_symbol = old_sym
                
                def visit_Call(self, node):
                    if isinstance(node.func, ast.Name) and self.current_symbol:
                        edges.append(DependencyEdge(
                            source_id=f"{self.current_file}:{self.current_symbol}",
                            target_id=node.func.id,
                            raw_target=node.func.id,
                            type="call",
                            is_resolved=False,
                            metadata={"line": str(node.lineno)}
                        ))
                    self.generic_visit(node)

            CallVisitor(file_path).visit(tree)

        except (SyntaxError, Exception):
            pass
        return edges
