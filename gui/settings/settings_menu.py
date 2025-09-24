# gui/settings/settings_menu.py - Settings menu screen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt

class SettingsMenuScreen(QWidget):
    """Settings menu screen with settings categories"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
        # Set up layout
        layout = QVBoxLayout(self)
        
        # Add title
        title = QLabel("Settings")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(20)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        
        # Add spacer
        layout.addSpacing(40)
        
        # Add buttons
        appearance_btn = QPushButton("Appearance")
        appearance_btn.setMinimumHeight(50)
        appearance_btn.clicked.connect(lambda: main_window.navigate_to(2))  # Navigate to appearance settings
        layout.addWidget(appearance_btn)
        
        tts_btn = QPushButton("Text to Speech Models")
        tts_btn.setMinimumHeight(50)
        tts_btn.clicked.connect(lambda: main_window.navigate_to(4))  # Navigate to TTS settings
        layout.addWidget(tts_btn)
        
        stt_btn = QPushButton("Speech to Text Models")
        stt_btn.setMinimumHeight(50)
        stt_btn.clicked.connect(lambda: main_window.navigate_to(3))  # Navigate to STT settings
        layout.addWidget(stt_btn)
        
        back_btn = QPushButton("Back to Main Menu")
        back_btn.setMinimumHeight(50)
        back_btn.clicked.connect(lambda: main_window.navigate_to(0))  # Navigate to main menu
        layout.addWidget(back_btn)
