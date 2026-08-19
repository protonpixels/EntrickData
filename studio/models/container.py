# models/container.py
from datetime import datetime


class Container:
    """Folder-like container for organizing projects."""

    def __init__(self, name: str, container_id: int = None, parent_id: int = None):
        self.id = container_id
        self.name = name
        self.parent_id = parent_id  # For nested containers
        self.project_ids = []  # IDs of projects in this container
        self.created_at = datetime.now()
        self.updated_at = datetime.now()