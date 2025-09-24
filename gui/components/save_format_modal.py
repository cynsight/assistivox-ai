# File: gui/components/save_format_modal.py

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut


class SaveFormatModal(QDialog):
    """Modal dialog for selecting save format (Markdown or Text)"""
    
    # Signal emitted when format is selected
    formatSelected = Signal(str)  # Emits 'markdown' or 'text'
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Document")
        self.setModal(True)
        self.setFixedSize(400, 200)
        
        # Center the dialog on parent
        if parent:
            self.move(
                parent.x() + (parent.width() - self.width()) // 2,
                parent.y() + (parent.height() - self.height()) // 2
            )
        
        self.setup_ui()
        self.setup_shortcuts()
    
    def setup_ui(self):
        """Set up the user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title label
        title_label = QLabel("Choose file format:")
        title_label.setAlignment(Qt.AlignCenter)
        font = title_label.font()
        font.setPointSize(14)
        font.setBold(True)
        title_label.setFont(font)
        layout.addWidget(title_label)
        
        # Buttons layout
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(20)
        
        # Markdown button
        self.markdown_button = QPushButton("Markdown (.md)")
        self.markdown_button.setFixedHeight(50)
        self.markdown_button.clicked.connect(lambda: self.select_format('markdown'))
        self.markdown_button.setDefault(True)  # Default selection
        buttons_layout.addWidget(self.markdown_button)
        
        # Text button  
        self.text_button = QPushButton("Text (.txt)")
        self.text_button.setFixedHeight(50)
        self.text_button.clicked.connect(lambda: self.select_format('text'))
        buttons_layout.addWidget(self.text_button)
        
        layout.addLayout(buttons_layout)
        
        # Cancel button
        cancel_layout = QHBoxLayout()
        cancel_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        cancel_layout.addWidget(cancel_button)
        
        layout.addLayout(cancel_layout)
        
        # Set focus to markdown button by default
        self.markdown_button.setFocus()
    
    def setup_shortcuts(self):
        """Set up keyboard shortcuts"""
        # Escape to cancel
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.escape_shortcut.activated.connect(self.reject)
        
        # M for markdown
        self.markdown_shortcut = QShortcut(QKeySequence("M"), self)
        self.markdown_shortcut.activated.connect(lambda: self.select_format('markdown'))
        
        # T for text
        self.text_shortcut = QShortcut(QKeySequence("T"), self)
        self.text_shortcut.activated.connect(lambda: self.select_format('text'))
        
        # Enter/Return to select default (markdown)
        self.enter_shortcut = QShortcut(QKeySequence(Qt.Key_Return), self)
        self.enter_shortcut.activated.connect(lambda: self.select_format('markdown'))
        
        self.enter_shortcut2 = QShortcut(QKeySequence(Qt.Key_Enter), self)
        self.enter_shortcut2.activated.connect(lambda: self.select_format('markdown'))
    
    def select_format(self, format_type):
        """Handle format selection"""
        self.formatSelected.emit(format_type)
        self.accept()
    
    def keyPressEvent(self, event):
        """Handle key press events for button navigation"""
        # Tab between buttons
        if event.key() == Qt.Key_Tab:
            if self.markdown_button.hasFocus():
                self.text_button.setFocus()
            else:
                self.markdown_button.setFocus()
            event.accept()
            return
        
        # Shift+Tab for reverse navigation
        if event.key() == Qt.Key_Tab and event.modifiers() & Qt.ShiftModifier:
            if self.text_button.hasFocus():
                self.markdown_button.setFocus()
            else:
                self.text_button.setFocus()
            event.accept()
            return
            
        # Enter/Space activates focused button
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            if self.markdown_button.hasFocus():
                self.select_format('markdown')
            elif self.text_button.hasFocus():
                self.select_format('text')
            event.accept()
            return
            
        super().keyPressEvent(event)
