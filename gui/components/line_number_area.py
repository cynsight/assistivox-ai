# gui/components/line_number_area.py
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QTextFormat
from PySide6.QtCore import QSize, QRect, Qt

class LineNumberArea(QWidget):
    """Widget that displays line numbers next to a QTextEdit"""
    
    def __init__(self, text_edit):
        super().__init__(text_edit)
        self.text_edit = text_edit
        self.text_edit.document().blockCountChanged.connect(self.update_width)
        self.text_edit.document().documentLayoutChanged.connect(self.update)
        self.text_edit.verticalScrollBar().valueChanged.connect(self.update)
        
        # Set initial width
        self.update_width()
    
    def update_width(self):
        """Update the width of the line number area"""
        # Calculate width based on number of digits in line count
        digits = len(str(max(1, self.text_edit.document().blockCount())))
        width = self.fontMetrics().horizontalAdvance('9') * max(2, digits + 1)
        
        # Set fixed width
        self.setFixedWidth(width)
        
        # Update text edit margins
        rect = self.text_edit.contentsRect()
        self.text_edit.setViewportMargins(width if self.isVisible() else 0, 0, 0, 0)
    
    def paintEvent(self, event):
        """Paint the line numbers"""
        if not self.isVisible():
            return
            
        # Fill background
        painter = QPainter(self)
        bg_color = self.palette().color(self.backgroundRole())
        painter.fillRect(event.rect(), bg_color.lighter(110))
        
        # Draw separator line
        painter.setPen(bg_color.darker(120))
        painter.drawLine(self.width() - 1, event.rect().top(), self.width() - 1, event.rect().bottom())
        
        # Get first visible block
        contents = self.text_edit.document().documentLayout().documentSize()
        viewport_height = self.text_edit.viewport().height()
        viewport_offset = self.text_edit.verticalScrollBar().value()
        
        painter.setPen(self.palette().color(self.foregroundRole()))
        
        # Use a slightly larger font
        font = painter.font()
        if self.text_edit.font().pointSize() > 0:
            font.setPointSize(self.text_edit.font().pointSize())
        painter.setFont(font)
        
        # Get and draw each line number
        block = self.text_edit.document().begin()
        line_count = 1
        line_height = self.fontMetrics().height()
        
        while block.isValid():
            position = self.text_edit.document().documentLayout().blockBoundingRect(block).topLeft()
            top = position.y() - viewport_offset
            
            # Only paint visible blocks
            if top >= 0 and top <= viewport_height:
                number = str(line_count)
                painter.drawText(0, int(top), self.width() - 5, line_height,
                                Qt.AlignRight, number)
            
            # Stop if we're beyond viewport
            if top > viewport_height:
                break
                
            block = block.next()
            line_count += 1
    
    def sizeHint(self):
        """Return the recommended size for the widget"""
        return QSize(self.width(), 0)
    
    def setVisible(self, visible):
        """Override setVisible to adjust text edit margins"""
        super().setVisible(visible)
        
        # Update margin when visibility changes
        if visible:
            self.update_width()
        else:
            self.text_edit.setViewportMargins(0, 0, 0, 0)
            
        # Update the display
        self.update()
        self.text_edit.update()
