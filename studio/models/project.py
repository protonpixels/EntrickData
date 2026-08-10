from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class Project:
    id: int
    name: str
    project_type: str
    headline: str
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]
    data_path: str
    is_active: bool = True

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            id=data['id'],
            name=data['name'],
            project_type=data['project_type'],
            headline=data.get('headline', ''),
            created_at=data.get('created_at', datetime.now()),
            updated_at=data.get('updated_at', datetime.now()),
            metadata=data.get('metadata', {}),
            data_path=data['data_path'],
            is_active=data.get('is_active', True)
        )

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'project_type': self.project_type,
            'headline': self.headline,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'metadata': self.metadata,
            'data_path': self.data_path,
            'is_active': self.is_active
        }