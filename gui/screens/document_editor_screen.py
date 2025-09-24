# gui/screens/document_editor_screen.py
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QStatusBar, QMessageBox, QFileDialog, QDialog, QLineEdit,
    QFormLayout, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QKeySequence, QShortcut

# Import the text editor component
from gui.components.text_editor_widget import TextEditorWidget
from gui.components.text_editor_settings import EditorSettingsDialog

class DocumentEditorScreen(QWidget):
    """
    Document editor screen for Assistivox
    
    This screen provides a full-featured text editor with file operations
    and accessibility features.
    """
    # Navigation signal
    navigateBack = Signal()  # Signal to navigate back to previous screen
    
    def __init__(self, main_window, initial_text=""):
        super().__init__()
        self.main_window = main_window
        
        # Set up layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Add header
        header_layout = QHBoxLayout()
        
        # Back button - fixed width based on content
        back_btn = QPushButton("← Back")
        back_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        back_btn.clicked.connect(self.on_back_pressed)
        header_layout.addWidget(back_btn)
        
        # Title - should expand to fill space
        title = QLabel("Document Editor")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header_layout.addWidget(title)

        # Create updates button
        self.updates_button = QPushButton("Updates")
        self.updates_button.setToolTip("View Latest Updates (Ctrl+Alt+U)")
        self.updates_button.setFixedSize(80, 32)
        self.updates_button.clicked.connect(self.open_updates_page)
        self.updates_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        header_layout.addWidget(self.updates_button)

        # Create settings button
        self.settings_button = QPushButton("Settings")
        self.settings_button.setToolTip("Editor Settings (Ctrl+Alt+S)")
        self.settings_button.setFixedSize(80, 32)
        self.settings_button.clicked.connect(self.show_settings_dialog)
        self.settings_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        header_layout.addWidget(self.settings_button)

        layout.addLayout(header_layout)
        
        # Add the text editor component
        self.text_editor = TextEditorWidget(
            self, 
            initial_text=initial_text,
            config=main_window.config,
            assistivox_dir=main_window.assistivox_dir
        )
        layout.addWidget(self.text_editor)
        
        # Add status bar
        self.status_bar = QStatusBar()
        self.status_bar.setSizeGripEnabled(False)
        
        # Add zoom label to status bar
        self.zoom_label = QLabel("Zoom: 100%")
        self.status_bar.addPermanentWidget(self.zoom_label)
        
        self.update_status_bar()
        layout.addWidget(self.status_bar)
        
        # Connect signals
        self.text_editor.textSaved.connect(self.on_text_saved)
        self.text_editor.dictationToggled.connect(self.on_dictation_toggled)
        self.text_editor.zoomChanged.connect(self.on_zoom_changed)
        
        # Add keyboard shortcuts
        self.add_shortcuts()
    
    def add_shortcuts(self):
        """Add keyboard shortcuts for the document editor"""
        # Escape to go back
        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.esc_shortcut.activated.connect(self.on_back_pressed)
        
        # Ctrl+S to save
        self.save_shortcut = QShortcut(QKeySequence.Save, self)
        self.save_shortcut.activated.connect(self.text_editor.save_document)
        
        # Ctrl+Alt+S for settings
        self.settings_shortcut = QShortcut(QKeySequence("Ctrl+Alt+S"), self)
        self.settings_shortcut.activated.connect(self.show_settings_dialog)

        # Ctrl+Alt+U for updates
        self.updates_shortcut = QShortcut(QKeySequence("Ctrl+Alt+U"), self)
        self.updates_shortcut.activated.connect(self.open_updates_page)
    
    def show_settings_dialog(self):
        """Show editor settings dialog"""
        if hasattr(self.text_editor, 'editor_settings'):
            dialog = EditorSettingsDialog(self.text_editor.editor_settings, self)
            dialog.settingsChanged.connect(self.text_editor.save_editor_settings)
            dialog.exec()
    
    def update_status_bar(self, message=None):
        """Update the status bar with information or a custom message"""
        if message:
            self.status_bar.showMessage(message, 5000)  # Show for 5 seconds
        else:
            # Default status info
            status_text = "Ready"
            
            # Add dictation status if available
            if hasattr(self.text_editor, 'dictation_manager') and self.text_editor.dictation_manager:
                if hasattr(self.text_editor.dictation_manager, 'dictation') and self.text_editor.dictation_manager.dictation:
                    if self.text_editor.dictation_manager.dictation.is_running:
                        status_text = "🎤 Dictation active"
            
            self.status_bar.showMessage(status_text)
            
            # Update zoom level display
            if hasattr(self.text_editor, 'zoom_level'):
                self.zoom_label.setText(f"Zoom: {self.text_editor.zoom_level}%")

    def open_updates_page(self):
        """Open the updates page on the website"""
        import webbrowser
        updates_url = "https://assistivox.ai/updates/"
        try:
            webbrowser.open(updates_url)
        except Exception as e:
            # Fallback - show message box with URL
            QMessageBox.information(
                self,
                "Updates",
                f"Please visit: {updates_url}\n\nCurrent Version: 0.1.0"
            )
    
    def on_text_saved(self, text, filepath):
        """Handle saved text"""
        filename = filepath.split('/')[-1] if '/' in filepath else filepath.split('\\')[-1]
        self.update_status_bar(f"Document saved as {filename}")
    
    def on_dictation_toggled(self, is_active):
        """Handle dictation toggle"""
        if is_active:
            self.update_status_bar("🎤 Dictation started")
        else:
            self.update_status_bar("Dictation stopped")
    
    def on_zoom_changed(self, zoom_level):
        """Handle zoom level changes"""
        self.zoom_label.setText(f"Zoom: {zoom_level}%")
        # No need to update the entire status bar, just the zoom label
   
    def on_back_pressed(self):
        """Handle back button press"""
        # Check if document is modified
        if self.text_editor.is_document_modified():
            response = QMessageBox.question(
                self,
                "Unsaved Changes",
                "The document has unsaved changes. Do you want to save before leaving?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )
        
            if response == QMessageBox.Save:
                # Save the document using file manager
                if not self.save_document():
                    # If save was cancelled, don't navigate back
                    return
            elif response == QMessageBox.Cancel:
                # Cancel the back action
                return
    
        # Clean up audio resources
        self.text_editor.cleanup_audio_resources()
    
        # Navigate back
        self.navigateBack.emit()

    def save_document(self):
        """Save the document using file manager"""
        if self.text_editor.file_manager.get_current_file_path():
            return self.text_editor.file_manager.save_document()
        else:
            # Use the custom dialog for new documents
            return self.text_editor.file_manager.save_document_with_dialog()

