# gui/settings/piper_bulk_download_dialog.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QProgressBar, QTextEdit
)
from PySide6.QtCore import Qt, QThread, Signal
import os
import sys
import json
import requests
import tempfile

# Import existing components
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load model information  
def load_model_map():
    """Load MODEL_MAP from tts.json"""
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tts_json_path = os.path.join(current_dir, "tts.json")
    
    try:
        with open(tts_json_path, 'r') as f:
            tts_data = json.load(f)
        return tts_data.get("piper_tts_voices", {}).get("voices", {})
    except Exception as e:
        print(f"Error loading tts.json: {e}")
        return {}

class BulkDownloadThread(QThread):
    """Thread for downloading multiple Piper voices"""
    progress_update = Signal(int, str)  # progress_value, status_message
    finished = Signal(bool, str)
    
    def __init__(self, voice_list, assistivox_dir):
        super().__init__()
        self.voice_list = voice_list
        self.assistivox_dir = assistivox_dir
        self.piper_voices = load_model_map()
        
    def run(self):
        total_voices = len(self.voice_list)
        successful_downloads = 0
        
        for i, voice_name in enumerate(self.voice_list):
            if self.isInterruptionRequested():
                self.finished.emit(False, "Download cancelled by user")
                return
                
            self.progress_update.emit(i, f"downloading {voice_name}")
            
            # Download this voice
            success = self.download_single_voice(voice_name)
            if success:
                successful_downloads += 1
                
            # Update progress
            progress_value = i + 1
            self.progress_update.emit(progress_value, f"downloading {voice_name}")
        
        # Emit completion
        if successful_downloads == total_voices:
            self.finished.emit(True, f"Successfully downloaded all {total_voices} voices")
        elif successful_downloads > 0:
            self.finished.emit(True, f"Downloaded {successful_downloads}/{total_voices} voices")
        else:
            self.finished.emit(False, "Failed to download any voices")
    
    def download_single_voice(self, voice_name):
        """Download a single voice using the same method as TTSDownloadDialog"""
        try:
            voice_info = self.piper_voices.get(voice_name, {})
            if not voice_info:
                print(f"No info found for voice: {voice_name}")
                return False
                
            # Get files to download
            files = voice_info.get("files", [])
            if not files:
                print(f"No files found for voice: {voice_name}")
                return False
            
            # Create target directory
            display_name = voice_info.get("display_name", voice_name)
            quality = voice_info.get("quality", "medium")
            model_dir = os.path.join(
                str(self.assistivox_dir), 
                "tts-models", 
                "piper", 
                voice_name
            )
            os.makedirs(model_dir, exist_ok=True)
            
            # Download each file
            for file_url in files:
                filename = os.path.basename(file_url)
                target_path = os.path.join(model_dir, filename)
                
                response = requests.get(file_url, stream=True, timeout=30)
                response.raise_for_status()
                
                with open(target_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            
            return True
            
        except Exception as e:
            print(f"Error downloading {voice_name}: {e}")
            return False

class PiperBulkDownloadDialog(QDialog):
    """Dialog for downloading multiple Piper voices with progress tracking"""
    
    def __init__(self, assistivox_dir, voice_list, parent=None):
        super().__init__(parent)
        self.assistivox_dir = assistivox_dir
        self.voice_list = voice_list
        
        self.setWindowTitle("Download Piper Voice Pack")
        self.setMinimumWidth(500)
        self.setMinimumHeight(200)
        self.setModal(True)
        
        # Set up layout
        layout = QVBoxLayout(self)
        
        # Info label
        info_label = QLabel(f"Downloading {len(voice_list)} Piper voices...")
        layout.addWidget(info_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, len(voice_list))
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Status message
        self.status_label = QLabel("Preparing download...")
        layout.addWidget(self.status_label)
        
        # Button layout (initially just cancel)
        self.button_layout = QHBoxLayout()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_download)
        self.button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(self.button_layout)
        
        # Start download automatically
        self.start_download()
        
    def start_download(self):
        """Start the bulk download process"""
        self.download_thread = BulkDownloadThread(self.voice_list, self.assistivox_dir)
        self.download_thread.progress_update.connect(self.update_progress)
        self.download_thread.finished.connect(self.download_finished)
        self.download_thread.start()
        
    def update_progress(self, progress_value, status_message):
        """Update progress bar and status message"""
        self.progress_bar.setValue(progress_value)
        self.status_label.setText(status_message)
        
    def download_finished(self, success, message):
        """Handle download completion"""
        self.status_label.setText(message)
        
        # Hide cancel button, show close button
        self.cancel_button.setVisible(False)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        self.button_layout.addWidget(close_button)
        
        # Auto-close after 2 seconds if successful
        if success:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, self.accept)
        
    def cancel_download(self):
        """Cancel the download process"""
        if hasattr(self, 'download_thread'):
            self.download_thread.requestInterruption()
            self.download_thread.wait(3000)  # Wait up to 3 seconds
        self.reject()
