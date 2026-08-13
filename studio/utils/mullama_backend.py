"""
Mullama Backend - Rust-powered GGUF model runner
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Dict, List, Any
import platform


class MullamaBackend:
    """Qwen backend using Mullama (Rust-powered GGUF runner)"""

    def __init__(self):
        self.model_path = None
        self.model_loaded = False
        self.model = None
        self.context = None
        self.model_info = {}

        # Find the model
        self._find_model()
        if self.model_path:
            self._load_model_info()
            self._try_load_model()

    def _find_model(self):
        """Find the Qwen model file in common locations"""
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent

        search_paths = [
            # 1. In the ai_model folder (next to the project)
            project_root.parent / "ai_model" / "models" / "qwen2.5-1.5b-instruct.gguf",
            # 2. In the ai_model folder (inside the project)
            project_root / "ai_model" / "models" / "qwen2.5-1.5b-instruct.gguf",
            # 3. In the models folder (project root)
            project_root / "models" / "qwen2.5-1.5b-instruct.gguf",
            # 4. In the user's data directory
            Path.home() / ".datastudio" / "models" / "qwen2.5-1.5b-instruct.gguf",
        ]

        for path in search_paths:
            if path.exists():
                self.model_path = str(path)
                print(f"✅ Found model at: {self.model_path}")
                return

        print("⚠️ Model not found. Please run download_ai_model.py first.")

    def _load_model_info(self):
        """Load model information"""
        info_path = Path(self.model_path).parent / "model_info.json"
        if info_path.exists():
            try:
                with open(info_path, 'r') as f:
                    self.model_info = json.load(f)
                print(f"📋 Model: {self.model_info.get('model_name', 'Unknown')}")
                size = self.model_info.get('file_size', 0)
                if size > 0:
                    print(f"📊 Size: {self._format_size(size)}")
            except:
                pass

    def _format_size(self, size: int) -> str:
        """Format file size for display"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def _try_load_model(self):
        """Try to load the model with Mullama"""
        try:
            from mullama import Model, Context

            print(f"🔄 Loading model with Mullama...")

            # Load the model
            self.model = Model.load(
                self.model_path,
                n_gpu_layers=-1,  # Use GPU if available
                n_ctx=4096,  # Context window
                use_mlock=False,  # Don't lock memory
                use_mmap=True  # Memory map for faster loading
            )

            # Create a context
            self.context = Context(self.model)

            self.model_loaded = True
            print("✅ Model loaded successfully with Mullama!")
            return True

        except ImportError:
            print("⚠️ Mullama not installed. Please run: pip install mullama")
            return False
        except Exception as e:
            print(f"❌ Error loading model with Mullama: {e}")
            return False

    def is_available(self) -> bool:
        """Check if the model is available and loaded"""
        return self.model_loaded

    def is_model_downloaded(self) -> bool:
        """Check if the model file exists"""
        return self.model_path is not None and os.path.exists(self.model_path)

    def get_name(self) -> str:
        """Get the backend name"""
        return "🔒 Mullama (Qwen)"

    def get_models(self) -> List[str]:
        """Get available models"""
        return ["qwen2.5:1.5b"] if self.model_loaded else []

    def query(self, prompt: str, context: str = "", model: str = "") -> str:
        """Query the model using Mullama"""
        if not self.model_loaded:
            return "⚠️ Model not loaded. Please check the model file and install Mullama."

        full_prompt = self._build_prompt(prompt, context)

        try:
            # Use Mullama's context to generate
            response = self.context.generate(
                full_prompt,
                max_tokens=1000,
                temperature=0.7,
                top_p=0.9,
                top_k=40,
                stop=["</s>", "User:", "Question:", "Context:"],
                echo=False
            )

            # Extract the response text
            if isinstance(response, dict) and 'text' in response:
                result = response['text'].strip()
            elif isinstance(response, str):
                result = response.strip()
            else:
                result = str(response).strip()

            # Check if the result is empty or just whitespace
            if not result or result.isspace():
                return "⚠️ Empty response from model."

            return result

        except Exception as e:
            return f"⚠️ Mullama error: {str(e)}"

    def _build_prompt(self, prompt: str, context: str) -> str:
        """Build the prompt with context"""
        if context:
            return f"""You are a helpful data analyst assistant. Answer questions based on the provided context.

Context:
{context}

Question: {prompt}

Answer concisely and accurately based on the context provided. If you don't know the answer, say so."""
        return prompt

    def get_stats(self) -> Dict[str, Any]:
        """Get model statistics if available"""
        stats = {
            "loaded": self.model_loaded,
            "model_path": self.model_path,
            "model_info": self.model_info
        }

        if self.model_loaded and hasattr(self.model, 'get_stats'):
            try:
                stats.update(self.model.get_stats())
            except:
                pass

        return stats


class MullamaManager:
    """Manager for Mullama backend"""

    def __init__(self):
        self.backend = None
        self._init_backend()

    def _init_backend(self):
        """Initialize the Mullama backend"""
        try:
            self.backend = MullamaBackend()
            if self.backend.is_model_downloaded():
                print("✅ Mullama backend initialized")
            else:
                print("ℹ️ Mullama backend: No model found")
        except Exception as e:
            print(f"⚠️ Failed to initialize Mullama backend: {e}")

    def get_active_backend(self):
        """Get the active backend"""
        return self.backend if self.backend and self.backend.is_available() else None

    def get_backend_status(self) -> Dict[str, Any]:
        """Get backend status"""
        if not self.backend:
            return {"available": False, "error": "Backend not initialized"}

        return {
            "available": self.backend.is_available(),
            "model_downloaded": self.backend.is_model_downloaded(),
            "model_info": self.backend.model_info if hasattr(self.backend, 'model_info') else {},
            "name": self.backend.get_name() if self.backend.is_available() else "Not loaded"
        }

    def query(self, prompt: str, context: str = "", model: str = "") -> str:
        """Send a query using the backend"""
        if not self.backend:
            return "⚠️ Mullama backend not available. Please install mullama: pip install mullama"

        return self.backend.query(prompt, context, model)