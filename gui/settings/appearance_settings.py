# gui/settings/appearance_settings.py - Modified to add Font Settings
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QCheckBox
from PySide6.QtCore import Qt
from gui.settings.font_settings import FontSettingsDialog

class AppearanceSettingsScreen(QWidget):
    """Appearance settings screen with theme and font options"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
        # Set up layout
        layout = QVBoxLayout(self)
        
        # Add title
        title = QLabel("Appearance Settings")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(20)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        
        # Add spacer
        layout.addSpacing(40)
        
        # Add font settings button
        font_settings_btn = QPushButton("Font Settings")
        font_settings_btn.setMinimumHeight(50)
        font_settings_btn.clicked.connect(self.show_font_settings)
        layout.addWidget(font_settings_btn)
        
        # Add dark mode toggle
        self.dark_mode_checkbox = QCheckBox("Dark Mode")
        self.dark_mode_checkbox.setChecked(self.main_window.config["appearance"].get("dark_mode", True))
        self.dark_mode_checkbox.stateChanged.connect(self.toggle_dark_mode)
        layout.addWidget(self.dark_mode_checkbox)
        
        # Add spacer
        layout.addSpacing(40)
        
        # Add back button
        back_btn = QPushButton("Back to Settings")
        back_btn.setMinimumHeight(50)
        back_btn.clicked.connect(lambda: self.main_window.navigate_to(1))  # Navigate to settings menu
        layout.addWidget(back_btn)
    
    def toggle_dark_mode(self, state):
        """Toggle dark mode and save to config"""
        self.main_window.config["appearance"]["dark_mode"] = bool(state)
        self.main_window.save_config()
        self.main_window.apply_theme()
    
    def show_font_settings(self):
        """Show the font settings dialog"""
        dialog = FontSettingsDialog(self.main_window.config, self)
        dialog.font_settings_changed.connect(self.main_window.apply_font_settings)
        dialog.exec()
