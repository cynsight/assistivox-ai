# gui/components/readonly_tts_widget.py
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, 
    QLabel, QFrame, QWidget, QMainWindow
)
from PySide6.QtGui import (
    QFont, QTextCharFormat, QColor, QTextCursor, QKeySequence, QShortcut,
    QTextDocument
)
from PySide6.QtCore import Qt, Signal

from gui.tts.tts_manager import TTSManager
from gui.components.markdown_handler import MarkdownHandler


class ReadOnlyTTSTextEdit(QTextEdit):
    """Read-only text edit with zoom support for TTS display"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.zoom_factor = 1.0
        
    def wheelEvent(self, event):
        """Handle mouse wheel events for zooming when Ctrl is pressed"""
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                # Zoom in
                if hasattr(self.parent(), 'zoom_in'):
                    self.parent().zoom_in()
            elif delta < 0:
                # Zoom out
                if hasattr(self.parent(), 'zoom_out'):
                    self.parent().zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse clicks to jump to sentences during TTS playback"""
        print(f"DEBUG: Mouse click detected at position {event.pos()}")
    
        # Only handle left clicks
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        # Find the ReadOnlyTTSWidget by traversing up the parent chain
        tts_widget = None
        widget = self
        while widget and not isinstance(widget, ReadOnlyTTSWidget):
            widget = widget.parent()
    
        if widget and isinstance(widget, ReadOnlyTTSWidget):
            tts_widget = widget
    
        print(f"DEBUG: Found TTS widget: {tts_widget is not None}")
    
        if not tts_widget:
            print("DEBUG: Could not find ReadOnlyTTSWidget in parent chain")
            super().mousePressEvent(event)
            return
    
        print(f"DEBUG: TTS manager exists: {hasattr(tts_widget, 'tts_manager') and tts_widget.tts_manager is not None}")
    
        if not hasattr(tts_widget, 'tts_manager') or not tts_widget.tts_manager:
            print("DEBUG: No TTS manager on TTS widget")
            super().mousePressEvent(event)
            return
    
        tts_manager = tts_widget.tts_manager
        print(f"DEBUG: TTS manager is_speaking: {tts_manager.is_speaking}")
    
        has_worker = tts_manager.tts_worker is not None
        print(f"DEBUG: TTS manager has worker: {has_worker}")
    
        if has_worker:
            worker_running = tts_manager.tts_worker.isRunning()
            print(f"DEBUG: TTS worker is running: {worker_running}")
        else:
            worker_running = False
    
        # Check if TTS is active (speaking OR has active worker)
        tts_is_active = tts_manager.is_speaking or (has_worker and worker_running)
        print(f"DEBUG: TTS is active: {tts_is_active}")
    
        if tts_is_active:
            print("DEBUG: TTS is active, processing click for sentence jump")
    
            # Get cursor position at click location
            cursor = self.cursorForPosition(event.pos())
    
            # Get the block (line) and position within block
            block = cursor.block()
            block_number = block.blockNumber()
            position_in_block = cursor.positionInBlock()
    
            print(f"DEBUG: Click at block {block_number}, position {position_in_block}")
    
            # Find sentence ID using TTS widget's method
            sentence_id = tts_widget.find_sentence_id_from_offset(block_number, position_in_block)
    
            if sentence_id:
                block_idx, sent_idx = sentence_id
                print(f"DEBUG: Clicked sentence: block {block_idx}, sentence {sent_idx}")
    
                # Use existing navigation to jump to this sentence
                tts_manager.set_sentence_index(block_idx, sent_idx)
                tts_manager._navigate_to_sentence(block_idx, sent_idx)
    
                # Accept the event to prevent further processing
                event.accept()
                return
            else:
                print("DEBUG: Could not find sentence ID for click position")
        else:
            print("DEBUG: TTS not active")
    
        # If we didn't handle the click for TTS navigation, pass to parent
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        """Handle key press events - let parent handle navigation keys"""
        # Pass all key events to parent implementation (the main window will handle navigation)
        super().keyPressEvent(event)

class ReadOnlyTTSWidget(QMainWindow):
    """
    Read-only window for TTS playback with sentence highlighting.
    Opens as independent window when TTS is launched.
    """
   
    def __init__(self, parent=None, config=None, assistivox_dir=None):
        super().__init__(parent)
        
        # Store references
        self.config = config
        self.assistivox_dir = assistivox_dir
        self.parent_editor = parent
        self.sentence_boundary_data = None  # Store sentence detection results
        
        # Set up independent window with proper flags
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle("Text-to-Speech Reader")
        self.setMinimumSize(600, 400)
        
        # Store reference to shared PDF viewer window
        self.pdf_viewer_window = None
        
        # Copy zoom level from parent editor if available
        self.zoom_level = 100
        if hasattr(parent, 'zoom_level'):
            self.zoom_level = parent.zoom_level
        
        # Set up UI
        self.setup_ui()
        
        # Initialize TTS manager for this widget
        self.tts_manager = TTSManager(self.text_edit, config, assistivox_dir)
        
        # Add keyboard shortcuts
        self.add_shortcuts()

        # Store markdown structure for navigation
        self.markdown_structure = []  # Hierarchical structure of the document
        self.heading_positions = {}   # Maps heading IDs to (block_idx, sent_idx)

    def setup_ui(self):
        """Set up the user interface"""
        # Create central widget for QMainWindow
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Header
        header = QLabel("Text-to-Speech Reader")
        header.setAlignment(Qt.AlignCenter)
        font = header.font()
        font.setBold(True)
        font.setPointSize(14)
        header.setFont(font)
        layout.addWidget(header)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # Text display area
        self.text_edit = ReadOnlyTTSTextEdit(self)
        layout.addWidget(self.text_edit)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.play_pause_button = QPushButton("Play (Alt+S)")
        self.play_pause_button.clicked.connect(self.toggle_speech)
        button_layout.addWidget(self.play_pause_button)
        
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_speech)
        button_layout.addWidget(self.stop_button)
        
        button_layout.addStretch()
        
        # Zoom controls
        zoom_label = QLabel("Zoom:")
        button_layout.addWidget(zoom_label)
        
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setMaximumWidth(30)
        self.zoom_in_button.clicked.connect(self.zoom_in)
        button_layout.addWidget(self.zoom_in_button)
        
        self.zoom_out_button = QPushButton("-")
        self.zoom_out_button.setMaximumWidth(30)
        self.zoom_out_button.clicked.connect(self.zoom_out)
        button_layout.addWidget(self.zoom_out_button)
       
        self.zoom_display_label = QLabel("100%")
        self.zoom_display_label.setAlignment(Qt.AlignCenter)
        self.zoom_display_label.setMinimumWidth(50)
        button_layout.addWidget(self.zoom_display_label)

        # Add separate reset button
        self.zoom_reset_button = QPushButton("Reset")
        self.zoom_reset_button.setMaximumWidth(60)
        self.zoom_reset_button.clicked.connect(self.zoom_reset)
        button_layout.addWidget(self.zoom_reset_button)
        
        button_layout.addStretch()
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        # Apply initial zoom
        self.apply_zoom()
        
    def add_shortcuts(self):
        """Add keyboard shortcuts for TTS navigation and controls"""
        # Alt+S for play/pause
        self.speech_shortcut = QShortcut(QKeySequence("Alt+S"), self)
        self.speech_shortcut.activated.connect(self.toggle_speech)
    
        # Alt+. for next sentence
        self.next_sentence_shortcut = QShortcut(QKeySequence("Alt+."), self)
        self.next_sentence_shortcut.activated.connect(self.navigate_to_next_sentence)
        
        # Alt+, for previous sentence  
        self.prev_sentence_shortcut = QShortcut(QKeySequence("Alt+,"), self)
        self.prev_sentence_shortcut.activated.connect(self.navigate_to_previous_sentence)
        
        # Alt+] for next paragraph (block)
        self.next_paragraph_shortcut = QShortcut(QKeySequence("Alt+]"), self)
        self.next_paragraph_shortcut.activated.connect(self.navigate_to_next_paragraph)
        
        # Alt+[ for previous paragraph (block)
        self.prev_paragraph_shortcut = QShortcut(QKeySequence("Alt+["), self)
        self.prev_paragraph_shortcut.activated.connect(self.navigate_to_previous_paragraph)

        # Alt+PageDown for next heading block
        self.next_heading_block_shortcut = QShortcut(QKeySequence("Alt+PgDown"), self)
        self.next_heading_block_shortcut.activated.connect(self.navigate_to_next_heading_block)

        # Alt+PageUp for previous heading block  
        self.prev_heading_block_shortcut = QShortcut(QKeySequence("Alt+PgUp"), self)
        self.prev_heading_block_shortcut.activated.connect(self.navigate_to_previous_heading_block)

        # Shift+Alt+PageDown for next horizontal rule section
        self.next_horizontal_rule_section_shortcut = QShortcut(QKeySequence("Shift+Alt+PgDown"), self)
        self.next_horizontal_rule_section_shortcut.activated.connect(self.navigate_to_next_horizontal_rule_section)

        # Shift+Alt+PageUp for previous horizontal rule section
        self.prev_horizontal_rule_section_shortcut = QShortcut(QKeySequence("Shift+Alt+PgUp"), self)
        self.prev_horizontal_rule_section_shortcut.activated.connect(self.navigate_to_previous_horizontal_rule_section)
        
        # Zoom shortcuts
        self.zoom_in_shortcut = QShortcut(QKeySequence.ZoomIn, self)
        self.zoom_in_shortcut.activated.connect(self.zoom_in)
        
        self.zoom_out_shortcut = QShortcut(QKeySequence.ZoomOut, self)
        self.zoom_out_shortcut.activated.connect(self.zoom_out)
        
        self.zoom_reset_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        self.zoom_reset_shortcut.activated.connect(self.zoom_reset)
        
        # Escape to close
        self.escape_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.escape_shortcut.activated.connect(self.close)

        # F11 for fullscreen toggle
        self.fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        self.fullscreen_shortcut.activated.connect(self.toggle_fullscreen)

        # Alt+Home to reset to first sentence in first block
        self.home_shortcut = QShortcut(QKeySequence("Alt+Home"), self)
        self.home_shortcut.activated.connect(self.navigate_to_first_sentence)

        # Add shortcut for Alt+O to open original PDF
        self.original_pdf_shortcut = QShortcut(QKeySequence("Alt+O"), self)
        self.original_pdf_shortcut.activated.connect(self.open_original_pdf)

        # Alt+G for go to page
        self.go_to_page_shortcut = QShortcut(QKeySequence("Alt+G"), self)
        self.go_to_page_shortcut.activated.connect(self.show_go_to_page_dialog)

    def keyPressEvent(self, event):
        """Handle key press events for the TTS window"""
        # Handle Alt+PageUp/PageDown for heading navigation FIRST
        if event.key() == Qt.Key_PageDown and event.modifiers() & Qt.AltModifier:
            self.navigate_to_next_heading_block()  # Changed from navigate_to_next_heading()
            event.accept()
            return
    
        if event.key() == Qt.Key_PageUp and event.modifiers() & Qt.AltModifier:
            self.navigate_to_previous_heading_block()  # Changed from navigate_to_previous_heading()
            event.accept()
            return
        
        # Handle Ctrl+PageUp/PageDown for scrolling
        if event.key() == Qt.Key_PageDown and event.modifiers() & Qt.ControlModifier:
            self.scroll_to_next_heading()
            event.accept()
            return
        
        if event.key() == Qt.Key_PageUp and event.modifiers() & Qt.ControlModifier:
            self.scroll_to_previous_heading()
            event.accept()
            return
        
        # Handle Escape to close
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()
            return
    
        # Pass other key events to parent
        super().keyPressEvent(event)

    def start_tts_automatically(self):
         """Start TTS automatically when widget opens"""
         if hasattr(self, 'tts_manager') and self.text_edit.document() and not self.text_edit.document().isEmpty():
             # Start TTS directly without toggling
             if not self.tts_manager.is_speaking:
                 self.tts_manager.toggle_speech()
                 # Update button text
                 if self.tts_manager.is_speaking:
                     self.play_pause_button.setText("Pause (Alt+S)")
                 else:
                     self.play_pause_button.setText("Play (Alt+S)")

    def set_document_content(self, markdown_content):
        """Set the document content to display"""
        print(f"DEBUG: Markdown content length: {len(markdown_content)}")
    
        # Parse markdown structure BEFORE conversion
        self.markdown_structure = self._parse_markdown_to_structure(markdown_content)
    
        # Use MarkdownHandler to set the content properly
        from gui.components.markdown_handler import MarkdownHandler
        MarkdownHandler.markdown_to_rich_text(self.text_edit.document(), markdown_content)
    
        # Check the result
        document = self.text_edit.document()
        print(f"DEBUG: Document character count after markdown: {document.characterCount()}")
        print(f"DEBUG: Plain text length: {len(self.text_edit.toPlainText())}")
    
        # Run sentence boundary detection and store results when document is set
        try:
            from gui.nlp.sentence_detector import SentenceDetector
            import os
        
            # Create sentence detector with config
            config_path = os.path.join(self.assistivox_dir, "config.json")
            detector = SentenceDetector(config_path)
        
            # Detect sentences in the document and store in widget
            self.sentence_boundary_data = detector.detect_sentences_in_document(self.text_edit.document())
        
            print(f"Sentence detection complete: {len(self.sentence_boundary_data)} blocks processed")
        
            # Map headings to their positions in the rendered text
            self._map_headings_to_positions()
        
        except Exception as e:
            print(f"Error during sentence detection: {e}")
            self.sentence_boundary_data = None
    
        # Reset TTS sentence index when setting new content
        if hasattr(self, 'tts_manager'):
            self.tts_manager.reset_sentence_index()
    
    def scroll_to_top(self):
        """Scroll to the top of the document after rendering is complete"""
        # Position cursor at the start of document
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.text_edit.setTextCursor(cursor)
    
        # Scroll to top
        self.text_edit.verticalScrollBar().setValue(0)
        self.text_edit.horizontalScrollBar().setValue(0)

    def toggle_speech(self):
        """Toggle text-to-speech on/off"""
        if hasattr(self, 'tts_manager'):
            self.tts_manager.toggle_speech()
            # Update button text based on TTS state
            if self.tts_manager.is_speaking:
                self.play_pause_button.setText("Pause (Alt+S)")
            else:
                self.play_pause_button.setText("Play (Alt+S)")
    
    def stop_speech(self):
        """Stop text-to-speech"""
        if hasattr(self, 'tts_manager'):
            # This will call our enhanced stop_speech which includes cleanup
            self.tts_manager.stop_speech()

    def navigate_to_next_sentence(self):
        """Navigate to next sentence during TTS"""
        if hasattr(self, 'tts_manager'):
            self.tts_manager.navigate_to_next_sentence()
    
    def store_sentence_boundary_data(self, sentence_data):
        """Store sentence boundary data for click-to-jump functionality"""
        self.sentence_boundary_data = sentence_data

    def find_sentence_id_from_offset(self, block_number, offset):
        """
        Find sentence ID given block number and offset within that block.
    
        Args:
            block_number (int): The block number (line number) in the document
            offset (int): Offset from the beginning of that block
        
        Returns:
            tuple: (block_number, sentence_index) or None if not found
        """
        if not self.sentence_boundary_data or block_number >= len(self.sentence_boundary_data):
            return None
        
        block_data = self.sentence_boundary_data[block_number]
        offsets = block_data['offsets']
        sentences = block_data['sentences']
    
        # Find the sentence that contains the given offset
        for sentence_index, (start_offset, end_offset) in enumerate(offsets):
            if start_offset <= offset <= end_offset:
                return (block_number, sentence_index)
    
        return None

    def navigate_to_previous_sentence(self):
        """Navigate to previous sentence during TTS"""
        if hasattr(self, 'tts_manager'):
            self.tts_manager.navigate_to_previous_sentence()

    def navigate_to_next_paragraph(self):
        """Navigate TTS to next paragraph (block) and scroll to make it visible"""
        print("DEBUG: navigate_to_next_paragraph called")
        if not hasattr(self, 'tts_manager') or not self.tts_manager:
            print("DEBUG: No TTS manager available")
            return

        if self.tts_manager.navigate_to_next_paragraph():
            # Get the new position and scroll to it
            block_idx, sent_idx = self.tts_manager.tts_sentence_index
            self._scroll_to_position(block_idx, sent_idx)
            print(f"DEBUG: Scrolled to next paragraph at block {block_idx}, sentence {sent_idx}")

    def navigate_to_previous_paragraph(self):
        """Navigate TTS to previous paragraph (block) and scroll to make it visible"""
        print("DEBUG: navigate_to_previous_paragraph called")
        if not hasattr(self, 'tts_manager') or not self.tts_manager:
            print("DEBUG: No TTS manager available")
            return

        if self.tts_manager.navigate_to_previous_paragraph():
            # Get the new position and scroll to it
            block_idx, sent_idx = self.tts_manager.tts_sentence_index
            self._scroll_to_position(block_idx, sent_idx)
            print(f"DEBUG: Scrolled to previous paragraph at block {block_idx}, sentence {sent_idx}")

    def zoom_in(self):
        """Increase zoom level"""
        if self.zoom_level < 300:
            self.zoom_level += 10
            self.apply_zoom()
            self.update_zoom_display()
   
    def zoom_out(self):
        """Decrease zoom level"""
        if self.zoom_level > 50:
            self.zoom_level -= 10
            self.apply_zoom()
            self.update_zoom_display()
   
    def zoom_reset(self):
        """Reset zoom to 100%"""
        self.zoom_level = 100
        self.apply_zoom()
        self.update_zoom_display()
   
    def apply_zoom(self):
        """Apply the current zoom level using font scaling approach like main editor"""
        # Get base font size from config or use default
        base_font_size = 14
        if self.config and 'appearance' in self.config:
            base_font_size = self.config['appearance'].get('editor_font_size', 14)
    
        # Calculate new font size
        new_size = base_font_size * (self.zoom_level / 100.0)
    
        # Store cursor position and scroll position
        cursor_position = self.text_edit.textCursor().position()
        scroll_position = self.text_edit.verticalScrollBar().value()
    
        # Set the base font for the text editor and document
        # This affects the default font size while preserving all rich text formatting
        font = self.text_edit.font()
        font.setPointSizeF(new_size)
        self.text_edit.setFont(font)
    
        # Set the default font for the document (affects display scaling)
        document = self.text_edit.document()
        document.setDefaultFont(font)
    
        # Restore cursor and scroll positions
        cursor = self.text_edit.textCursor()
        cursor.setPosition(min(cursor_position, document.characterCount() - 1))
        self.text_edit.setTextCursor(cursor)
        self.text_edit.verticalScrollBar().setValue(scroll_position)

    def update_zoom_display(self):
        """Update the zoom display label to show current zoom level"""
        self.zoom_display_label.setText(f"{self.zoom_level}%")
    
    def closeEvent(self, event):
        """Handle dialog close event"""
        # Stop any active TTS
        self.stop_speech()
        
        # Return focus to parent editor if it exists
        if self.parent_editor:
            self.parent_editor.setFocus()
        
        event.accept()

    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
    
    def mouseDoubleClickEvent(self, event):
        """Handle double-click events on the title bar"""
        # Check if the double-click is on the title bar area
        if event.y() <= 30:  # Approximate title bar height
            self.toggle_fullscreen()
        else:
            super().mouseDoubleClickEvent(event)

    def navigate_to_first_sentence(self):
        """Navigate to the first sentence in the first block"""
        if hasattr(self, 'tts_manager'):
            if self.tts_manager.is_speaking:
                # If TTS is playing, jump to first sentence
                self.tts_manager.navigate_to_first_sentence()
            else:
                # If TTS is stopped, reset to first sentence and start
                self.tts_manager.reset_sentence_index()
                self.tts_manager.toggle_speech()

    def navigate_to_next_heading(self):
        """Navigate TTS to the next markdown heading of any level"""
        print("DEBUG: navigate_to_next_heading called")
        if not hasattr(self, 'tts_manager') or not self.tts_manager:
            print("DEBUG: No TTS manager available")
            return

        print(f"DEBUG: sentence_boundary_data exists: {self.sentence_boundary_data is not None}")
        if self.sentence_boundary_data:
            print(f"DEBUG: Number of blocks: {len(self.sentence_boundary_data)}")
            current_block, current_sent = self.tts_manager.tts_sentence_index
            print(f"DEBUG: Current TTS position: block {current_block}, sentence {current_sent}")

            # Show some sample sentences to check if headings exist
            for i, block_data in enumerate(self.sentence_boundary_data[:5]):  # First 5 blocks
                if block_data['sentences']:
                    first_sentence = block_data['sentences'][0].strip()
                    print(f"DEBUG: Block {i} first sentence: '{first_sentence}' (starts with #: {first_sentence.startswith('#')})")
    
        heading_position = self._find_next_heading()
        print(f"DEBUG: Next heading position: {heading_position}")
        if heading_position is not None:
            block_idx, sent_idx = heading_position
            if self.tts_manager.is_speaking:
                # If TTS is playing, jump to the heading
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
                self.tts_manager._navigate_to_sentence(block_idx, sent_idx)
            else:
                # If TTS is stopped, start from the heading
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
                self.tts_manager.toggle_speech()
        else:
            print("DEBUG: No next heading found")

    def _find_next_heading(self):
        """Find the next heading using the parsed markdown structure"""
        if not self.heading_positions or not hasattr(self, 'tts_manager'):
            return None
    
        # Get current TTS position
        current_block, current_sent = self.tts_manager.tts_sentence_index
    
        # Get all heading positions sorted by position
        positions = [(pos[0], pos[1], heading_id) for heading_id, pos in self.heading_positions.items()]
        positions.sort()  # Sort by (block_idx, sent_idx)
    
        # Find next heading after current position
        for block_idx, sent_idx, heading_id in positions:
            if (block_idx > current_block or
                (block_idx == current_block and sent_idx > current_sent)):
                return (block_idx, sent_idx)
    
        return None
    
    def _find_previous_heading(self):
        """Find the previous heading using the parsed markdown structure"""
        if not self.heading_positions or not hasattr(self, 'tts_manager'):
            return None
    
        # Get current TTS position
        current_block, current_sent = self.tts_manager.tts_sentence_index
    
        # Get all heading positions sorted by position (reverse for previous)
        positions = [(pos[0], pos[1], heading_id) for heading_id, pos in self.heading_positions.items()]
        positions.sort(reverse=True)  # Sort in reverse order
    
        # Find previous heading before current position
        for block_idx, sent_idx, heading_id in positions:
            if (block_idx < current_block or
                (block_idx == current_block and sent_idx < current_sent)):
                return (block_idx, sent_idx)
    
        return None

    def _find_previous_heading_for_scroll(self):
        """Find the previous heading for scrolling based on current view position"""
        if not self.heading_positions:
            return None
    
        # Get current cursor position in the document
        cursor = self.text_edit.textCursor()
        cursor_position = cursor.position()
        
        # Convert cursor position to block/sentence coordinates
        current_block, current_sent = self._convert_cursor_position_to_block_sentence(cursor_position)
        if current_block is None:
            return None
    
        # Get all heading positions sorted by position (reverse for previous)
        positions = [(pos[0], pos[1], heading_id) for heading_id, pos in self.heading_positions.items()]
        positions.sort(reverse=True)  # Sort in reverse order
    
        # Find previous heading before current position
        for block_idx, sent_idx, heading_id in positions:
            if (block_idx < current_block or
                (block_idx == current_block and sent_idx < current_sent)):
                return (block_idx, sent_idx)
    
        return None

    def _convert_cursor_position_to_block_sentence(self, cursor_position):
        """Convert absolute cursor position to block/sentence coordinates"""
        if not self.sentence_boundary_data:
            return None, None

        position_counter = 0

        for block_idx, block_data in enumerate(self.sentence_boundary_data):
            if not block_data['sentences']:
                position_counter += 1  # Empty block still takes 1 character (newline)
                continue

            # Use the original block text, not reconstructed from sentences
            block_text = block_data['block_text']
            block_length = len(block_text)
            block_end = position_counter + block_length

            if cursor_position >= position_counter and cursor_position <= block_end:
                # We're in this block, find which sentence
                position_in_block = cursor_position - position_counter

                if block_data['offsets']:
                    for sent_idx, (start_offset, end_offset) in enumerate(block_data['offsets']):
                        if position_in_block >= start_offset and position_in_block <= end_offset:
                            print(f"DEBUG: Cursor at position {cursor_position} -> block {block_idx}, sentence {sent_idx}")
                            return block_idx, sent_idx

                # If not found in any sentence, return first sentence of block
                print(f"DEBUG: Cursor at position {cursor_position} -> block {block_idx}, sentence 0 (default)")
                return block_idx, 0

            position_counter = block_end + 1  # +1 for newline between blocks

        # If we're past the end, return the last block/sentence
        if self.sentence_boundary_data:
            last_block = len(self.sentence_boundary_data) - 1
            last_sentence = len(self.sentence_boundary_data[last_block]['sentences']) - 1 if self.sentence_boundary_data[last_block]['sentences'] else 0
            print(f"DEBUG: Cursor at position {cursor_position} -> block {last_block}, sentence {last_sentence} (end of document)")
            return last_block, last_sentence

        return None, None

    def _parse_markdown_to_structure(self, markdown_content):
        """Parse markdown into hierarchical structure"""
        import re
    
        lines = markdown_content.split('\n')
        structure = []
        heading_stack = []  # Stack to track heading hierarchy
        current_content = []
        heading_id = 0
    
        for line_idx, line in enumerate(lines):
            heading_match = re.match(r'^(#{1,6})\s+(.+)', line.strip())
        
            if heading_match:
                # Save any accumulated content to the previous section
                if current_content and heading_stack:
                    heading_stack[-1]['content'] = '\n'.join(current_content)
                current_content = []
            
                level = len(heading_match.group(1))
                text = heading_match.group(2).strip()
                heading_id += 1
            
                heading_obj = {
                    'id': heading_id,
                    'level': level,
                    'text': text,
                    'line_idx': line_idx,
                    'content': '',
                    'children': [],
                    'block_idx': None,
                    'sent_idx': None
                }
            
                # Pop stack until we find the right parent level
                while heading_stack and heading_stack[-1]['level'] >= level:
                    completed_heading = heading_stack.pop()
                    completed_heading['content'] = '\n'.join(current_content) if current_content else completed_heading['content']
                    current_content = []
            
                # Add to parent or root
                if heading_stack:
                    heading_stack[-1]['children'].append(heading_obj)
                else:
                    structure.append(heading_obj)
            
                heading_stack.append(heading_obj)
            else:
                # Regular content line
                current_content.append(line)
    
        # Handle any remaining content
        if current_content and heading_stack:
            heading_stack[-1]['content'] = '\n'.join(current_content)
    
        print(f"DEBUG: Parsed markdown structure with {self._count_headings(structure)} headings")
        return structure

    def _count_headings(self, structure):
        """Recursively count all headings in the structure"""
        count = 0
        for item in structure:
            count += 1
            count += self._count_headings(item.get('children', []))
        return count

    def _map_headings_to_positions(self):
        """Map heading text to positions in rendered document"""
        if not self.sentence_boundary_data or not self.markdown_structure:
            return
        
        # Flatten all headings for easier searching
        all_headings = []
        self._flatten_headings(self.markdown_structure, all_headings)
        
        for heading in all_headings:
            heading_text = heading['text']
            
            # Search for this heading text in the sentence data
            for block_idx, block_data in enumerate(self.sentence_boundary_data):
                if not block_data['sentences']:
                    continue
                    
                for sent_idx, sentence in enumerate(block_data['sentences']):
                    # Check if this sentence matches the heading text
                    sentence_clean = sentence.strip().lower()
                    heading_clean = heading_text.strip().lower()
                    
                    if heading_clean in sentence_clean or sentence_clean in heading_clean:
                        heading['block_idx'] = block_idx
                        heading['sent_idx'] = sent_idx
                        self.heading_positions[heading['id']] = (block_idx, sent_idx)
                        print(f"DEBUG: Mapped heading '{heading_text}' to position {block_idx}-{sent_idx}")
                        break
                
                if heading['block_idx'] is not None:
                    break
    
    def _flatten_headings(self, structure, result):
        """Flatten hierarchical structure into a list for easier searching"""
        for item in structure:
            result.append(item)
            self._flatten_headings(item.get('children', []), result)

    def scroll_to_next_heading(self):
        """Scroll view to the next heading without affecting TTS position"""
        print("DEBUG: scroll_to_next_heading called")
        heading_position = self._find_next_heading_for_scroll()
        if heading_position is not None:
            block_idx, sent_idx = heading_position
            self._scroll_to_position(block_idx, sent_idx)
        else:
            print("DEBUG: No next heading found for scrolling")

    def scroll_to_previous_heading(self):
        """Scroll view to the previous heading without affecting TTS position"""
        print("DEBUG: scroll_to_previous_heading called")
        heading_position = self._find_previous_heading_for_scroll()
        if heading_position is not None:
            block_idx, sent_idx = heading_position
            self._scroll_to_position(block_idx, sent_idx)
        else:
            print("DEBUG: No previous heading found for scrolling")

    def _find_next_heading_for_scroll(self):
        """Find the next heading for scrolling based on current view position"""
        if not self.heading_positions:
            return None
    
        # Get current cursor position for scroll reference
        cursor = self.text_edit.textCursor()
        current_block = cursor.blockNumber()
        current_position = cursor.positionInBlock()
    
        # Get all heading positions sorted by position
        positions = [(pos[0], pos[1], heading_id) for heading_id, pos in self.heading_positions.items()]
        positions.sort()  # Sort by (block_idx, sent_idx)
    
        # Find next heading after current cursor position
        for block_idx, sent_idx, heading_id in positions:
            if (block_idx > current_block or
                (block_idx == current_block and sent_idx > current_position)):
                return (block_idx, sent_idx)
    
        return None

    def _find_previous_heading_for_scroll(self):
        """Find the previous heading for scrolling based on current view position"""
        if not self.heading_positions:
            print("DEBUG: No heading positions available")
            return None

        # Get current cursor position in the document
        cursor = self.text_edit.textCursor()
        cursor_position = cursor.position()
        print(f"DEBUG: Current cursor position: {cursor_position}")

        # Convert cursor position to block/sentence coordinates
        current_block, current_sent = self._convert_cursor_position_to_block_sentence(cursor_position)
        if current_block is None:
            print("DEBUG: Could not convert cursor position")
            return None

        print(f"DEBUG: Current position: block {current_block}, sentence {current_sent}")

        # Get all heading positions sorted by position (reverse for previous)
        positions = [(pos[0], pos[1], heading_id) for heading_id, pos in self.heading_positions.items()]
        positions.sort(reverse=True)  # Sort in reverse order

        print(f"DEBUG: Available headings (reverse order): {positions}")

        # Find previous heading before current position
        for block_idx, sent_idx, heading_id in positions:
            print(f"DEBUG: Checking heading at block {block_idx}, sentence {sent_idx}")
            if (block_idx < current_block or
                (block_idx == current_block and sent_idx < current_sent)):
                print(f"DEBUG: Found previous heading at block {block_idx}, sentence {sent_idx}")
                return (block_idx, sent_idx)

        print("DEBUG: No previous heading found")
        return None

    def _scroll_to_position(self, block_idx, sent_idx):
        """Scroll the view to a specific block and sentence position without affecting TTS"""
        if not self.sentence_boundary_data or block_idx >= len(self.sentence_boundary_data):
            return
        
        block_data = self.sentence_boundary_data[block_idx]
        if sent_idx >= len(block_data['sentences']):
            return
        
        # Calculate the absolute position in the document
        absolute_position = 0
        
        # Add up all characters in previous blocks
        for i in range(block_idx):
            if i < len(self.sentence_boundary_data):
                block_text = '\n'.join(self.sentence_boundary_data[i]['sentences'])
                absolute_position += len(block_text) + 1  # +1 for newline between blocks
        
        # Add offset within the current block to reach the sentence
        if block_data['offsets'] and sent_idx < len(block_data['offsets']):
            sentence_start_offset = block_data['offsets'][sent_idx][0]
            absolute_position += sentence_start_offset
        
        # Create cursor and position it at the heading
        cursor = self.text_edit.textCursor()
        cursor.setPosition(absolute_position)
        self.text_edit.setTextCursor(cursor)
        
        # Ensure the cursor is visible (this scrolls the view)
        self.text_edit.ensureCursorVisible()
        
        print(f"DEBUG: Scrolled view to heading at block {block_idx}, sentence {sent_idx}")

    def navigate_to_previous_heading(self):
        """Navigate TTS to the previous markdown heading of any level"""
        print("DEBUG: navigate_to_previous_heading called")
        if not hasattr(self, 'tts_manager') or not self.tts_manager:
            print("DEBUG: No TTS manager available")
            return

        heading_position = self._find_previous_heading()
        print(f"DEBUG: Previous heading position: {heading_position}")
        if heading_position is not None:
            block_idx, sent_idx = heading_position
            if self.tts_manager.is_speaking:
                # If TTS is playing, jump to the heading
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
                self.tts_manager._navigate_to_sentence(block_idx, sent_idx)
            else:
                # If TTS is stopped, start from the heading
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
                self.tts_manager.toggle_speech()
        else:
            print("DEBUG: No previous heading found")

    def open_original_pdf(self):
        """Open the original PDF in a shared window or bring existing one to front, jumping to current sentence page"""
        # Get the original PDF path from parent editor
        original_pdf_path = None
        if hasattr(self.parent_editor, 'file_manager') and self.parent_editor.file_manager:
            original_pdf_path = self.parent_editor.file_manager.get_original_pdf_path()
    
        if not original_pdf_path:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Original PDF", "No original PDF file available")
            return
        
        # Get current sentence page number
        current_page = self.get_current_sentence_page_number()
        print(f"DEBUG: TTS Alt+O - jumping to page {current_page}")
    
        # Use shared PDF viewer window from parent editor or create new one
        if hasattr(self.parent_editor, 'pdf_viewer_window') and self.parent_editor.pdf_viewer_window:
            # Bring existing window to front and jump to page
            self.parent_editor.pdf_viewer_window.raise_()
            self.parent_editor.pdf_viewer_window.activateWindow()
            print(f"DEBUG: Calling go_to_page({current_page}) on existing window")
            self.parent_editor.pdf_viewer_window.go_to_page(current_page)
        else:
            # Create new PDF viewer window and share it
            from gui.components.pdf_handler import PDFViewerWindow
            self.parent_editor.pdf_viewer_window = PDFViewerWindow(original_pdf_path, self.parent_editor)
            self.parent_editor.pdf_viewer_window.show()
            
            # Use a timer to jump to the page after the PDF is loaded
            from PySide6.QtCore import QTimer
            def delayed_jump():
                print(f"DEBUG: Delayed calling go_to_page({current_page}) on new window")
                print(f"DEBUG: PDF viewer total_pages: {self.parent_editor.pdf_viewer_window.total_pages}")
                self.parent_editor.pdf_viewer_window.go_to_page(current_page)
            
            # Try immediately first
            self.parent_editor.pdf_viewer_window.go_to_page(current_page)
            # Then try again after 500ms delay to ensure PDF is loaded
            QTimer.singleShot(500, delayed_jump)
            # And one more try after 1 second if needed
            QTimer.singleShot(1000, delayed_jump)

    def navigate_to_next_heading_block(self):
        """Navigate TTS to the next heading block (Alt+PageDown)"""
        print("DEBUG: navigate_to_next_heading_block called")
        if not hasattr(self, 'tts_manager') or not self.tts_manager:
            print("DEBUG: No TTS manager available")
            return

        heading_position = self._find_next_heading()
        print(f"DEBUG: Next heading position: {heading_position}")
        if heading_position is not None:
            block_idx, sent_idx = heading_position
            # Scroll to make the sentence visible
            self._scroll_to_position(block_idx, sent_idx)
            if self.tts_manager.is_speaking:
                # If TTS is playing, jump to the heading
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
                self.tts_manager._navigate_to_sentence(block_idx, sent_idx)
            else:
                # If TTS is stopped, start from the heading
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
                self.tts_manager.toggle_speech()
        else:
            print("DEBUG: No next heading found")
    
    def navigate_to_previous_heading_block(self):
        """Navigate TTS to the previous heading block (Alt+PageUp)"""
        print("DEBUG: navigate_to_previous_heading_block called")
        if not hasattr(self, 'tts_manager') or not self.tts_manager:
            print("DEBUG: No TTS manager available")
            return
    
        heading_position = self._find_previous_heading()
        print(f"DEBUG: Previous heading position: {heading_position}")
        if heading_position is not None:
            block_idx, sent_idx = heading_position
            # Scroll to make the sentence visible
            self._scroll_to_position(block_idx, sent_idx)
            if self.tts_manager.is_speaking:
                # If TTS is playing, jump to the heading
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
                self.tts_manager._navigate_to_sentence(block_idx, sent_idx)
            else:
                # If TTS is stopped, start from the heading
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
                self.tts_manager.toggle_speech()
        else:
            print("DEBUG: No previous heading found")
    
    def navigate_to_next_horizontal_rule_section(self):
        """Navigate TTS to first element after next horizontal rule (Shift+Alt+PageDown)"""
        print("DEBUG: navigate_to_next_horizontal_rule_section called")
        if not hasattr(self, 'tts_manager') or not self.tts_manager:
            print("DEBUG: No TTS manager available")
            return
    
        next_section_position = self._find_first_element_after_next_horizontal_rule()
        print(f"DEBUG: Next section position: {next_section_position}")
        if next_section_position is not None:
            block_idx, sent_idx = next_section_position
            # Scroll to make the sentence visible
            self._scroll_to_position(block_idx, sent_idx)
            if self.tts_manager.is_speaking:
                # If TTS is playing, jump to the section
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
                self.tts_manager._navigate_to_sentence(block_idx, sent_idx)
            else:
                # If TTS is stopped, start from the section
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
                self.tts_manager.toggle_speech()
        else:
            print("DEBUG: No next horizontal rule section found")
    
    def navigate_to_previous_horizontal_rule_section(self):
        """Navigate TTS to first element after previous horizontal rule (Shift+Alt+PageUp)"""
        print("DEBUG: navigate_to_previous_horizontal_rule_section called")
        if not hasattr(self, 'tts_manager') or not self.tts_manager:
            print("DEBUG: No TTS manager available")
            return
    
        prev_section_position = self._find_first_element_after_previous_horizontal_rule()
        print(f"DEBUG: Previous section position: {prev_section_position}")
        if prev_section_position is not None:
            block_idx, sent_idx = prev_section_position
            # Scroll to make the sentence visible
            self._scroll_to_position(block_idx, sent_idx)
            if self.tts_manager.is_speaking:
                # If TTS is playing, jump to the section
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
                self.tts_manager._navigate_to_sentence(block_idx, sent_idx)
            else:
                # If TTS is stopped, start from the section
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
                self.tts_manager.toggle_speech()
        else:
            print("DEBUG: No previous horizontal rule section found")
    
    def _find_first_element_after_next_horizontal_rule(self):
        """Find the first element after the next PAGE BREAK block"""
        if not self.sentence_boundary_data:
            return None
    
        # Get current TTS position
        if hasattr(self, 'tts_manager') and self.tts_manager and hasattr(self.tts_manager, 'tts_sentence_index'):
            current_block, current_sent = self.tts_manager.tts_sentence_index
        else:
            # Fallback to cursor position
            cursor = self.text_edit.textCursor()
            cursor_position = cursor.position()
            current_position = self._convert_cursor_position_to_block_sentence(cursor_position)
            if current_position is None:
                return None
            current_block, current_sent = current_position
    
        print(f"DEBUG: Current position: block {current_block}, sentence {current_sent}")
    
        # Find PAGE BREAK blocks in the document
        page_break_blocks = []
        for block_idx, block_data in enumerate(self.sentence_boundary_data):
            if block_data['sentences']:
                for sent_idx, sentence in enumerate(block_data['sentences']):
                    sentence_text = sentence.strip()
                    # Check for PAGE BREAK pattern
                    if sentence_text.startswith('PAGE BREAK ') and sentence_text.split()[-1].isdigit():
                        page_break_blocks.append((block_idx, sent_idx))
                        print(f"DEBUG: Found PAGE BREAK at block {block_idx}, sentence {sent_idx}")
    
        if not page_break_blocks:
            print("DEBUG: No PAGE BREAK blocks found")
            return None
    
        # Find next PAGE BREAK after current position
        next_page_break = None
        for block_idx, sent_idx in page_break_blocks:
            if (block_idx > current_block or
                (block_idx == current_block and sent_idx > current_sent)):
                next_page_break = (block_idx, sent_idx)
                break
    
        if next_page_break is None:
            print("DEBUG: No PAGE BREAK found after current position")
            return None
    
        print(f"DEBUG: Next PAGE BREAK at block {next_page_break[0]}, sentence {next_page_break[1]}")
    
        # Find first element after the PAGE BREAK
        search_block, search_sent = next_page_break
    
        # Start searching from the sentence after the PAGE BREAK
        search_sent += 1
    
        # Search for first non-empty element
        while search_block < len(self.sentence_boundary_data):
            block_data = self.sentence_boundary_data[search_block]
    
            while search_sent < len(block_data['sentences']):
                sentence_text = block_data['sentences'][search_sent].strip()
                if sentence_text:  # Found non-empty sentence
                    print(f"DEBUG: First element after PAGE BREAK: block {search_block}, sentence {search_sent}")
                    return (search_block, search_sent)
                search_sent += 1
    
            # Move to next block
            search_block += 1
            search_sent = 0
    
        print("DEBUG: No element found after PAGE BREAK")
        return None
   
    def _find_first_element_after_previous_horizontal_rule(self):
        """Find the first element after the previous PAGE BREAK block"""
        if not self.sentence_boundary_data:
            return None
    
        # Get current TTS position
        if hasattr(self, 'tts_manager') and self.tts_manager and hasattr(self.tts_manager, 'tts_sentence_index'):
            current_block, current_sent = self.tts_manager.tts_sentence_index
        else:
            # Fallback to cursor position
            cursor = self.text_edit.textCursor()
            cursor_position = cursor.position()
            current_position = self._convert_cursor_position_to_block_sentence(cursor_position)
            if current_position is None:
                return None
            current_block, current_sent = current_position
    
        print(f"DEBUG: Current position: block {current_block}, sentence {current_sent}")
    
        # Find PAGE BREAK blocks in the document
        page_break_blocks = []
        for block_idx, block_data in enumerate(self.sentence_boundary_data):
            if block_data['sentences']:
                for sent_idx, sentence in enumerate(block_data['sentences']):
                    sentence_text = sentence.strip()
                    # Check for PAGE BREAK pattern
                    if sentence_text.startswith('PAGE BREAK ') and sentence_text.split()[-1].isdigit():
                        page_break_blocks.append((block_idx, sent_idx))
                        print(f"DEBUG: Found PAGE BREAK at block {block_idx}, sentence {sent_idx}")
    
        if not page_break_blocks:
            print("DEBUG: No PAGE BREAK blocks found - jumping to document start")
            # No horizontal rules exist, go to first sentence of document
            for block_idx, block_data in enumerate(self.sentence_boundary_data):
                if block_data['sentences']:
                    for sent_idx, sentence in enumerate(block_data['sentences']):
                        sentence_text = sentence.strip()
                        if sentence_text:  # Found first non-empty sentence
                            print(f"DEBUG: First sentence in document: block {block_idx}, sentence {sent_idx}")
                            return (block_idx, sent_idx)
            return None
    
        # Find the current "page" (section between PAGE BREAKs)
        current_page_start = None
        current_page_end = None
        
        # Find which page we're currently in
        for i, (block_idx, sent_idx) in enumerate(page_break_blocks):
            if (current_block < block_idx or 
                (current_block == block_idx and current_sent <= sent_idx)):
                # Current position is before this PAGE BREAK
                current_page_end = (block_idx, sent_idx)
                current_page_start = page_break_blocks[i-1] if i > 0 else None
                break
        
        # If we didn't find a page end, we're in the last page
        if current_page_end is None:
            current_page_start = page_break_blocks[-1] if page_break_blocks else None
        
        print(f"DEBUG: Current page start: {current_page_start}, end: {current_page_end}")
        
        # Find first sentence of current page
        if current_page_start is None:
            # We're in the first page (before first PAGE BREAK)
            search_block, search_sent = 0, 0
        else:
            # Start searching after the PAGE BREAK that starts this page
            search_block, search_sent = current_page_start
            search_sent += 1  # Move past the PAGE BREAK sentence
        
        current_page_first_sentence = None
        while search_block < len(self.sentence_boundary_data):
            if current_page_end and (search_block > current_page_end[0] or 
                                    (search_block == current_page_end[0] and search_sent >= current_page_end[1])):
                break
                
            block_data = self.sentence_boundary_data[search_block]
            while search_sent < len(block_data['sentences']):
                if current_page_end and search_block == current_page_end[0] and search_sent >= current_page_end[1]:
                    break
                    
                sentence_text = block_data['sentences'][search_sent].strip()
                if sentence_text and not (sentence_text.startswith('PAGE BREAK ') and sentence_text.split()[-1].isdigit()):
                    current_page_first_sentence = (search_block, search_sent)
                    break
                search_sent += 1
            
            if current_page_first_sentence:
                break
            search_block += 1
            search_sent = 0
        
        print(f"DEBUG: Current page first sentence: {current_page_first_sentence}")
        
        # Check if we're already at the first sentence of current page
        if (current_page_first_sentence and 
            current_block == current_page_first_sentence[0] and 
            current_sent == current_page_first_sentence[1]):
            print("DEBUG: Already at first sentence of current page, finding previous page")
            
            # Find previous page
            if current_page_start is None:
                # We're in first page, no previous page
                print("DEBUG: Already in first page, no previous page")
                return current_page_first_sentence  # Stay at first sentence
            else:
                # Find the PAGE BREAK before current_page_start
                prev_page_start = None
                for i, (block_idx, sent_idx) in enumerate(page_break_blocks):
                    if (block_idx, sent_idx) == current_page_start:
                        prev_page_start = page_break_blocks[i-1] if i > 0 else None
                        break
                
                print(f"DEBUG: Previous page start: {prev_page_start}")
                
                # Find first sentence of previous page
                if prev_page_start is None:
                    # Previous page is the very first page
                    search_block, search_sent = 0, 0
                else:
                    search_block, search_sent = prev_page_start
                    search_sent += 1  # Move past the PAGE BREAK
                
                while search_block < len(self.sentence_boundary_data):
                    if (current_page_start and 
                        (search_block > current_page_start[0] or 
                         (search_block == current_page_start[0] and search_sent >= current_page_start[1]))):
                        break
                        
                    block_data = self.sentence_boundary_data[search_block]
                    while search_sent < len(block_data['sentences']):
                        if (current_page_start and 
                            search_block == current_page_start[0] and search_sent >= current_page_start[1]):
                            break
                            
                        sentence_text = block_data['sentences'][search_sent].strip()
                        if sentence_text and not (sentence_text.startswith('PAGE BREAK ') and sentence_text.split()[-1].isdigit()):
                            print(f"DEBUG: First sentence of previous page: block {search_block}, sentence {search_sent}")
                            return (search_block, search_sent)
                        search_sent += 1
                    
                    search_block += 1
                    search_sent = 0
                
                print("DEBUG: No content found in previous page")
                return None
        else:
            # Not at first sentence of current page, go to current page first sentence
            print(f"DEBUG: Going to current page first sentence: {current_page_first_sentence}")
            return current_page_first_sentence

    def get_current_sentence_page_number(self):
        """Get the page number of the current sentence being read"""
        if not self.sentence_boundary_data:
            return 1
        
        # Get current TTS position
        if hasattr(self, 'tts_manager') and self.tts_manager and hasattr(self.tts_manager, 'tts_sentence_index'):
            current_block, current_sent = self.tts_manager.tts_sentence_index
        else:
            # Fallback to cursor position
            cursor = self.text_edit.textCursor()
            cursor_position = cursor.position()
            current_position = self._convert_cursor_position_to_block_sentence(cursor_position)
            if current_position is None:
                return 1
            current_block, current_sent = current_position
        
        print(f"DEBUG: Current TTS position: block {current_block}, sentence {current_sent}")
        
        # Find PAGE BREAK blocks in the document
        page_break_blocks = []
        for block_idx, block_data in enumerate(self.sentence_boundary_data):
            if block_data['sentences']:
                for sent_idx, sentence in enumerate(block_data['sentences']):
                    sentence_text = sentence.strip()
                    # Check for PAGE BREAK pattern
                    if sentence_text.startswith('PAGE BREAK ') and sentence_text.split()[-1].isdigit():
                        page_break_blocks.append((block_idx, sent_idx))
                        print(f"DEBUG: Found PAGE BREAK at block {block_idx}, sentence {sent_idx}")
        
        if not page_break_blocks:
            # No page breaks exist, everything is page 1
            return 1
        
        # Count how many PAGE BREAK blocks are before the current sentence position
        page_breaks_before_current = 0
        for block_idx, sent_idx in page_break_blocks:
            if (block_idx < current_block or 
                (block_idx == current_block and sent_idx < current_sent)):
                page_breaks_before_current += 1
            else:
                break
        
        # Page number is the number of page breaks before current position + 1
        page_number = page_breaks_before_current + 1
        
        print(f"DEBUG: {page_breaks_before_current} page breaks before current position, page number: {page_number}")
        return page_number

    def show_go_to_page_dialog(self):
        """Show go to page dialog for TTS widget"""
        if not self.sentence_boundary_data:
            print("DEBUG: No sentence boundary data available")
            return
    
        # Count total pages
        total_pages = self.get_total_page_count()
        current_page = self.get_current_sentence_page_number()
    
        if total_pages <= 0:
            print("DEBUG: No pages found")
            return
    
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
    
        dialog = QDialog(self)
        dialog.setWindowTitle("Go to Page")
        dialog.setModal(True)
        dialog.resize(300, 120)
    
        layout = QVBoxLayout(dialog)
    
        # Instructions
        instruction_label = QLabel(f"Enter page number (1-{total_pages}):")
        layout.addWidget(instruction_label)
    
        # Page input
        input_layout = QHBoxLayout()
        page_input = QLineEdit()
        page_input.setText(str(current_page))
        page_input.selectAll()
        input_layout.addWidget(QLabel("Page:"))
        input_layout.addWidget(page_input)
        layout.addLayout(input_layout)
    
        # Buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
    
        ok_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
    
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
    
        ok_button.setDefault(True)
        page_input.returnPressed.connect(dialog.accept)
        page_input.setFocus()
    
        if dialog.exec() == QDialog.Accepted:
            try:
                page_number = int(page_input.text().strip())
                if 1 <= page_number <= total_pages:
                    self.jump_to_page_and_start(page_number)
            except ValueError:
                pass
    
    def get_total_page_count(self):
        """Get total number of pages in the document"""
        if not self.sentence_boundary_data:
            return 0
    
        page_breaks = 0
        for block_idx, block_data in enumerate(self.sentence_boundary_data):
            if block_data['sentences']:
                for sent_idx, sentence in enumerate(block_data['sentences']):
                    sentence_text = sentence.strip()
                    if sentence_text.startswith('PAGE BREAK ') and sentence_text.split()[-1].isdigit():
                        page_breaks += 1
    
        # If no page breaks, assume 1 page
        return max(1, page_breaks + 1)
    
    def jump_to_page_and_start(self, page_number):
        """Jump to specific page and start TTS from first sentence of that page"""
        if not self.sentence_boundary_data:
            return
    
        first_sentence_of_page = self._find_first_sentence_of_page(page_number)
        if first_sentence_of_page is not None:
            block_idx, sent_idx = first_sentence_of_page
            print(f"DEBUG: Jumping to page {page_number}, block {block_idx}, sentence {sent_idx}")
    
            # Set TTS position and navigate
            if hasattr(self, 'tts_manager') and self.tts_manager:
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
                self._scroll_to_position(block_idx, sent_idx)
    
                # Start TTS if not already speaking
                if not self.tts_manager.is_speaking:
                    self.tts_manager.toggle_speech()
                else:
                    self.tts_manager._navigate_to_sentence(block_idx, sent_idx)
    
    def _find_first_sentence_of_page(self, page_number):
        """Find the first sentence of a specific page"""
        if not self.sentence_boundary_data or page_number < 1:
            return None
    
        # Find PAGE BREAK blocks
        page_break_blocks = []
        for block_idx, block_data in enumerate(self.sentence_boundary_data):
            if block_data['sentences']:
                for sent_idx, sentence in enumerate(block_data['sentences']):
                    sentence_text = sentence.strip()
                    if sentence_text.startswith('PAGE BREAK ') and sentence_text.split()[-1].isdigit():
                        page_break_blocks.append((block_idx, sent_idx))
    
        if page_number == 1:
            # First page - find first non-empty sentence
            for block_idx, block_data in enumerate(self.sentence_boundary_data):
                if block_data['sentences']:
                    for sent_idx, sentence in enumerate(block_data['sentences']):
                        sentence_text = sentence.strip()
                        if sentence_text and not sentence_text.startswith('PAGE BREAK '):
                            return (block_idx, sent_idx)
            return None
    
        # For pages > 1, find the appropriate page break
        if page_number - 2 >= len(page_break_blocks):
            return None
    
        # Start searching after the (page_number - 2)th page break
        search_block, search_sent = page_break_blocks[page_number - 2]
        search_sent += 1  # Start after the page break
    
        # Find first non-empty sentence
        while search_block < len(self.sentence_boundary_data):
            block_data = self.sentence_boundary_data[search_block]
    
            while search_sent < len(block_data['sentences']):
                sentence_text = block_data['sentences'][search_sent].strip()
                if sentence_text and not sentence_text.startswith('PAGE BREAK '):
                    return (search_block, search_sent)
                search_sent += 1
    
            search_block += 1
            search_sent = 0
    
        return None

    def start_tts_from_cursor_position(self, cursor_position):
        """Start TTS from a specific cursor position in the document"""
        if hasattr(self, 'tts_manager') and self.text_edit.document() and not self.text_edit.document().isEmpty():
            # Set cursor to the specified position
            cursor = self.text_edit.textCursor()
            cursor.setPosition(min(cursor_position, self.text_edit.document().characterCount() - 1))
            self.text_edit.setTextCursor(cursor)
            self.text_edit.ensureCursorVisible()
            
            print(f"DEBUG: Starting TTS from cursor position {cursor_position}")
            
            # Convert cursor position to block/sentence coordinates
            block_idx, sent_idx = self._convert_cursor_position_to_block_sentence(cursor_position)
            if block_idx is not None and sent_idx is not None:
                print(f"DEBUG: Converted to block {block_idx}, sentence {sent_idx}")
                # Set the TTS manager to start from this position
                self.tts_manager.set_sentence_index(block_idx, sent_idx)
            else:
                print("DEBUG: Could not convert cursor position, using default (0,0)")
                self.tts_manager.reset_sentence_index()
            
            # Start TTS from the set position
            if not self.tts_manager.is_speaking:
                self.tts_manager.toggle_speech()
                # Update button text
                if self.tts_manager.is_speaking:
                    self.play_pause_button.setText("Pause (Alt+S)")
                else:
                    self.play_pause_button.setText("Play (Alt+S)")

    def jump_to_cursor_position_and_start(self, cursor_position):
        """Jump to cursor position and start/restart TTS from there"""
        print(f"DEBUG: jump_to_cursor_position_and_start called with position {cursor_position}")
        
        # Set cursor to the specified position
        cursor = self.text_edit.textCursor()
        cursor.setPosition(min(cursor_position, self.text_edit.document().characterCount() - 1))
        self.text_edit.setTextCursor(cursor)
        self.text_edit.ensureCursorVisible()
        
        # Convert cursor position to block/sentence coordinates
        block_idx, sent_idx = self._convert_cursor_position_to_block_sentence(cursor_position)
        if block_idx is not None and sent_idx is not None:
            print(f"DEBUG: Converted to block {block_idx}, sentence {sent_idx}")
            # Set the TTS manager to the new position
            self.tts_manager.set_sentence_index(block_idx, sent_idx)
        else:
            print("DEBUG: Could not convert cursor position, using default (0,0)")
            self.tts_manager.reset_sentence_index()
        
        # If TTS is already running, stop it and restart from new position
        if hasattr(self, 'tts_manager'):
            if self.tts_manager.is_speaking:
                # Stop current TTS
                self.tts_manager.stop_speech()
                
            # Start TTS from new position
            self.tts_manager.toggle_speech()
            
            # Update button text
            if self.tts_manager.is_speaking:
                self.play_pause_button.setText("Pause (Alt+S)")
            else:
                self.play_pause_button.setText("Play (Alt+S)")
