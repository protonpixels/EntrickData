from enum import Enum


class ColumnType(Enum):
    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    CATEGORY = "category"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE_PATH = "file_path"
    URL = "url"
    EMAIL = "email"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"

    @classmethod
    def get_display_name(cls, type_val):
        display_names = {
            cls.TEXT.value: "Text",
            cls.INTEGER.value: "Integer",
            cls.FLOAT.value: "Float",
            cls.CATEGORY.value: "Category",
            cls.IMAGE.value: "🖼️ Image",
            cls.VIDEO.value: "🎬 Video",
            cls.AUDIO.value: "🎵 Audio",
            cls.FILE_PATH.value: "📁 File Path",
            cls.URL.value: "🔗 URL",
            cls.EMAIL.value: "✉️ Email",
            cls.DATE.value: "📅 Date",
            cls.DATETIME.value: "📅 Date & Time",
            cls.BOOLEAN.value: "✅ Boolean"
        }
        return display_names.get(type_val, "Text")

    @classmethod
    def get_all_types(cls):
        return [(t.value, cls.get_display_name(t.value)) for t in cls]

    @classmethod
    def is_file_type(cls, type_val):
        return type_val in [cls.IMAGE.value, cls.VIDEO.value, cls.AUDIO.value, cls.FILE_PATH.value]

    @classmethod
    def is_media_type(cls, type_val):
        return type_val in [cls.IMAGE.value, cls.VIDEO.value, cls.AUDIO.value]

