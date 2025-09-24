# gui/dictation/dictation_manager.py
import os
import sys
import threading
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

# Import dictation engine if available
try:
    from gui.dictation.dictation_engine import DictationEngine
    DICTATION_AVAILABLE = True
except ImportError:
    DictationEngine = None
    DICTATION_AVAILABLE = False

class DictationManager(QObject):
    """
    Dictation manager for handling speech-to-text in the application
    
    This class encapsulates all dictation-related functionality that was previously
    in the TextEditorWidget class.
    """
    
    # Signals
    dictationToggled = Signal(bool)  # Emitted when dictation is toggled
    textReceived = Signal(str)  # Emitted when text is received from dictation
    partialTextReceived = Signal(str)  # Gray text while speaking
    finalTextReceived = Signal(str)    # Black text when finished
    
    def __init__(self, text_edit=None, config=None, assistivox_dir=None):
        super().__init__()
        self.text_edit = text_edit
        self.config = config
        self.assistivox_dir = assistivox_dir
        self.dictation = None
        self.dictation_action = None
        
        # Initialize dictation engine if available and config is ready
        if text_edit is not None and config is not None and assistivox_dir is not None:
            self.init_dictation_engine()
   
    def init_dictation_engine(self):
        """Initialize the dictation engine if available"""
        if not DICTATION_AVAILABLE or not self.config or not self.assistivox_dir:
            return
        
        try:
            config_path = self.assistivox_dir / "config.json"
            self.dictation = DictationEngine(self.assistivox_dir, config_path)
        
            # Connect existing signals
            self.dictation.textReceived.connect(self.on_text_received)
            self.dictation.statusChanged.connect(self.on_dictation_status_changed)
        
            # Connect NEW signals for partial/final results
            self.dictation.partialTextReceived.connect(self.on_partial_text_received)
            self.dictation.finalTextReceived.connect(self.on_final_text_received)
        
        except Exception as e:
            print(f"Failed to initialize dictation: {e}")

    def register_dictation_action(self, action):
        """Register the toolbar action for dictation"""
        self.dictation_action = action
    
    def is_available(self):
        """Check if dictation is available"""
        return DICTATION_AVAILABLE and self.dictation is not None
    
    def is_running(self):
        """Check if dictation is currently running"""
        return self.dictation and self.dictation.is_running
    
    def toggle_dictation(self):
        """Toggle dictation on/off based on current state"""
        if not self.dictation:
            QMessageBox.information(self.text_edit, "Dictation Not Available",
                                   "Dictation is not available. Please check that speech-to-text models are installed.")
            return
    
        # Check the current dictation state - if running, turn it off. If not running, turn it on.
        if self.dictation.is_running:
            # Stop dictation
            self.dictation.stop_dictation()
        
            # Update toolbar button if it exists
            if self.dictation_action:
                self.dictation_action.blockSignals(True)
                self.dictation_action.setChecked(False)
                self.dictation_action.blockSignals(False)
        else:
            # Check if a model is selected - reload config to get the latest selection
            self.dictation.config = self.dictation._load_config()
        
            if not self.dictation.is_model_selected():
                QMessageBox.warning(self.text_edit, "No Model Selected",
                                   "No speech-to-text model is selected. Please select a model in the settings.")
            
                # Ensure toolbar button is unchecked
                if self.dictation_action:
                    self.dictation_action.blockSignals(True)
                    self.dictation_action.setChecked(False)
                    self.dictation_action.blockSignals(False)
                return
        
            # Try to start dictation
            if not self.dictation.start_dictation():
                QMessageBox.warning(self.text_edit, "Dictation Failed",
                                   "Failed to start dictation. Please check that the selected model is properly installed.")
            
                # Ensure toolbar button is unchecked
                if self.dictation_action:
                    self.dictation_action.blockSignals(True)
                    self.dictation_action.setChecked(False)
                    self.dictation_action.blockSignals(False)
                return
        
            # Update toolbar button if it exists
            if self.dictation_action:
                self.dictation_action.blockSignals(True)
                self.dictation_action.setChecked(True)
                self.dictation_action.blockSignals(False)
    
    def on_text_received(self, text):
        """Handle text received from dictation"""
        self.textReceived.emit(text)
    
    def on_dictation_status_changed(self, is_active, message):
        """Handle dictation status changes"""
        if self.dictation_action:
            # Update the button state without triggering the action
            self.dictation_action.blockSignals(True)
            self.dictation_action.setChecked(is_active)
            self.dictation_action.blockSignals(False)
        
        # Emit signal for other components to react
        self.dictationToggled.emit(is_active)
        
        # Show status message
        if not is_active and "Error" in message:
            QMessageBox.warning(self.text_edit, "Dictation Error", message)
    
    def cleanup_resources(self):
        """Clean up dictation resources when widget is being closed"""
        if self.dictation and self.dictation.is_running:
            self.dictation.stop_dictation()

    def on_partial_text_received(self, text):
        """Handle partial text - emit to UI components"""
        self.partialTextReceived.emit(text)

    def on_final_text_received(self, text):
        """Handle final text - emit to UI components"""  
        self.finalTextReceived.emit(text)
