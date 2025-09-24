# gui/main_menu.py - Main menu screen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt

class MainMenuScreen(QWidget):
    """Main menu screen with primary navigation options"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
        # Set up layout
        layout = QVBoxLayout(self)
        
        # Add title
        title = QLabel("Assistivox - Main Menu")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(20)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        
        # Add spacer
        layout.addSpacing(40)
        
        # Add buttons
        self.create_doc_btn = QPushButton("Create Document")
        self.create_doc_btn.setMinimumHeight(50)
        # Note: The connection to on_create_document is made in main_window.py
        layout.addWidget(self.create_doc_btn)
        
        settings_btn = QPushButton("Settings")
        settings_btn.setMinimumHeight(50)
        settings_btn.clicked.connect(lambda: main_window.navigate_to(1))  # Navigate to settings menu
        layout.addWidget(settings_btn)
        
        exit_btn = QPushButton("Exit")
        exit_btn.setMinimumHeight(50)
        exit_btn.clicked.connect(main_window.close)
        layout.addWidget(exit_btn)
