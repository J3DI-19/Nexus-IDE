from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class PromptMode(str, Enum):
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    ARCHITECTURE = "architecture"

class PromptSection(BaseModel):
    title: str
    content: str
    order: int

class PromptWarning(BaseModel):
    severity: str # "HIGH", "MEDIUM", "LOW"
    message: str
    affected_path: str

class PromptContext(BaseModel):
    mode: PromptMode
    task: str
    sections: List[PromptSection] = Field(default_factory=list)
    warnings: List[PromptWarning] = Field(default_factory=list)
    
    def render(self) -> str:
        # Sort sections by order
        sorted_sections = sorted(self.sections, key=lambda s: s.order)
        
        output = []
        # Header
        output.append(f"--- ENGINEERING BRIEFING: {self.mode.upper()} ---")
        output.append(f"GOAL: {self.task}")
        output.append("-" * 40)
        
        # Warnings
        if self.warnings:
            output.append("\n### [CRITICAL WARNINGS & CONSTRAINTS]")
            for w in self.warnings:
                output.append(f"[{w.severity}] {w.affected_path}: {w.message}")
        
        # Sections
        for sec in sorted_sections:
            output.append(f"\n### [{sec.title.upper()}]")
            output.append(sec.content)
            
        output.append("\n--- END OF BRIEFING ---")
        return "\n".join(output)
