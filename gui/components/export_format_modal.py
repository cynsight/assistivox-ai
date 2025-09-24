# File: gui/components/export_format_modal.py

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut


class ExportFormatModal(QDialog):
    """Modal dialog for selecting export format (Text or PDF for Alt+E)"""
    
    # Signal emitted when format is selected
    formatSelected = Signal(str)  # Emits 'text' or 'pdf'
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Document")
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
        title_label = QLabel("Choose export format:")
        title_label.setAlignment(Qt.AlignCenter)
        font = title_label.font()
        font.setPointSize(14)
        font.setBold(True)
        title_label.setFont(font)
        layout.addWidget(title_label)
        
        # Buttons layout - horizontal like your original
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(20)
        
        # Text button (original)
        self.text_button = QPushButton("Text (.txt)")
        self.text_button.setFixedHeight(50)
        self.text_button.clicked.connect(lambda: self.select_format('text'))
        self.text_button.setDefault(True)  # Default selection
        buttons_layout.addWidget(self.text_button)
        
        # PDF button (new)
        self.pdf_button = QPushButton("PDF (.pdf)")
        self.pdf_button.setFixedHeight(50)
        self.pdf_button.clicked.connect(lambda: self.select_format('pdf'))
        buttons_layout.addWidget(self.pdf_button)
        
        layout.addLayout(buttons_layout)
        
        # Cancel button
        cancel_layout = QHBoxLayout()
        cancel_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        cancel_layout.addWidget(cancel_button)
        
        layout.addLayout(cancel_layout)
        
        # Set focus to text button by default
        self.text_button.setFocus()
    
    def setup_shortcuts(self):
        """Set up keyboard shortcuts"""
        # Escape to cancel
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.escape_shortcut.activated.connect(self.reject)
        
        # T for text
        self.text_shortcut = QShortcut(QKeySequence("T"), self)
        self.text_shortcut.activated.connect(lambda: self.select_format('text'))
        
        # P for PDF
        self.pdf_shortcut = QShortcut(QKeySequence("P"), self)
        self.pdf_shortcut.activated.connect(lambda: self.select_format('pdf'))
        
        # Enter/Return to select default (text)
        self.enter_shortcut = QShortcut(QKeySequence(Qt.Key_Return), self)
        self.enter_shortcut.activated.connect(lambda: self.select_format('text'))
        
        self.enter_shortcut2 = QShortcut(QKeySequence(Qt.Key_Enter), self)
        self.enter_shortcut2.activated.connect(lambda: self.select_format('text'))
    
    def select_format(self, format_type):
        """Handle format selection"""
        self.formatSelected.emit(format_type)
        self.accept()
    
    def keyPressEvent(self, event):
        """Handle key press events for button navigation"""
        # Enter/Space activates the text button
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.select_format('text')
            event.accept()
            return
            
        super().keyPressEvent(event)
