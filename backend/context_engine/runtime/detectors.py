from typing import Optional
from .models import RuntimeArtifact
from .parsers import RuntimeParser

class RuntimeDetector:
    """
    Analyzes raw logs to deterministically identify the execution environment
    and route to the appropriate parser.
    """
    def __init__(self):
        self.parser = RuntimeParser()

    def detect_and_parse(self, log: str) -> Optional[RuntimeArtifact]:
        # 1. Pytest Failure
        if "=== FAILURES ===" in log or "E   " in log or "AssertionError" in log:
            return self.parser.parse_pytest_failure(log)
            
        # 2. TypeScript Compiler Error
        if "error TS" in log:
            return self.parser.parse_ts_compiler_error(log)
            
        # 3. Java / Kotlin Stack Trace
        if "Exception in thread" in log or "java.lang." in log or "\tat " in log:
            if "Execution failed for task" in log or "BUILD FAILED" in log:
                return self.parser.parse_gradle_failure(log)
            return self.parser.parse_java_stacktrace(log)
            
        # 3.5 C# / .NET Stack Trace
        if " in " in log and ":line " in log and "at " in log:
            return self.parser.parse_csharp_stacktrace(log)
            
        # 3.6 C++ Stack Trace / Compiler Error
        if (" at " in log or " in " in log) and (":" in log and "(" in log):
            # Check for MSVC style error first
            if " error " in log or " warning " in log:
                return self.parser.parse_cpp_compiler_error(log)
            return self.parser.parse_cpp_stacktrace(log)
            
        # 4. Vite / React Error
        if "[vite]" in log or "React will try to recreate this component" in log:
            return self.parser.parse_vite_react_error(log)
            
        # 5. Generic Python Stack Trace
        if 'Traceback (most recent call last):' in log or ('File "' in log and 'line ' in log):
            return self.parser.parse_python_stacktrace(log)
            
        # 6. Generic JS Stack Trace
        if 'at ' in log and (':' in log) and ('Error:' in log or 'Exception' in log):
            return self.parser.parse_js_stacktrace(log)
            
        # 7. Fallback
        return self.parser.parse_generic_failure(log)
