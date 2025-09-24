# gui/settings/stt_settings.py - Speech-to-text settings screen
import os
import sys
import json
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QHBoxLayout, QMessageBox, QDialog, QProgressBar, QComboBox, QGroupBox,
    QFormLayout, QCheckBox, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal

# Import the model information and functions
# Use relative import for the package structure
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from install_stt import MODEL_MAP, list_installed_models
except ImportError:
    # If import fails, try to find the module in various ways
    import importlib.util
    
    # Get the current script's directory - adjust path to find module
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Look for install_stt.py in the main directory
    install_stt_path = os.path.join(current_dir, "install_stt.py")
    
    # If not found there, try some alternative names
    if not os.path.exists(install_stt_path):
        install_stt_path = os.path.join(current_dir, "install-stt.py")
    
    if not os.path.exists(install_stt_path):
        MODEL_MAP = {}
        list_installed_models = lambda x: {}
    else:
        # Load the module from the file path
        spec = importlib.util.spec_from_file_location("install_stt", install_stt_path)
        install_stt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(install_stt)
        
        # Now we can access the required functions and variables
        MODEL_MAP = install_stt.MODEL_MAP
        list_installed_models = install_stt.list_installed_models


class ModelInstallThread(QThread):
    """Thread for installing models without blocking the GUI"""
    progress_update = Signal(str)
    finished = Signal(bool, str)
    
    def __init__(self, model_type, model_size, assistivox_dir):
        super().__init__()
        self.model_type = model_type
        self.model_size = model_size
        self.assistivox_dir = assistivox_dir
        
    def run(self):
        try:
            # Call install_stt.py using subprocess
            cmd = [
                sys.executable,
                "install_stt.py",
                self.model_type,
                self.model_size,
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
                self.finished.emit(True, f"Successfully installed {self.model_type} {self.model_size}")
            else:
                self.finished.emit(False, f"Failed to install model: {errors}")
        
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")


class ModelUninstallThread(QThread):
    """Thread for uninstalling models without blocking the GUI"""
    progress_update = Signal(str)
    finished = Signal(bool, str)
    
    def __init__(self, model_type, model_size, assistivox_dir):
        super().__init__()
        self.model_type = model_type
        self.model_size = model_size
        self.assistivox_dir = assistivox_dir
        
    def run(self):
        try:
            # Call uninstall_stt.py using subprocess
            cmd = [
                sys.executable,
                "uninstall_stt.py",
                self.model_type,
                self.model_size,
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
                self.finished.emit(True, f"Successfully uninstalled {self.model_type} {self.model_size}")
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
    """Dialog for selecting and downloading STT models"""
    
    def __init__(self, assistivox_dir, parent=None):
        super().__init__(parent)
        self.assistivox_dir = assistivox_dir
        
        # Define which model types to hide from UI
        self.hidden_model_types = ["whisper", "insanely-fast-whisper"]
        
        self.setWindowTitle("Download Speech-to-Text Model")
        self.setMinimumWidth(450)
        
        # Set up layout
        layout = QVBoxLayout(self)
        
        # Model type selection
        type_group = QGroupBox("Model Type")
        type_layout = QVBoxLayout()
        
        self.type_combo = QComboBox()
        # Add all model types from MODEL_MAP (excluding hidden types)
        for model_type in MODEL_MAP.keys():
            if model_type not in self.hidden_model_types:
                self.type_combo.addItem(model_type.replace("-", " ").title(), model_type)
        
        self.type_combo.currentIndexChanged.connect(self.update_size_combo)
        type_layout.addWidget(self.type_combo)
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)
        
        # Model size selection
        size_group = QGroupBox("Model Size")
        size_layout = QVBoxLayout()
        
        self.size_combo = QComboBox()
        size_layout.addWidget(self.size_combo)
        size_group.setLayout(size_layout)
        layout.addWidget(size_group)
        
        # Update size combo initially
        self.update_size_combo()
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.accept)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(self.download_button)
        
        layout.addLayout(button_layout)
    
    def update_size_combo(self):
        """Update the size combo box based on selected model type"""
        self.size_combo.clear()
        
        # Get the current model type
        model_type = self.type_combo.currentData()
        
        if model_type in MODEL_MAP:
            # Add all available model sizes for this type
            for model_size in MODEL_MAP[model_type]:
                self.size_combo.addItem(model_size, model_size)
    
    def get_selected_model(self):
        """Get the selected model type and size"""
        model_type = self.type_combo.currentData()
        model_size = self.size_combo.currentText()
        
        return model_type, model_size


class SelectModelDialog(QDialog):
    """Dialog to select an installed model"""
    
    def __init__(self, assistivox_dir, hidden_model_types, parent=None):
        super().__init__(parent)
        self.assistivox_dir = assistivox_dir
        self.hidden_model_types = hidden_model_types
        
        self.setWindowTitle("Select Model")
        self.setMinimumWidth(300)
        
        layout = QVBoxLayout(self)
        
        label = QLabel("Select a model to use:")
        layout.addWidget(label)
        
        self.model_list = QListWidget()
        # Connect double-click signal to accept the dialog
        self.model_list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.model_list)
        
        # Add installed models to the list
        installed_models = list_installed_models(str(self.assistivox_dir))
        for model_type, sizes in installed_models.items():
            if model_type not in self.hidden_model_types:  # Skip hidden types
                for size in sizes:
                    display_name = f"{model_type.replace('-', ' ').title()} {size}"
                    item = QListWidgetItem(display_name)
                    item.setData(Qt.UserRole, (model_type, size))
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
        """Get the selected model type and size"""
        selected_item = self.model_list.currentItem()
        if selected_item:
            return selected_item.data(Qt.UserRole)
        return None, None


class STTSettingsScreen(QWidget):
    """Speech-to-text settings screen for model management"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
        # Define which model types to hide from UI
        self.hidden_model_types = ["whisper", "insanely-fast-whisper"]
        
        # Set up layout
        layout = QVBoxLayout(self)
        
        # Add title
        title = QLabel("Speech to Text Settings")
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
            model_type, model_size = selected_model.split("_")
            self.current_model_label.setText(f"{model_type.replace('-', ' ').title()} {model_size}")
            self.uninstall_model_button.setEnabled(True)
        else:
            self.current_model_label.setText("No model selected")
            self.uninstall_model_button.setEnabled(False)
    
    def get_selected_model(self):
        """Get the currently selected model from config"""
        if "stt_models" not in self.main_window.config:
            return None
        
        if "selected" not in self.main_window.config["stt_models"]:
            return None
        
        selected_model = self.main_window.config["stt_models"]["selected"]
        
        # Get installed models
        installed_models = list_installed_models(str(self.main_window.assistivox_dir))
        
        # If no models are installed, return None
        if not installed_models:
            return None
        
        # Parse the selected model name to get type and size
        try:
            model_type, model_size = selected_model.split("_")
        except ValueError:
            # Invalid format
            return None
        
        # Check if the selected model is installed
        if model_type in installed_models and model_size in installed_models[model_type]:
            return selected_model
        
        # If we get here, the selected model is not installed
        return None
    
    def set_selected_model(self, model_type, model_size):
        """Set the selected model in the config"""
        # Ensure stt_models section exists in config
        if "stt_models" not in self.main_window.config:
            self.main_window.config["stt_models"] = {}
        
        # Set the selected model
        self.main_window.config["stt_models"]["selected"] = f"{model_type}_{model_size}"
        
        # Save the config
        self.main_window.save_config()
        
        # Update UI
        self.update_ui()
    
    def show_select_model_dialog(self):
        """Show dialog to select an installed model"""
        # Get installed models
        installed_models = list_installed_models(str(self.main_window.assistivox_dir))
        
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
            self.hidden_model_types,
            self
        )
        
        # Show the dialog
        if dialog.exec() == QDialog.Accepted:
            # Get selected model
            model_type, model_size = dialog.get_selected_model()
            if model_type and model_size:
                self.set_selected_model(model_type, model_size)
    
    def show_download_dialog(self):
        """Show dialog to download a new model"""
        dialog = DownloadModelDialog(self.main_window.assistivox_dir, self)
        
        if dialog.exec() == QDialog.Accepted:
            model_type, model_size = dialog.get_selected_model()
            self.download_model(model_type, model_size)
    
    def download_model(self, model_type, model_size):
        """Download the selected model type and size"""
        # Create progress dialog
        progress_dialog = ProgressDialog("Downloading Model", self)
        
        # Create and configure thread
        self.install_thread = ModelInstallThread(
            model_type,
            model_size,
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
    
    def on_model_installed(self, success, message):
        """Called when model installation completes"""
        if success:
            # Get the model type and size from the thread
            model_type = self.install_thread.model_type
            model_size = self.install_thread.model_size
            
            # Update the UI
            self.update_ui()
            
            # If no model is currently selected, set this one as selected
            if not self.get_selected_model():
                self.set_selected_model(model_type, model_size)
    
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
        
        model_type, model_size = selected_model.split("_")
        
        # Confirm uninstallation
        result = QMessageBox.question(
            self,
            "Uninstall Model",
            f"Are you sure you want to uninstall {model_type.replace('-', ' ').title()} {model_size}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if result == QMessageBox.Yes:
            # Create progress dialog
            progress_dialog = ProgressDialog("Uninstalling Model", self)
            
            # Create and configure thread
            self.uninstall_thread = ModelUninstallThread(
                model_type,
                model_size,
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
    
    def on_model_uninstalled(self, success, message):
        """Called when model uninstallation completes"""
        if success:
            # Remove the selected model from config if it was the one uninstalled
            selected_model = self.get_selected_model()
            if selected_model:
                model_type, model_size = selected_model.split("_")
                
                # If the uninstalled model is the selected one, clear selection
                if (model_type == self.uninstall_thread.model_type and 
                    model_size == self.uninstall_thread.model_size):
                    if "stt_models" in self.main_window.config and "selected" in self.main_window.config["stt_models"]:
                        del self.main_window.config["stt_models"]["selected"]
                        self.main_window.save_config()
            
            # Update the UI
            self.update_ui()
