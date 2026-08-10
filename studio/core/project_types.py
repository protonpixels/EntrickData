from enum import Enum


class ProjectType(Enum):
    DATA_TABLE = "data_table"
    DATA_RESEARCH = "data_research"

    @classmethod
    def get_display_name(cls, project_type):
        return {
            cls.DATA_TABLE.value: "📊 Data Table",
            cls.DATA_RESEARCH.value: "🌐 Data Research"
        }.get(project_type, "Unknown")

    @classmethod
    def get_all_types(cls):
        return [(t.value, cls.get_display_name(t.value)) for t in cls]

    @classmethod
    def get_icon(cls, project_type):
        return {
            cls.DATA_TABLE.value: "📊",
            cls.DATA_RESEARCH.value: "🌐"
        }.get(project_type, "📁")