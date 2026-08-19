# studio/views/regenerate_thread.py
from PySide6.QtCore import QThread, Signal
from .table_generator import TableGenerator, ResponseType, ChunkStrategy, SourceType


class RegenerateThread(QThread):
    """Thread for regenerating selected items."""

    progress_update = Signal(int, int)
    item_complete = Signal(int, str, list)
    complete = Signal(list)
    error = Signal(str)

    def __init__(self, results, columns, col_index, rows, settings, selected_only, llm, db):
        super().__init__()
        self.results = results
        self.columns = columns
        self.col_index = col_index
        self.rows = rows
        self.settings = settings
        self.selected_only = selected_only
        self.llm = llm
        self.db = db

    def run(self):
        try:
            total = len(self.rows)
            processed = 0

            for row_idx in self.rows:
                # Get the item data
                if row_idx < len(self.results[0]):
                    item_data = self.results[0][row_idx]
                else:
                    continue

                # Get chunks for this item
                chunks = item_data.get('chunks', [])
                if not chunks:
                    # If no chunks, try to get from source text
                    # For simplicity, we'll use a placeholder
                    chunks = [item_data.get('context', '')]

                # Generate new item with updated settings
                new_item = self._generate_item(chunks)

                # Update results
                self.results[0][row_idx]['item'] = new_item

                # Emit progress
                processed += 1
                self.progress_update.emit(processed, total)
                self.item_complete.emit(row_idx, new_item, chunks)

            self.complete.emit(self.results)

        except Exception as e:
            self.error.emit(str(e))

    def _generate_item(self, chunks: list) -> str:
        """Generate a single item with updated settings."""
        # Extract settings
        creativity = self.settings.get('creativity', 0.5)
        max_tokens = self.settings.get('max_tokens', 200)
        response_type = self.settings.get('response_type', 'Sentence')
        min_size = self.settings.get('min_size', 2)
        max_size = self.settings.get('max_size', 6)
        temperature = self.settings.get('temperature', 0.7)
        top_p = self.settings.get('top_p', 0.9)

        # Build context
        context = '\n\n'.join(chunks[:5])

        # Determine format instruction
        if response_type == "Sentence":
            format_instruction = f"Provide a response in 1 sentence ({min_size}-{max_size} words)."
        elif response_type == "Paragraph":
            format_instruction = f"Provide a response in 1 paragraph ({min_size}-{max_size} sentences)."
        else:
            format_instruction = f"Provide a response as an article ({min_size}-{max_size} paragraphs)."

        # Build prompt
        if creativity < 0.3:
            style = "Extract the information directly and literally."
        elif creativity < 0.7:
            style = "Summarize the information clearly and concisely."
        else:
            style = "Write in a creative, engaging, and expressive style."

        prompt = f"""Based on the following context, provide a response:

CONTEXT:
{context}

{format_instruction}
{style}

RESPONSE:"""

        try:
            response = self.llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=["###", "---", "```"]
            )
            content = response['choices'][0]['text'].strip()
            return content
        except Exception as e:
            print(f"⚠️ Regeneration error: {e}")
            return f"[Error: {str(e)}]"