"""
Shared job schema and models for PlagioScale.
"""
from enum import Enum
from typing import Optional
from dataclasses import dataclass, asdict
import json
from datetime import datetime


class JobStatus(str, Enum):
    """Job lifecycle states."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class Job:
    """Job schema for plagiarism detection."""
    job_id: str
    text: str
    status: JobStatus = JobStatus.PENDING
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: str = None
    completed_at: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        d = self.to_dict()
        d['status'] = self.status.value
        return json.dumps(d)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Job':
        """Create Job from dictionary."""
        if isinstance(data['status'], str):
            data['status'] = JobStatus(data['status'])
        return cls(**data)
    
    @classmethod
    def from_json(cls, data: str) -> 'Job':
        """Create Job from JSON string."""
        return cls.from_dict(json.loads(data))
