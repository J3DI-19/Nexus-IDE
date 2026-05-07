from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class RuntimeArtifactType(str, Enum):
    STACK_TRACE = "stack_trace"
    BUILD_FAILURE = "build_failure"
    TEST_FAILURE = "test_failure"
    COMPILER_ERROR = "compiler_error"
    RUNTIME_EXCEPTION = "runtime_exception"

class StackTraceFrame(BaseModel):
    file_path: str
    line_number: int
    symbol_name: Optional[str] = None
    context_line: Optional[str] = None

class RuntimeArtifact(BaseModel):
    artifact_type: RuntimeArtifactType
    message: str
    frames: List[StackTraceFrame] = Field(default_factory=list)
    raw_log: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
