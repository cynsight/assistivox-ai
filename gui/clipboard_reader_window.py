# gui/clipboard_reader_window.py
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut

from gui.components.readonly_tts_widget import ReadOnlyTTSWidget
from gui.components.markdown_handler import MarkdownHandler

class ClipboardReaderWindow(ReadOnlyTTSWidget):
    """
    Clipboard reader window that inherits from ReadOnlyTTSWidget
    
    This provides the same interface and navigation as the TTS widget
    but loads content from the clipboard instead of from a text editor.
    """
    
    def __init__(self, config=None, assistivox_dir=None, main_window=None, parent=None):
        # Initialize the parent ReadOnlyTTSWidget
        super().__init__(parent, config, assistivox_dir)
        
        # Store reference to main window
        self.main_window = main_window
        
        # Override window properties for clipboard reader
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle("Clipboard Reader")
        
        # Override the header text - find the header label and update it
        from PySide6.QtWidgets import QLabel
        header_labels = self.findChildren(QLabel)
        for label in header_labels:
            if "Text-to-Speech Reader" in label.text():
                label.setText("Clipboard Reader (Ctrl+Alt+V)")
                break
        
        # Remove shortcuts we don't want for clipboard reader
        self.remove_unwanted_shortcuts()
        
        # Load clipboard content when window is created
        self.load_clipboard_content()

    def remove_unwanted_shortcuts(self):
        """Remove shortcuts that don't apply to clipboard reader"""
        # Remove Alt+O (open original PDF) shortcut
        if hasattr(self, 'original_pdf_shortcut'):
            self.original_pdf_shortcut.setEnabled(False)
        
        # Remove Alt+G (go to page) shortcut
        if hasattr(self, 'go_to_page_shortcut'):
            self.go_to_page_shortcut.setEnabled(False)
        
        # Remove page navigation shortcuts (Shift+Ctrl+PgUp/PgDown)
        # These are handled in keyPressEvent, so we'll override that method
    
    def load_clipboard_content(self):
        """Load content from clipboard and render as markdown"""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        
        if text:
            # Parse markdown structure FIRST
            self.markdown_structure = self._parse_markdown_to_structure(text)
            
            # Use MarkdownHandler to convert the text to rich text
            MarkdownHandler.markdown_to_rich_text(self.text_edit.document(), text)
            
            # Run sentence boundary detection to get sentence_boundary_data
            try:
                from gui.nlp.sentence_detector import SentenceDetector
                import os
                
                config_path = os.path.join(self.assistivox_dir, "config.json")
                detector = SentenceDetector(config_path)
                self.sentence_boundary_data = detector.detect_sentences_in_document(self.text_edit.document())
                
                # NOW map headings to positions (this was missing!)
                self._map_headings_to_positions()
                
            except Exception as e:
                print(f"DEBUG: Error in sentence detection: {e}")
                self.sentence_boundary_data = []
                self.heading_positions = {}
            
            # Reset TTS sentence index when loading new clipboard content
            if self.tts_manager:
                self.tts_manager.reset_sentence_index()
        else:
            # Clear the editor if clipboard is empty
            self.text_edit.clear()
            # Clear navigation data
            self.heading_positions = {}
            self.markdown_structure = []
            self.sentence_boundary_data = None

    def changeEvent(self, event):
        """Handle window state changes"""
        if event.type() == event.Type.ActivationChange:
            if self.isActiveWindow():
                print("DEBUG: Clipboard reader window activated")
                # Re-sync TTS state when window regains focus
                if hasattr(self, 'tts_manager') and self.tts_manager:
                    if (self.tts_manager.tts_worker and 
                        self.tts_manager.tts_worker.isRunning()):
                        # Worker is running, ensure UI reflects this
                        if not self.tts_manager.is_speaking:
                            print("DEBUG: Worker running but is_speaking False - correcting")
                            self.tts_manager.is_speaking = True
                        if hasattr(self, 'play_pause_button'):
                            self.play_pause_button.setText("Pause (Alt+S)")
                    else:
                        # No worker running, ensure UI reflects this
                        if self.tts_manager.is_speaking:
                            print("DEBUG: No worker but is_speaking True - correcting")
                            self.tts_manager.is_speaking = False
                        if hasattr(self, 'play_pause_button'):
                            self.play_pause_button.setText("Play (Alt+S)")
        
        super().changeEvent(event)

    def focusInEvent(self, event):
        """Handle focus in events"""
        print("DEBUG: Clipboard reader focus in")
        # Ensure TTS state consistency when focus returns
        if hasattr(self, 'tts_manager') and self.tts_manager:
            if (self.tts_manager.tts_worker and
                self.tts_manager.tts_worker.isRunning() and
                not self.tts_manager.is_speaking):
                print("DEBUG: Correcting TTS speaking flag on focus in")
                self.tts_manager.is_speaking = True
                if hasattr(self, 'play_pause_button'):
                    self.play_pause_button.setText("Pause (Alt+S)")
    
        super().focusInEvent(event)
    
    def focusOutEvent(self, event):
        """Handle focus out events"""
        print("DEBUG: Clipboard reader focus out")
        super().focusOutEvent(event)
    
    def showEvent(self, event):
        """Override show event to load clipboard contents and auto-start TTS"""
        super().showEvent(event)
        self.load_clipboard_content()
        
        # Auto-start TTS from first sentence if content exists
        if self.text_edit.document() and not self.text_edit.document().isEmpty():
            # Set to first sentence of first block
            if self.tts_manager:
                self.tts_manager.set_sentence_index(0, 0)
                # Start TTS automatically
                self.tts_manager.toggle_speech()
                # Navigate to first sentence to make it visible
                self.tts_manager._navigate_to_sentence(0, 0)

    def open_original_pdf(self):
        """Override to disable PDF opening for clipboard reader"""
        # This method exists in parent but doesn't apply to clipboard reader
        pass
    
    def show_go_to_page_dialog(self):
        """Override to disable page navigation for clipboard reader"""
        # This method exists in parent but doesn't apply to clipboard reader
        pass
