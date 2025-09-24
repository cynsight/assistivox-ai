# gui/settings/font_settings.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QSlider, QSpinBox, QGroupBox
)
from PySide6.QtCore import Qt, Signal

class FontSettingsDialog(QDialog):
    """Dialog for customizing font sizes throughout the application"""
    
    # Signal to notify main window that font settings have changed
    font_settings_changed = Signal()
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Font Settings")
        self.setMinimumWidth(450)
        
        # Storage for controls
        self.spinboxes = {}
        
        # Create the layout
        layout = QVBoxLayout(self)
        
        # Text Editor Font Size
        editor_group = self._create_font_group(
            "Text Editor Font Size", 
            "editor_font_size",
            "Size of text in the editor",
            8, 36, 14
        )
        layout.addWidget(editor_group)
        
        # Menu Items Font Size
        menu_group = self._create_font_group(
            "Menu Items Font Size", 
            "menu_font_size",
            "Size of text in menus and lists",
            8, 24, 12
        )
        layout.addWidget(menu_group)
        
        # Button Labels Font Size
        button_group = self._create_font_group(
            "Button Labels Font Size", 
            "button_font_size",
            "Size of text on buttons",
            8, 20, 12
        )
        layout.addWidget(button_group)
        
        # Dialog/Window Description Font Size
        dialog_group = self._create_font_group(
            "Dialog Text Font Size", 
            "dialog_font_size",
            "Size of descriptive text in dialogs and windows",
            8, 18, 11
        )
        layout.addWidget(dialog_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        reset_button = QPushButton("Reset to Defaults")
        reset_button.clicked.connect(self.reset_to_defaults)
        
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.accept)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(reset_button)
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(save_button)
        
        layout.addLayout(button_layout)
        
        # Load current values
        self.load_settings()
   
    def _create_font_group(self, title, setting_name, description, min_size, max_size, default_size):
        """Create a group for a single font size setting"""
        group = QGroupBox(title)
        layout = QVBoxLayout()
    
        # Description
        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
    
        # Size controls
        size_layout = QHBoxLayout()
    
        # Create the slider
        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_size, max_size)
        slider.setValue(default_size)
    
        # Create the spinbox
        spinbox = QSpinBox()
        spinbox.setRange(min_size, max_size)
        spinbox.setValue(default_size)
        spinbox.setSuffix("px")
    
        # Connect slider to spinbox and vice versa
        slider.valueChanged.connect(spinbox.setValue)
        spinbox.valueChanged.connect(slider.setValue)
        
        # Store reference to spinbox
        self.spinboxes[setting_name] = spinbox
    
        # Add widgets to layout
        size_layout.addWidget(slider)
        size_layout.addWidget(spinbox)
        
        layout.addLayout(size_layout)
        
        group.setLayout(layout)
        return group

    def load_settings(self):
        """Load settings from config"""
        if "appearance" not in self.config:
            return
        
        appearance = self.config["appearance"]
        
        # Load each font size setting
        for setting_name in self.spinboxes:
            if setting_name in appearance:
                size = appearance[setting_name]
                self.spinboxes[setting_name].setValue(size)
    
    def save_settings(self):
        """Save settings to config"""
        if "appearance" not in self.config:
            self.config["appearance"] = {}
        
        appearance = self.config["appearance"]
        
        # Save each font size setting
        for setting_name, spinbox in self.spinboxes.items():
            appearance[setting_name] = spinbox.value()
        
        # Emit signal to notify that settings have changed
        self.font_settings_changed.emit()
    
    def reset_to_defaults(self):
        """Reset all font sizes to their defaults"""
        defaults = {
            "editor_font_size": 14,
            "menu_font_size": 12,
            "button_font_size": 12,
            "dialog_font_size": 11
        }
        
        for setting_name, default_value in defaults.items():
            if setting_name in self.spinboxes:
                self.spinboxes[setting_name].setValue(default_value)
    
    def accept(self):
        """Override accept to save settings before closing"""
        self.save_settings()
        super().accept()
