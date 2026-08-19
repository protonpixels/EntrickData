# utils/container_manager.py
from typing import List, Dict, Optional
from models.container import Container


class ContainerManager:
    """Manages project containers (folders)."""

    def __init__(self, db):
        self.db = db

    def create_container(self, name: str, parent_id: Optional[int] = None) -> Container:
        """Create a new container."""
        cursor = self.db.conn.cursor()
        cursor.execute(
            'INSERT INTO containers (name, parent_id) VALUES (?, ?)',
            (name, parent_id)
        )
        self.db.conn.commit()
        container_id = cursor.lastrowid
        return Container(name, container_id, parent_id)

    def delete_container(self, container_id: int):
        """Delete a container and move projects to parent."""
        cursor = self.db.conn.cursor()

        # Get parent container
        cursor.execute('SELECT parent_id FROM containers WHERE id = ?', (container_id,))
        result = cursor.fetchone()
        parent_id = result[0] if result else None

        # Move projects to parent container
        cursor.execute(
            'UPDATE projects SET container_id = ? WHERE container_id = ?',
            (parent_id, container_id)
        )

        # Delete container
        cursor.execute('DELETE FROM containers WHERE id = ?', (container_id,))
        self.db.conn.commit()

    def get_container_tree(self) -> List[Dict]:
        """Get nested container tree."""
        cursor = self.db.conn.cursor()

        # Get all containers
        cursor.execute('SELECT id, name, parent_id FROM containers ORDER BY name')
        containers = cursor.fetchall()

        # Build tree
        container_map = {}
        for c_id, name, parent_id in containers:
            container_map[c_id] = {
                'id': c_id,
                'name': name,
                'parent_id': parent_id,
                'children': [],
                'projects': []
            }

        # Build hierarchy
        root_containers = []
        for c_id, container in container_map.items():
            if container['parent_id'] is None:
                root_containers.append(container)
            else:
                parent = container_map.get(container['parent_id'])
                if parent:
                    parent['children'].append(container)

        # Add projects to containers
        for project in self.db.get_all_projects():
            container_id = project.get('container_id')
            if container_id and container_id in container_map:
                container_map[container_id]['projects'].append(project)
            else:
                # Add to "Uncategorized" pseudo-container
                pass

        return root_containers