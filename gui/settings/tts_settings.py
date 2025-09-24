# gui/settings/tts_settings.py - Text-to-speech settings screen
import os
import sys
import json
import requests
import subprocess
from pathlib import Path
from urllib.request import urlretrieve

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QHBoxLayout, QMessageBox, QDialog, QProgressBar, QComboBox, QGroupBox,
    QFormLayout, QCheckBox, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal

# Build MODEL_MAP from tts.json
def load_model_map():
    """Load MODEL_MAP from tts.json"""
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tts_json_path = os.path.join(current_dir, "tts.json")
    
    model_map = {}
    try:
        with open(tts_json_path, 'r') as f:
            tts_data = json.load(f)
        
        # Extract piper voices
        piper_voices = tts_data.get("piper_tts_voices", {}).get("voices", {})
        if piper_voices:
            model_map["piper"] = piper_voices
            
        return model_map
    except Exception as e:
        print(f"Error loading tts.json: {e}")
        return {}

MODEL_MAP = load_model_map()

def list_installed_tts_models(base_path):
    """List installed TTS models"""
    tts_models_path = os.path.join(base_path, "tts-models")
    model_groups = {}
    
    print(f"DEBUG: Looking for models in: {tts_models_path}")
    
    if not os.path.exists(tts_models_path):
        print(f"DEBUG: Directory {tts_models_path} does not exist")
        return model_groups
    
    try:
        tts_contents = os.listdir(tts_models_path)
        print(f"DEBUG: Contents of tts-models: {tts_contents}")
    except Exception as e:
        print(f"DEBUG: Error listing tts-models directory: {e}")
        return model_groups
    
    for engine in tts_contents:
        engine_path = os.path.join(tts_models_path, engine)
        print(f"DEBUG: Checking engine path: {engine_path}")
        
        if not os.path.isdir(engine_path):
            print(f"DEBUG: {engine} is not a directory")
            continue
            
        try:
            engine_contents = os.listdir(engine_path)
            print(f"DEBUG: Contents of {engine}: {engine_contents}")
        except Exception as e:
            print(f"DEBUG: Error listing {engine} directory: {e}")
            continue
            
        models = set()
        
        for model_dir in engine_contents:
            model_dir_path = os.path.join(engine_path, model_dir)
            print(f"DEBUG: Checking model path: {model_dir_path}")
            
            if not os.path.isdir(model_dir_path):
                print(f"DEBUG: {model_dir} is not a directory")
                continue

            print(f"DEBUG: Adding model: {model_dir}")
            models.add(model_dir)

        print(f"DEBUG: Final models for {engine}: {sorted(models)}")
        model_groups[engine] = sorted(models)
        
    print(f"DEBUG: Final result: {model_groups}")
    return model_groups

def download_piper_voice(voice_name, assistivox_dir):
    """Download a Piper voice based on tts.json data"""
    if "piper" not in MODEL_MAP or voice_name not in MODEL_MAP["piper"]:
        raise ValueError(f"Voice '{voice_name}' not found in available Piper voices")
    
    voice_data = MODEL_MAP["piper"][voice_name]
    files = voice_data.get("files", [])
    
    if not files:
        raise ValueError(f"No files specified for voice '{voice_name}'")

    # Create voice directory (save to tts_models/engine/voice_name/)
    voice_dir = os.path.join(assistivox_dir, "tts-models", "piper", voice_name)
    os.makedirs(voice_dir, exist_ok=True)
    
    # Download each file
    for url in files:
        filename = url.split("/")[-1]
        dest_path = os.path.join(voice_dir, filename)
        
        if not os.path.exists(dest_path):
            print(f"Downloading {filename}...")
            urlretrieve(url, dest_path)
            print(f"{filename} downloaded")
        else:
            print(f"{filename} already exists")
    
    return voice_dir


class ModelInstallThread(QThread):
    """Thread for installing models without blocking the GUI"""
    progress_update = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, engine, model, version, assistivox_dir):
        super().__init__()
        self.engine = engine
        self.model = model
        self.version = version
        self.assistivox_dir = assistivox_dir

    def run(self):
        try:
            self.progress_update.emit(f"Starting download of {self.model} voice...")
            
            if self.engine == "piper":
                # Use our direct download method
                voice_dir = download_piper_voice(self.model, str(self.assistivox_dir))
                self.finished.emit(True, f"Successfully installed {self.engine} voice {self.model} to {voice_dir}")
            else:
                self.finished.emit(False, f"Unsupported engine: {self.engine}")
                
        except Exception as e:
            self.finished.emit(False, f"Error downloading voice: {str(e)}")

class ModelUninstallThread(QThread):
    """Thread for uninstalling models without blocking the GUI"""
    progress_update = Signal(str)
    finished = Signal(bool, str)
    
    def __init__(self, engine, model, version, assistivox_dir):
        super().__init__()
        self.engine = engine
        self.model = model
        self.version = version
        self.assistivox_dir = assistivox_dir
        
    def run(self):
        try:
            # Call uninstall_tts.py using subprocess
            cmd = [
                sys.executable,
                "uninstall_tts.py",
                self.engine,
                self.model,
                self.version,
                "--path",
                str(self.assistivox_dir)
            ]
            
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Monitor the process output
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    self.progress_update.emit(output.strip())
            
            # Get return code and errors
            return_code = process.poll()
            errors = process.stderr.read()
            
            if return_code == 0:
                self.finished.emit(True, f"Successfully uninstalled {self.engine} model {self.model}")
            else:
                self.finished.emit(False, f"Failed to uninstall model: {errors}")
        
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")


class ProgressDialog(QDialog):
    """Dialog showing progress of model installation/uninstallation"""
    
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        
        # Set up layout
        layout = QVBoxLayout(self)
        
        # Progress information
        self.status_label = QLabel("Starting operation...")
        layout.addWidget(self.status_label)
        
        # Progress bar (indeterminate)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        layout.addWidget(self.progress_bar)
        
        # Close button (initially disabled)
        self.close_button = QPushButton("Close")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button)
    
    def update_status(self, message):
        """Update the status message"""
        self.status_label.setText(message)
    
    def operation_complete(self, success, message):
        """Called when the operation completes"""
        if success:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
        
        self.status_label.setText(message)
        self.close_button.setEnabled(True)


class DownloadModelDialog(QDialog):
    """Dialog for selecting and downloading TTS models"""
    
    def __init__(self, assistivox_dir, parent=None):
        super().__init__(parent)
        self.assistivox_dir = assistivox_dir
        
        self.setWindowTitle("Download Text-to-Speech Model")
        self.setMinimumWidth(450)
        
        # Set up layout
        layout = QVBoxLayout(self)
        
        # Engine selection
        engine_group = QGroupBox("Engine")
        engine_layout = QVBoxLayout()
        
        self.engine_combo = QComboBox()
        for engine in MODEL_MAP.keys():
            self.engine_combo.addItem(engine.replace("-", " ").title(), engine)
        
        self.engine_combo.currentIndexChanged.connect(self.update_model_combo)
        engine_layout.addWidget(self.engine_combo)
        engine_group.setLayout(engine_layout)
        layout.addWidget(engine_group)
        
        # Model selection
        model_group = QGroupBox("Model")
        model_layout = QVBoxLayout()
        
        self.model_combo = QComboBox()
        model_layout.addWidget(self.model_combo)
        model_group.setLayout(model_layout)
        layout.addWidget(model_group)
        
        # Version selection
        version_group = QGroupBox("Version")
        version_layout = QVBoxLayout()
        
        self.version_combo = QComboBox()
        version_layout.addWidget(self.version_combo)
        version_group.setLayout(version_layout)
        layout.addWidget(version_group)
        
        # Update model combo initially
        self.update_model_combo()
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.accept)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(self.download_button)
        
        layout.addLayout(button_layout)
    
    def update_model_combo(self):
        """Update the model combo box based on selected engine"""
        self.model_combo.clear()
        
        # Get the current engine
        engine = self.engine_combo.currentData()
        
        if engine in MODEL_MAP:
            # Add all available models for this engine
            for model in sorted(MODEL_MAP[engine].keys()):
                self.model_combo.addItem(model, model)
            
            # Connect model change to version update
            self.model_combo.currentIndexChanged.connect(self.update_version_combo)
            
            # Update versions
            self.update_version_combo()
    
    def update_version_combo(self):
        """Update the version combo box based on selected model"""
        self.version_combo.clear()
        
        # Get the current engine and model
        engine = self.engine_combo.currentData()
        model = self.model_combo.currentData()
        
        if engine in MODEL_MAP and model in MODEL_MAP[engine]:
            # Check if this model has versions
            model_info = MODEL_MAP[engine][model]
            
            # Models in MODEL_MAP have a "versions" key with a list of version objects
            if "versions" in model_info:
                versions = model_info["versions"]
                for version_info in versions:
                    version = version_info["version"]
                    self.version_combo.addItem(version, version)
            else:
                # No versions, use a default
                self.version_combo.addItem("default", "default")

    def get_selected_model(self):
        """Get the selected engine, model, and version"""
        engine = self.engine_combo.currentData()
        model = self.model_combo.currentData()
        version = self.version_combo.currentData()
        return engine, model, version
    
class SelectModelDialog(QDialog):
    """Dialog to select an installed model"""
    
    def __init__(self, assistivox_dir, parent=None):
        super().__init__(parent)
        self.assistivox_dir = assistivox_dir
        
        self.setWindowTitle("Select Text-to-Speech Model")
        self.setMinimumWidth(300)
        
        layout = QVBoxLayout(self)
        
        label = QLabel("Select a model to use:")
        layout.addWidget(label)
        
        self.model_list = QListWidget()
        # Connect double-click signal to accept the dialog
        self.model_list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.model_list)
        
        # Add installed models to the list
        installed_models = list_installed_tts_models(str(self.assistivox_dir))
        for engine, models in installed_models.items():
            for model in models:
                display_name = f"{engine.title()} - {model}"
                item = QListWidgetItem(display_name)
                item.setData(Qt.UserRole, (engine, model))
                self.model_list.addItem(item)
        
        buttons = QHBoxLayout()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        select_button = QPushButton("Select")
        select_button.clicked.connect(self.accept)
        
        buttons.addWidget(cancel_button)
        buttons.addWidget(select_button)
        
        layout.addLayout(buttons)
        
    def keyPressEvent(self, event):
        """Handle key press events for the dialog"""
        # Accept dialog when Enter/Return is pressed with an item selected
        if event.key() in (Qt.Key_Enter, Qt.Key_Return):
            if self.model_list.currentItem():
                self.accept()
            return
        # Call the parent class implementation for other keys
        super().keyPressEvent(event)

    def get_selected_model(self):
        """Get the selected model engine and name"""
        selected_item = self.model_list.currentItem()
        if selected_item:
            return selected_item.data(Qt.UserRole)
        return None, None
    
class TTSSettingsScreen(QWidget):
    """Text-to-speech settings screen for model management"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
        # Set up layout
        layout = QVBoxLayout(self)
        
        # Add title
        title = QLabel("Text to Speech Settings")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(20)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        
        # Current model section
        current_model_group = QGroupBox("Current Model")
        current_model_layout = QVBoxLayout()
        
        self.current_model_label = QLabel("No model selected")
        current_model_layout.addWidget(self.current_model_label)
        
        current_model_buttons = QHBoxLayout()
        
        self.select_model_button = QPushButton("Change Model")
        self.select_model_button.clicked.connect(self.show_select_model_dialog)
        
        self.uninstall_model_button = QPushButton("Uninstall Model")
        self.uninstall_model_button.clicked.connect(self.uninstall_current_model)
        
        current_model_buttons.addWidget(self.select_model_button)
        current_model_buttons.addWidget(self.uninstall_model_button)
        
        current_model_layout.addLayout(current_model_buttons)
        current_model_group.setLayout(current_model_layout)
        layout.addWidget(current_model_group)
        
        # Download section
        download_button = QPushButton("Download New Model")
        download_button.clicked.connect(self.show_download_dialog)
        layout.addWidget(download_button)
        
        # Add spacer - this will expand to fill available space
        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))
        
        # Add back button
        back_btn = QPushButton("Back to Settings")
        back_btn.setMinimumHeight(50)
        back_btn.clicked.connect(lambda: self.main_window.navigate_to(1))  # Navigate to settings menu
        layout.addWidget(back_btn)
        
        # Update the UI with current data
        self.update_ui()
    
    def update_ui(self):
        """Update the UI with current model information"""
        # Update current model display
        selected_model = self.get_selected_model()
        if selected_model:
            engine, model = selected_model
            self.current_model_label.setText(f"{engine.title()} - {model}")
            self.uninstall_model_button.setEnabled(True)
        else:
            self.current_model_label.setText("No model selected")
            self.uninstall_model_button.setEnabled(False)
    
    def show_select_model_dialog(self):
        """Show dialog to select an installed model"""
        # Get installed models
        installed_models = list_installed_tts_models(str(self.main_window.assistivox_dir))
        
        # Check if there are any installed models
        if not installed_models:
            QMessageBox.information(
                self,
                "No Models Installed",
                "There are no models installed. Please download a model first."
            )
            return
        
        # Create a dialog for model selection
        dialog = SelectModelDialog(
            self.main_window.assistivox_dir,
            self
        )
        
        # Show the dialog
        if dialog.exec() == QDialog.Accepted:
            # Get selected model
            engine, model = dialog.get_selected_model()
            if engine and model:
                self.set_selected_model(engine, model)
    
    def show_download_dialog(self):
        """Show dialog to download a new model"""
        dialog = DownloadModelDialog(self.main_window.assistivox_dir, self)
        
        if dialog.exec() == QDialog.Accepted:
            engine, model, version = dialog.get_selected_model()
            self.download_model(engine, model, version)
    
    def download_model(self, engine, model, version):
        """Download the selected model"""
        # Create progress dialog
        progress_dialog = ProgressDialog("Downloading Model", self)
        
        # Create and configure thread
        self.install_thread = ModelInstallThread(
            engine,
            model,
            version,
            self.main_window.assistivox_dir
        )
        
        # Connect signals
        self.install_thread.progress_update.connect(progress_dialog.update_status)
        self.install_thread.finished.connect(progress_dialog.operation_complete)
        self.install_thread.finished.connect(self.on_model_installed)
        
        # Start thread
        self.install_thread.start()
        
        # Show dialog
        progress_dialog.exec()
    
    def uninstall_current_model(self):
        """Uninstall the currently selected model"""
        selected_model = self.get_selected_model()
        if not selected_model:
            QMessageBox.information(
                self,
                "No Model Selected",
                "There is no model currently selected."
            )
            return
    
        engine, model = selected_model
    
        # Get installed models
        installed_models = list_installed_tts_models(str(self.main_window.assistivox_dir))
    
        # Default version
        version = "default"
    
        # Look for version in model dir name
        # Fix: Check if the engine exists in installed_models first, and handle the list correctly
        if engine in installed_models and model in installed_models[engine]:
            # Check the model directories to extract version
            tts_models_path = os.path.join(str(self.main_window.assistivox_dir), "tts-models", engine)
            if os.path.exists(tts_models_path):
                for model_dir in os.listdir(tts_models_path):
                    if model_dir.startswith(model + "-"):
                        if "-" in model_dir:
                            version = model_dir.split("-")[1]
                            break
    
        # Confirm uninstallation
        result = QMessageBox.question(
            self,
            "Uninstall Model",
            f"Are you sure you want to uninstall {engine.title()} - {model}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
    
        if result == QMessageBox.Yes:
            # Create progress dialog
            progress_dialog = ProgressDialog("Uninstalling Model", self)
        
            # Create and configure thread
            self.uninstall_thread = ModelUninstallThread(
                engine,
                model,
                version,
                self.main_window.assistivox_dir
            )
        
            # Connect signals
            self.uninstall_thread.progress_update.connect(progress_dialog.update_status)
            self.uninstall_thread.finished.connect(progress_dialog.operation_complete)
            self.uninstall_thread.finished.connect(self.on_model_uninstalled)
        
            # Start thread
            self.uninstall_thread.start()
        
            # Show dialog
            progress_dialog.exec()
    
    def get_selected_model(self):
        """Get the currently selected model from config"""
        if "tts_models" not in self.main_window.config:
            return None
    
        if "selected" not in self.main_window.config["tts_models"]:
            return None
    
        selected = self.main_window.config["tts_models"]["selected"]
    
        # Parse the selected model string (format: "piper-amy")
        try:
            engine, model = selected.split("-", 1)
        
            # Get installed models
            installed_models = list_installed_tts_models(str(self.main_window.assistivox_dir))
        
            # If no models are installed, return None
            if not installed_models:
                return None
        
            # Check if the selected model is installed
            if engine in installed_models and model in installed_models[engine]:
                return (engine, model)
        
            # If we get here, the selected model is not installed
            return None
        except ValueError:
            # Invalid format
            return None

    def on_model_installed(self, success, message):
        """Called when model installation completes"""
        if success:
            # Get the model type and size from the thread
            engine = self.install_thread.engine
            model = self.install_thread.model
       
           # Update the UI
            self.update_ui()
        
            # If no model is currently selected, set this one as selected
            if not self.get_selected_model():
                self.set_selected_model(engine, model)

    def on_model_uninstalled(self, success, message):
        """Called when model uninstallation completes"""
        if success:
            # Remove the selected model from config if it was the one uninstalled
            selected_model = self.get_selected_model()
            if selected_model:
                engine, model = selected_model
            
                # If the uninstalled model is the selected one, clear selection
                if (engine == self.uninstall_thread.engine and 
                    model == self.uninstall_thread.model):
                    if "tts_models" in self.main_window.config and "selected" in self.main_window.config["tts_models"]:
                        del self.main_window.config["tts_models"]["selected"]
                        self.main_window.save_config()
        
            # Update the UI
            self.update_ui()

    def set_selected_model(self, engine, model):
        """Set the selected model in the config"""
        # Ensure tts_models section exists in config
        if "tts_models" not in self.main_window.config:
            self.main_window.config["tts_models"] = {}

        # Set the selected model in the new format
        self.main_window.config["tts_models"]["selected"] = f"{engine}-{model}"

        # Save the config
        self.main_window.save_config()

        # Update UI
        self.update_ui()
