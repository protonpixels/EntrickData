#!/usr/bin/env python
"""
Download Qwen AI Model
Downloads the Qwen2.5 1.5B model directly into the ai_model folder.
100% offline after download - no external dependencies required.
"""

import os
import sys
import requests
import json
import time
import hashlib
from pathlib import Path
import subprocess
import platform


class QwenModelDownloader:
    """Download Qwen model directly to the ai_model folder"""
    
    def __init__(self):
        # Get the directory where this script is located
        self.script_dir = Path(__file__).parent.absolute()
        self.model_dir = self.script_dir / "models"
        self.model_dir.mkdir(exist_ok=True)
        
        # Model file paths
        self.model_file = self.model_dir / "qwen2.5-1.5b-instruct.gguf"
        self.model_info_file = self.model_dir / "model_info.json"
        
        # Model info
        self.model_url = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
        self.model_name = "Qwen2.5 1.5B Instruct"
        self.expected_size = 1_100_000_000  # ~1.1 GB
        self.expected_hash = None  # We'll compute this after download
    
    def print_header(self):
        """Print a nice header"""
        print("=" * 60)
        print("🤖 Qwen Model Downloader")
        print("=" * 60)
        print(f"📁 Downloading to: {self.model_dir}")
        print(f"📦 Model: {self.model_name}")
        print(f"📏 Size: ~1.1 GB")
        print("🔒 100% Offline after download")
        print("=" * 60)
        print()
    
    def check_existing_model(self):
        """Check if model already exists"""
        if self.model_file.exists():
            size = self.model_file.stat().st_size
            print(f"✅ Model already exists at: {self.model_file}")
            print(f"📊 File size: {self.format_size(size)}")
            
            # Check if it's complete
            if size > 100_000_000:  # At least 100MB
                print("✅ Model appears to be complete.")
                return True
            else:
                print("⚠️ Model file seems incomplete. Re-downloading...")
                return False
        return False
    
    def format_size(self, size):
        """Format file size for display"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def download_model(self, progress_callback=None):
        """Download the model with progress tracking"""
        print("📥 Starting download...")
        print(f"🔗 Source: {self.model_url}")
        print()
        
        try:
            # Start the download
            response = requests.get(self.model_url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            block_size = 8192
            downloaded = 0
            start_time = time.time()
            
            # Open file for writing
            with open(self.model_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=block_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Calculate progress
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            elapsed = time.time() - start_time
                            speed = downloaded / elapsed if elapsed > 0 else 0
                            
                            # Format progress bar
                            bar_length = 40
                            filled = int(bar_length * downloaded / total_size)
                            bar = '█' * filled + '░' * (bar_length - filled)
                            
                            # Format speed
                            if speed > 1024 * 1024:
                                speed_str = f"{speed / (1024 * 1024):.2f} MB/s"
                            else:
                                speed_str = f"{speed / 1024:.2f} KB/s"
                            
                            # Format ETA
                            if speed > 0:
                                remaining = (total_size - downloaded) / speed
                                if remaining > 60:
                                    eta = f"{remaining / 60:.1f} min"
                                else:
                                    eta = f"{remaining:.0f} sec"
                            else:
                                eta = "calculating..."
                            
                            # Print progress
                            print(f"\r[{bar}] {percent}% | {self.format_size(downloaded)} / {self.format_size(total_size)} | {speed_str} | ETA: {eta}", end='')
                            
                            if progress_callback:
                                progress_callback(percent, downloaded, total_size)
            
            print()  # New line after progress bar
            print("✅ Download complete!")
            
            # Verify the file
            if self.model_file.exists():
                size = self.model_file.stat().st_size
                print(f"📊 File size: {self.format_size(size)}")
                
                if size > 100_000_000:
                    print("✅ File appears to be valid.")
                    self.save_model_info()
                    return True
                else:
                    print("❌ File seems corrupt. Please try again.")
                    return False
            else:
                print("❌ File not found after download.")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Download error: {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return False
    
    def save_model_info(self):
        """Save model information"""
        info = {
            "model_name": self.model_name,
            "model_file": str(self.model_file),
            "file_size": self.model_file.stat().st_size,
            "download_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source_url": self.model_url
        }
        
        with open(self.model_info_file, 'w') as f:
            json.dump(info, f, indent=2)
        
        print(f"✅ Model info saved to: {self.model_info_file}")
    
    def load_model_info(self):
        """Load model information"""
        if self.model_info_file.exists():
            with open(self.model_info_file, 'r') as f:
                return json.load(f)
        return None
    
    def test_model(self):
        """Test if the model works"""
        print()
        print("🧪 Testing model...")
        
        try:
            # Try to load with llama-cpp-python if available
            try:
                from llama_cpp import Llama
                import multiprocessing
                
                n_threads = max(1, multiprocessing.cpu_count() - 1)
                
                print(f"🔄 Loading model with {n_threads} threads...")
                
                llm = Llama(
                    model_path=str(self.model_file),
                    n_ctx=512,  # Small context for testing
                    n_threads=n_threads,
                    n_gpu_layers=0,
                    verbose=False,
                    use_mmap=True
                )
                
                # Test with a simple prompt
                test_prompt = "What is 2+2?"
                response = llm(test_prompt, max_tokens=10, echo=False)
                result = response['choices'][0]['text'].strip()
                
                print(f"✅ Model loaded successfully!")
                print(f"🧪 Test response: {result}")
                return True
                
            except ImportError:
                print("⚠️ llama-cpp-python not installed. Model downloaded but not tested.")
                print("   To test, install: pip install llama-cpp-python")
                return True
            except Exception as e:
                print(f"⚠️ Model test failed: {e}")
                return False
                
        except Exception as e:
            print(f"⚠️ Test error: {e}")
            return False
    
    def run(self):
        """Main execution"""
        self.print_header()
        
        # Check if model already exists
        if self.check_existing_model():
            info = self.load_model_info()
            if info:
                print(f"📋 Download date: {info.get('download_date', 'Unknown')}")
            
            # Ask if user wants to re-download
            print()
            reply = input("Do you want to re-download? (y/N): ").strip().lower()
            if reply != 'y':
                print("✅ Using existing model.")
                self.test_model()
                return
        
        # Download the model
        print()
        print("📥 Starting download...")
        print("⏱️ This may take 5-15 minutes depending on your internet speed.")
        print()
        
        success = self.download_model()
        
        if success:
            print()
            print("=" * 60)
            print("🎉 Model downloaded successfully!")
            print("=" * 60)
            print(f"📁 Location: {self.model_file}")
            print(f"📊 Size: {self.format_size(self.model_file.stat().st_size)}")
            print("✅ Ready to use with Data Engineering Studio")
            print()
            print("📋 Next steps:")
            print("1. The model is now available in the ai_model/models/ folder")
            print("2. Open Data Engineering Studio")
            print("3. Create a Chat project")
            print("4. Click 'Enable AI' and start chatting with your data")
            print()
            
            # Test the model
            self.test_model()
            
        else:
            print()
            print("❌ Download failed.")
            print("Please check your internet connection and try again.")
            print()
            print("Alternative download methods:")
            print("1. Manual download from Hugging Face:")
            print(f"   {self.model_url}")
            print("2. Save the file to:")
            print(f"   {self.model_file}")
            print("3. Run this script again to verify the download")


def main():
    """Main entry point"""
    downloader = QwenModelDownloader()
    downloader.run()


if __name__ == "__main__":
    main()