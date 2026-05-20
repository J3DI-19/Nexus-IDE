from pydantic import BaseModel
from typing import List, Optional

class ProjectMetadata(BaseModel):
    root_path: str
    project_name: str
    frameworks_detected: List[str] = []
    entry_points: List[str] = []
    android_detected: bool = False
    android_detection_reasons: List[str] = []
