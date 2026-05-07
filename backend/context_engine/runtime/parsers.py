import re
from typing import List, Optional
from .models import RuntimeArtifact, RuntimeArtifactType, StackTraceFrame

class RuntimeParser:
    """
    Deterministic regex-based parsers for various execution environments.
    """
    
    # Python: File "main.py", line 15, in <module>
    PYTHON_FRAME_REGEX = r'File "(.*?)", line (\d+), in (.*)'
    
    # JS: at Object.<anonymous> (E:\Nexus-IDE\backend\main.py:10:5)
    # or: at myFunction (index.js:5:10)
    JS_FRAME_REGEX = r'at (?:(.*?)\s+)?\(?(.*?):(\d+):(\d+)\)?'
    
    # TS: src/App.tsx(10,5): error TS2322: Type '...'
    TS_ERROR_REGEX = r'(.*?)\((\d+),(\d+)\): error (TS\d+): (.*)'
    
    # Java: at com.example.MyClass.method(MyClass.java:15)
    JAVA_FRAME_REGEX = r'at ([\w\.$]+)\((.*?):(\d+)\)'

    # C#: at MyNamespace.MyClass.MyMethod(Type arg) in C:\path\file.cs:line 15
    CSHARP_FRAME_REGEX = r'at (.*?) in (.*?):line (\d+)'

    # C++ GCC/Clang: at main (test.cpp:15) or #0 0x... in main () at test.cpp:15
    CPP_GCC_FRAME_REGEX = r'(?:at|in)\s+(.*?)\s+\((.*?):(\d+)\)'
    # C++ MSVC: test.cpp(15): error C2065: ...
    CPP_MSVC_ERROR_REGEX = r'(.*?)\((\d+)\): (?:error|warning) (.*?): (.*)'

    def parse_python_stacktrace(self, log: str) -> RuntimeArtifact:
        frames = []
        matches = re.finditer(self.PYTHON_FRAME_REGEX, log)
        for match in matches:
            frames.append(StackTraceFrame(
                file_path=match.group(1),
                line_number=int(match.group(2)),
                symbol_name=match.group(3)
            ))
        
        lines = [l.strip() for l in log.splitlines() if l.strip()]
        message = lines[-1] if lines else "Unknown Python Error"
        
        return RuntimeArtifact(
            artifact_type=RuntimeArtifactType.STACK_TRACE,
            message=message,
            frames=frames,
            raw_log=log,
            metadata={"lang": "python"}
        )

    def parse_js_stacktrace(self, log: str) -> RuntimeArtifact:
        frames = []
        matches = re.finditer(self.JS_FRAME_REGEX, log)
        for match in matches:
            frames.append(StackTraceFrame(
                file_path=match.group(2),
                line_number=int(match.group(3)),
                symbol_name=match.group(1)
            ))
            
        lines = [l.strip() for l in log.splitlines() if l.strip()]
        message = lines[0] if lines else "Unknown JS Error"

        return RuntimeArtifact(
            artifact_type=RuntimeArtifactType.STACK_TRACE,
            message=message,
            frames=frames,
            raw_log=log,
            metadata={"lang": "javascript"}
        )

    def parse_pytest_failure(self, log: str) -> RuntimeArtifact:
        frames = []
        # Pytest shows failing line with '>'
        matches = re.finditer(r'>\s+(.*)', log)
        for match in matches:
            frames.append(StackTraceFrame(
                file_path="Unknown (pytest)",
                line_number=0,
                context_line=match.group(1)
            ))
            
        # Try to find specific error like 'E   AssertionError: ...'
        error_match = re.search(r'E\s+([A-Za-z]+Error:.*)', log)
        message = error_match.group(1) if error_match else "Pytest Test Failure"
        
        return RuntimeArtifact(
            artifact_type=RuntimeArtifactType.TEST_FAILURE,
            message=message,
            frames=frames,
            raw_log=log,
            metadata={"framework": "pytest"}
        )

    def parse_ts_compiler_error(self, log: str) -> RuntimeArtifact:
        frames = []
        message = "TypeScript Compiler Error"
        
        matches = list(re.finditer(self.TS_ERROR_REGEX, log))
        for match in matches:
            frames.append(StackTraceFrame(
                file_path=match.group(1).strip(),
                line_number=int(match.group(2)),
                symbol_name=match.group(4) # TS error code
            ))
        
        if matches:
            message = matches[0].group(5) # The actual error description of the first error
            
        return RuntimeArtifact(
            artifact_type=RuntimeArtifactType.COMPILER_ERROR,
            message=message,
            frames=frames,
            raw_log=log,
            metadata={"lang": "typescript"}
        )

    def parse_java_stacktrace(self, log: str) -> RuntimeArtifact:
        frames = []
        matches = re.finditer(self.JAVA_FRAME_REGEX, log)
        for match in matches:
            frames.append(StackTraceFrame(
                file_path=match.group(2),
                line_number=int(match.group(3)),
                symbol_name=match.group(1)
            ))
            
        lines = [l.strip() for l in log.splitlines() if l.strip()]
        message = lines[0] if lines else "Unknown Java Error"

        return RuntimeArtifact(
            artifact_type=RuntimeArtifactType.STACK_TRACE,
            message=message,
            frames=frames,
            raw_log=log,
            metadata={"lang": "java"}
        )

    def parse_csharp_stacktrace(self, log: str) -> RuntimeArtifact:
        frames = []
        matches = re.finditer(self.CSHARP_FRAME_REGEX, log)
        for match in matches:
            # Match 1: symbol (namespace.class.method)
            # Match 2: file path
            # Match 3: line number
            frames.append(StackTraceFrame(
                file_path=match.group(2),
                line_number=int(match.group(3)),
                symbol_name=match.group(1).split('(')[0].strip()
            ))
            
        lines = [l.strip() for l in log.splitlines() if l.strip()]
        message = lines[0] if lines else "Unknown C# Error"

        return RuntimeArtifact(
            artifact_type=RuntimeArtifactType.STACK_TRACE,
            message=message,
            frames=frames,
            raw_log=log,
            metadata={"lang": "csharp"}
        )

    def parse_cpp_stacktrace(self, log: str) -> RuntimeArtifact:
        frames = []
        matches = re.finditer(self.CPP_GCC_FRAME_REGEX, log)
        for match in matches:
            frames.append(StackTraceFrame(
                file_path=match.group(2),
                line_number=int(match.group(3)),
                symbol_name=match.group(1).split('(')[0].strip()
            ))
            
        lines = [l.strip() for l in log.splitlines() if l.strip()]
        message = lines[0] if lines else "Unknown C++ Error"

        return RuntimeArtifact(
            artifact_type=RuntimeArtifactType.STACK_TRACE,
            message=message,
            frames=frames,
            raw_log=log,
            metadata={"lang": "cpp"}
        )

    def parse_cpp_compiler_error(self, log: str) -> RuntimeArtifact:
        frames = []
        matches = re.finditer(self.CPP_MSVC_ERROR_REGEX, log)
        for match in matches:
            frames.append(StackTraceFrame(
                file_path=match.group(1),
                line_number=int(match.group(2)),
                symbol_name=match.group(3) # Error code
            ))
            
        lines = [l.strip() for l in log.splitlines() if l.strip()]
        message = lines[0] if lines else "Unknown C++ Compiler Error"

        return RuntimeArtifact(
            artifact_type=RuntimeArtifactType.COMPILER_ERROR,
            message=message,
            frames=frames,
            raw_log=log,
            metadata={"lang": "cpp"}
        )

    def parse_gradle_failure(self, log: str) -> RuntimeArtifact:
        task_match = re.search(r'Execution failed for task \'(.*?)\'', log)
        message = f"Gradle Build Failed at {task_match.group(1)}" if task_match else "Gradle Build Failed"
        
        return RuntimeArtifact(
            artifact_type=RuntimeArtifactType.BUILD_FAILURE,
            message=message,
            frames=[],
            raw_log=log,
            metadata={"framework": "gradle"}
        )
        
    def parse_vite_react_error(self, log: str) -> RuntimeArtifact:
        lines = [l.strip() for l in log.splitlines() if l.strip()]
        message = lines[0] if lines else "Vite/React Error"
        
        return RuntimeArtifact(
            artifact_type=RuntimeArtifactType.BUILD_FAILURE,
            message=message,
            frames=[],
            raw_log=log,
            metadata={"framework": "react"}
        )

    def parse_generic_failure(self, log: str) -> RuntimeArtifact:
        return RuntimeArtifact(
            artifact_type=RuntimeArtifactType.RUNTIME_EXCEPTION,
            message="Raw Execution Log",
            raw_log=log,
            frames=[]
        )
