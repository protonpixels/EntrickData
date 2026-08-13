from enum import Enum


class ProjectType(Enum):
    DATA_TABLE = "data_table"
    DATA_RESEARCH = "data_research"
    DATA_DOCUMENT = "data_document"
    DATA_CHAT = "data_chat"  # New chat project type

    @classmethod
    def get_display_name(cls, project_type):
        return {
            cls.DATA_TABLE.value: "📊 Data Table",
            cls.DATA_RESEARCH.value: "🌐 Data Research",
            cls.DATA_DOCUMENT.value: "📄 Data Document",
            cls.DATA_CHAT.value: "💬 Data Chat"
        }.get(project_type, "Unknown")

    @classmethod
    def get_all_types(cls):
        return [(t.value, cls.get_display_name(t.value)) for t in cls]

    @classmethod
    def get_icon(cls, project_type):
        return {
            cls.DATA_TABLE.value: "📊",
            cls.DATA_RESEARCH.value: "🌐",
            cls.DATA_DOCUMENT.value: "📄",
            cls.DATA_CHAT.value: "💬"
        }.get(project_type, "📁")

    @classmethod
    def get_description(cls, project_type):
        return {
            cls.DATA_TABLE.value: "Create structured datasets with custom columns and data entry",
            cls.DATA_RESEARCH.value: "Extract and analyze content from web pages",
            cls.DATA_DOCUMENT.value: "Process and analyze documents (PDF, DOCX, TXT)",
            cls.DATA_CHAT.value: "AI-powered chat to query your data across projects"
        }.get(project_type, "")