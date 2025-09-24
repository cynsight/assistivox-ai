# gui/main_window.py
import os
import sys
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStackedWidget, QPushButton, QLabel, QCheckBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence, QFont

# Import Kokoro manager for Docker lifecycle
try:
    from gui.tts.kokoro_manager import get_kokoro_docker_manager, cleanup_kokoro_docker
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    get_kokoro_docker_manager = None
    cleanup_kokoro_docker = None

class AssistivoxMainWindow(QMainWindow):
    """Main window class for the Assistivox application"""

    def __init__(self, dev_mode=False, splash=None, app=None):
        super().__init__()
    
        # Set up the main window
        self.setWindowTitle("Assistivox")
        self.setMinimumSize(800, 600)
    
        # Initialize path to config directory and file
        if dev_mode:
            # Use current directory for development
            self.assistivox_dir = Path.cwd() / ".assistivox"
        else:
            # Use home directory for normal operation
            self.assistivox_dir = Path.home() / ".assistivox"
        
        self.assistivox_dir.mkdir(exist_ok=True)
        self.config_path = self.assistivox_dir / "config.json"
   
        # Load or create config
        if splash and app:
            # Set larger font for splash messages to improve accessibility
            splash_font = QFont("Arial", 16, QFont.Normal)
            splash.setFont(splash_font)
            splash.showMessage("Loading configuration...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
            app.processEvents()

        self.load_config()

        # Set up the central widget with a stacked layout to manage "pages"
        if splash and app:
            splash.showMessage("Setting up interface...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
            app.processEvents()
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Create a stacked widget to manage different "screens"
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)

        # Create and add screens
        if splash and app:
            splash.showMessage("Creating application screens...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
            app.processEvents()
        self.init_screens()

        # Apply theme and font settings based on config
        if splash and app:
            splash.showMessage("Applying theme...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
            app.processEvents()
        self.apply_theme()

        # Skip main menu and go directly to text editor
        self.navigate_to(5)

        # Ensure text editor gets focus when window loads
        from PySide6.QtCore import QTimer
        def set_editor_focus():
            if hasattr(self.document_editor, 'text_editor'):
                if hasattr(self.document_editor.text_editor, 'text_edit'):
                    self.document_editor.text_editor.text_edit.setFocus()
        QTimer.singleShot(100, set_editor_focus)

        self.apply_font_settings()
    
        # Initialize all shortcuts
        self.init_shortcuts()
    
    def load_config(self):
        """Load or create the configuration file"""
        if not self.config_path.exists():
            # Create a default config with dark mode enabled and default font sizes
            self.config = {
                "appearance": {
                    "dark_mode": True,
                    "editor_font_size": 14,
                    "menu_font_size": 12,
                    "button_font_size": 12,
                    "dialog_font_size": 11
                },
                "editor": {
                    "show_toolbar": True,
                    "show_line_numbers": False
                }
            }
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
        else:
            # Load existing config
            try:
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
                # Ensure appearance section exists
                if "appearance" not in self.config:
                    self.config["appearance"] = {
                        "dark_mode": True,
                        "editor_font_size": 14,
                        "menu_font_size": 12,
                        "button_font_size": 12,
                        "dialog_font_size": 11
                    }
                # Ensure font settings exist with defaults
                appearance = self.config["appearance"]
                if "editor_font_size" not in appearance:
                    appearance["editor_font_size"] = 14
                if "menu_font_size" not in appearance:
                    appearance["menu_font_size"] = 12
                if "button_font_size" not in appearance:
                    appearance["button_font_size"] = 12
                if "dialog_font_size" not in appearance:
                    appearance["dialog_font_size"] = 11
                
                # Ensure editor settings section exists
                if "editor" not in self.config:
                    self.config["editor"] = {
                        "show_toolbar": True,
                        "show_line_numbers": False
                    }
            except json.JSONDecodeError:
                # Reset config if corrupted
                self.config = {
                    "appearance": {
                        "dark_mode": True,
                        "editor_font_size": 14,
                        "menu_font_size": 12,
                        "button_font_size": 12,
                        "dialog_font_size": 11
                    },
                    "editor": {
                        "show_toolbar": True,
                        "show_line_numbers": False
                    }
                }
    
        # Save any changes made to ensure configuration structure
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def save_config(self):
        """Save the configuration file"""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def init_screens(self):
        """Initialize all screens and add them to the stacked widget"""
        # Import screens lazily to avoid blocking startup
        from gui.main_menu import MainMenuScreen
        from gui.settings.settings_menu import SettingsMenuScreen  
        from gui.settings.appearance_settings import AppearanceSettingsScreen
        from gui.settings.stt_settings import STTSettingsScreen
        from gui.screens.document_editor_screen import DocumentEditorScreen
        from gui.settings.tts_settings import TTSSettingsScreen
        
        # Create screens
        self.main_menu = MainMenuScreen(self)
        self.settings_menu = SettingsMenuScreen(self)
        self.appearance_settings = AppearanceSettingsScreen(self)
        self.stt_settings = STTSettingsScreen(self)
        self.tts_settings = TTSSettingsScreen(self)  # Add TTS settings
    
        # Create document editor screen
        self.document_editor = DocumentEditorScreen(self)
        self.document_editor.navigateBack.connect(self.close)  # Exit application
    
        # Add screens to stacked widget
        self.stacked_widget.addWidget(self.main_menu)
        self.stacked_widget.addWidget(self.settings_menu)
        self.stacked_widget.addWidget(self.appearance_settings)
        self.stacked_widget.addWidget(self.stt_settings)
        self.stacked_widget.addWidget(self.tts_settings)  # Add TTS settings
        self.stacked_widget.addWidget(self.document_editor)
    
        # Connect the create document button in main menu to launch document editor
        self.main_menu.create_doc_btn.clicked.connect(self.on_create_document)

    def navigate_to(self, screen_index):
        """Navigate to the specified screen index"""
        self.stacked_widget.setCurrentIndex(screen_index)
   
    def on_create_document(self):
        """Handle create document button click"""
        # Navigate to document editor screen (index 5 after adding TTS settings)
        self.navigate_to(5)

    def apply_theme(self):
        """Apply the dark or light theme based on config"""
        dark_mode = self.config["appearance"].get("dark_mode", True)
        
        if dark_mode:
            # Dark theme stylesheet
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #2D2D30;
                    color: #E1E1E1;
                }
                QPushButton {
                    background-color: #3E3E42;
                    color: #E1E1E1;
                    border: 1px solid #555555;
                    padding: 10px;
                    border-radius: 5px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #505050;
                }
                QPushButton:pressed {
                    background-color: #007ACC;
                }
                QLabel {
                    color: #E1E1E1;
                    font-size: 16px;
                }
                QCheckBox {
                    color: #E1E1E1;
                    font-size: 14px;
                }
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                }
                QTextEdit {
                    background-color: #1E1E1E;
                    color: #E1E1E1;
                    border: 1px solid #3E3E42;
                }
                QToolBar {
                    background-color: #333333;
                    border: 1px solid #3E3E42;
                    spacing: 3px;
                }
                QToolBar QToolButton {
                    background-color: #3E3E42;
                    border: 1px solid #555555;
                    border-radius: 3px;
                    padding: 3px;
                }
                QToolBar QToolButton:hover {
                    background-color: #505050;
                }
                QToolBar QComboBox, QToolBar QSpinBox {
                    background-color: #1E1E1E;
                    color: #E1E1E1;
                    border: 1px solid #555555;
                    padding: 2px;
                }
                QStatusBar {
                    background-color: #2D2D30;
                    color: #E1E1E1;
                    border-top: 1px solid #3E3E42;
                }
                QDialog {
                    background-color: #2D2D30;
                    color: #E1E1E1;
                }
                QListWidget, QListView, QTreeView, QComboBox {
                    background-color: #1E1E1E;
                    color: #E1E1E1;
                    border: 1px solid #3E3E42;
                }
                QGroupBox {
                    border: 1px solid #3E3E42;
                    margin-top: 1ex;
                    padding-top: 0.5ex;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top center;
                    padding: 0 3px;
                    color: #E1E1E1;
                }
            """)
        else:
            # Light theme stylesheet
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #F0F0F0;
                    color: #333333;
                }
                QPushButton {
                    background-color: #E1E1E1;
                    color: #333333;
                    border: 1px solid #CCCCCC;
                    padding: 10px;
                    border-radius: 5px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #D0D0D0;
                }
                QPushButton:pressed {
                    background-color: #C0C0C0;
                }
                QLabel {
                    color: #333333;
                    font-size: 16px;
                }
                QCheckBox {
                    color: #333333;
                    font-size: 14px;
                }
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                }
                QTextEdit {
                    background-color: #FFFFFF;
                    color: #333333;
                    border: 1px solid #CCCCCC;
                }
                QToolBar {
                    background-color: #E1E1E1;
                    border: 1px solid #CCCCCC;
                    spacing: 3px;
                }
                QToolBar QToolButton {
                    background-color: #F0F0F0;
                    border: 1px solid #CCCCCC;
                    border-radius: 3px;
                    padding: 3px;
                }
                QToolBar QToolButton:hover {
                    background-color: #D0D0D0;
                }
                QToolBar QComboBox, QToolBar QSpinBox {
                    background-color: #FFFFFF;
                    color: #333333;
                    border: 1px solid #CCCCCC;
                    padding: 2px;
                }
                QStatusBar {
                    background-color: #F0F0F0;
                    color: #333333;
                    border-top: 1px solid #CCCCCC;
                }
                QDialog {
                    background-color: #F0F0F0;
                    color: #333333;
                }
                QListWidget, QListView, QTreeView, QComboBox {
                    background-color: #FFFFFF;
                    color: #333333;
                    border: 1px solid #CCCCCC;
                }
                QGroupBox {
                    border: 1px solid #CCCCCC;
                    margin-top: 1ex;
                    padding-top: 0.5ex;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top center;
                    padding: 0 3px;
                    color: #333333;
                }
            """)
   
    def apply_font_settings(self):
        """Apply font settings from config to the application"""
        appearance = self.config.get("appearance", {})
    
        # Get font sizes with defaults
        button_size = appearance.get("button_font_size", 12)
        menu_size = appearance.get("menu_font_size", 12)
        dialog_size = appearance.get("dialog_font_size", 11)
        editor_size = appearance.get("editor_font_size", 14)
    
        # Apply font sizes to all widgets based on their type
        for widget in self.findChildren(QWidget):
            font = widget.font()
        
            # Apply appropriate font size based on widget type
            if isinstance(widget, QPushButton):
                font.setPointSize(button_size)
                widget.setFont(font)
            elif isinstance(widget, QLabel):
                font.setPointSize(dialog_size)
                widget.setFont(font)
            elif isinstance(widget, QCheckBox):
                font.setPointSize(dialog_size)
                widget.setFont(font)
            # For list widgets and other menu items
            elif widget.__class__.__name__ in ('QListWidget', 'QListView', 'QTreeView', 'QComboBox'):
                font.setPointSize(menu_size)
                widget.setFont(font)
            # For dialog labels and controls
            elif widget.__class__.__name__ in ('QGroupBox', 'QRadioButton', 'QSpinBox', 'QSlider'):
                font.setPointSize(dialog_size)
                widget.setFont(font)
            # For text editors
            elif widget.__class__.__name__ == 'QTextEdit':
                font.setPointSize(editor_size)
                widget.setFont(font)
    
        # Update stylesheet for consistently applying fonts to new widgets
        css_dark_bg = '#2D2D30' if self.config['appearance'].get('dark_mode', True) else '#F0F0F0'
        css_dark_fg = '#E1E1E1' if self.config['appearance'].get('dark_mode', True) else '#333333'
        css_dark_border = '#555555' if self.config['appearance'].get('dark_mode', True) else '#CCCCCC'
        css_dark_button = '#3E3E42' if self.config['appearance'].get('dark_mode', True) else '#E1E1E1'
        css_dark_hover = '#505050' if self.config['appearance'].get('dark_mode', True) else '#D0D0D0'
        css_dark_pressed = '#007ACC' if self.config['appearance'].get('dark_mode', True) else '#C0C0C0'
        css_dark_edit_bg = '#1E1E1E' if self.config['appearance'].get('dark_mode', True) else '#FFFFFF'
        
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {css_dark_bg};
                color: {css_dark_fg};
            }}
            QPushButton {{
                background-color: {css_dark_button};
                color: {css_dark_fg};
                border: 1px solid {css_dark_border};
                padding: 10px;
                border-radius: 5px;
                font-size: {button_size}pt;
            }}
            QPushButton:hover {{
                background-color: {css_dark_hover};
            }}
            QPushButton:pressed {{
                background-color: {css_dark_pressed};
            }}
            QLabel {{
                color: {css_dark_fg};
                font-size: {dialog_size}pt;
            }}
            QCheckBox {{
                color: {css_dark_fg};
                font-size: {dialog_size}pt;
            }}
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
            }}
            QTextEdit {{
                background-color: {css_dark_edit_bg};
                color: {css_dark_fg};
                border: 1px solid {css_dark_border};
                font-size: {editor_size}pt;
            }}
            QListWidget, QListView, QTreeView, QComboBox {{
                font-size: {menu_size}pt;
            }}
            QGroupBox, QRadioButton, QSpinBox, QSlider, QDialog {{
                font-size: {dialog_size}pt;
            }}
        """)
    
        # Save the updated config to ensure settings persist
        self.save_config()
    
        # Force update with style refresh
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def show_font_settings(self):
        """Show the font settings dialog"""
        from gui.settings.font_settings import FontSettingsDialog
        dialog = FontSettingsDialog(self.config, self)
        dialog.font_settings_changed.connect(self.apply_font_settings)
        dialog.exec()

    def show_voice_settings(self):
        """Show the voice settings dialog"""
        try:
            from gui.settings.voice_settings import VoiceSettingsDialog

            dialog = VoiceSettingsDialog(self.config, self.assistivox_dir, self)
            dialog.voice_settings_changed.connect(self.on_voice_settings_changed)
            dialog.exec()
        except Exception as e:
            print(f"Error showing voice settings: {e}")

    def on_voice_settings_changed(self):
        """Handle changes to voice settings"""
        # Reload the configuration
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"Error reloading config: {e}")

    def init_shortcuts(self):
        """Initialize global shortcuts for the application"""
        # Add Alt+F shortcut for font settings
        self.font_shortcut = QShortcut(QKeySequence("Alt+F"), self)
        self.font_shortcut.activated.connect(self.show_font_settings)
    
        # Add Ctrl+Alt+V shortcut for clipboard reader
        self.clipboard_reader_shortcut = QShortcut(QKeySequence("Ctrl+Alt+V"), self)
        self.clipboard_reader_shortcut.activated.connect(self.show_clipboard_reader)
    
    def show_clipboard_reader(self):
        """Show the clipboard reader window"""
        from gui.clipboard_reader_window import ClipboardReaderWindow
        if not hasattr(self, 'clipboard_reader_window') or not self.clipboard_reader_window:
            self.clipboard_reader_window = ClipboardReaderWindow(
                config=self.config,
                assistivox_dir=self.assistivox_dir,
                main_window=self  # Pass reference to main window
            )
    
        # Show the window and bring it to the front
        self.clipboard_reader_window.show()
        self.clipboard_reader_window.raise_()
        self.clipboard_reader_window.activateWindow()
