# File: gui/components/text_editor_widget.py

import os
from pathlib import Path
import tempfile
from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QToolBar,
    QFontComboBox, QComboBox, QSpinBox, QFrame,
    QSizePolicy, QFileDialog, QMessageBox, QPushButton
)
from PySide6.QtGui import (
    QFont, QTextCharFormat, QColor, QTextListFormat, QTextCursor,
    QAction, QKeySequence, QIcon, QShortcut, QTextDocument
)
from PySide6.QtCore import Qt, Signal, QSize, QThread

from gui.components.text_editor_settings import EditorSettingsDialog
from gui.components.line_number_area import LineNumberArea
from gui.file_manager import FileManager
from gui.tts.tts_manager import TTSManager
from gui.dictation.dictation_manager import DictationManager
from gui.components.markdown_handler import MarkdownHandler
from gui.components.save_format_modal import SaveFormatModal
from gui.components.export_format_modal import ExportFormatModal

class FormattingTextEdit(QTextEdit):
    """
    Custom QTextEdit that maintains formatting when creating a new line
    and supports zooming
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.zoom_factor = 1.0  # Default zoom factor (100%)
        
    def keyPressEvent(self, event):
        """Enhanced keypress handling with blank line node creation"""
        # Check if the key pressed is Enter/Return
        if event.key() in (Qt.Key_Enter, Qt.Key_Return):
            # Store the current character format before inserting a new line
            cursor = self.textCursor()
            currentFormat = cursor.charFormat()
            
            # Get current cursor line for blank line insertion
            current_line = cursor.blockNumber() + 1  # Convert to 1-based
            
            # Let the text editor handle the key press normally (create new line)
            super().keyPressEvent(event)
            
            # Apply the stored format to the new position
            cursor = self.textCursor()
            cursor.setCharFormat(currentFormat)
            self.setTextCursor(cursor)
            
            # Notify parent widget that a blank line may have been created
            if hasattr(self.parent(), '_on_return_pressed'):
                self.parent()._on_return_pressed(current_line + 1)  # New line is at current + 1
                
        else:
            # For all other keys, use default behavior
            super().keyPressEvent(event)
    

    def wheelEvent(self, event):
        """Handle mouse wheel events for zooming when Ctrl is pressed"""
        # Check if Ctrl key is pressed
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
            # Pass the event to the parent for normal scrolling
            super().wheelEvent(event)

class TextEditorWidget(QWidget):
    """
    Rich text editor widget for Assistivox

    This component can be used standalone or embedded in other screens.
    It includes text formatting controls and dictation support.
    """
    # Signals
    textSaved = Signal(str, str)  # Emitted when text is saved (text, filename)
    dictationToggled = Signal(bool)  # Emitted when dictation is toggled
    zoomChanged = Signal(int)  # Emitted when zoom level changes

    def __init__(self, parent=None, initial_text="", config=None, assistivox_dir=None):
        super().__init__(parent)

        # Store references to config and paths
        self.config = config
        self.assistivox_dir = assistivox_dir

        # Editor state
        self.is_modified = False

        # Zoom level (100 = 100%, 150 = 150%, etc.)
        self.zoom_level = 100

        # Partial text tracking for dictation
        self.partial_text_start_pos = -1  # Track where partial text started
        self.partial_text_length = 0     # Track length of current partial text
        self.partial_text_max_length = 0     # Track maximum length of partial text seen
        # Editor settings
        self.editor_settings = self.load_editor_settings()

        # Set up UI first to create the text_edit widget
        self.setup_ui(initial_text)

        # Initialize file manager
        self.file_manager = FileManager(self.text_edit, config, assistivox_dir, self)
        self.file_manager.fileLoaded.connect(self.on_file_loaded)
        self.file_manager.fileSaved.connect(self.on_file_saved)

        # Initialize managers after UI is set up (so text_edit exists)
        # Initialize TTS manager
        self.tts_manager = TTSManager(self.text_edit, config, assistivox_dir)

        # Initialize dictation manager
        self.dictation_manager = DictationManager(self.text_edit, config, assistivox_dir)

        # Connect ALL dictation manager signals regardless of current engine
        # The dictation manager will emit the appropriate signals based on the engine
        self.dictation_manager.partialTextReceived.connect(self.insert_partial_text)
        self.dictation_manager.finalTextReceived.connect(self.insert_final_text)
        self.dictation_manager.textReceived.connect(self.insert_dictated_text)

        self.dictation_manager.dictationToggled.connect(self.dictationToggled)

        # Set up dictation in toolbar now that dictation_manager exists
        self.setup_dictation_toolbar()

        # Apply font settings from config if available
        if self.config and 'appearance' in self.config:
            appearance = self.config['appearance']
            if 'editor_font_size' in appearance:
                font = self.text_edit.font()
                font.setPointSize(appearance['editor_font_size'])
                self.text_edit.setFont(font)
                self.font_size_spinner.setValue(appearance['editor_font_size'])

        # Apply initial zoom level from settings
        if self.editor_settings and 'default_zoom' in self.editor_settings:
            self.zoom_level = self.editor_settings['default_zoom']
            self.apply_zoom()

        # Apply editor settings
        self.apply_editor_settings()

        # Add keyboard shortcuts - AFTER all initialization
        self.pdf_viewer_window = None
        self.add_shortcuts()

        # Reset TTS sentence index for new document
        self.tts_manager.reset_sentence_index()

        # Shared PDF viewer window
        self.pdf_viewer_window = None

    def load_editor_settings(self):
        """Load editor settings from config"""
        if not self.config or 'editor' not in self.config:
            # Default settings
            return {
                "show_toolbar": True,
                "show_line_numbers": False,
                "default_zoom": 100
            }

        # Get editor settings from config
        editor_settings = self.config.get('editor', {})

        # Apply defaults for any missing settings
        if "show_toolbar" not in editor_settings:
            editor_settings["show_toolbar"] = True
        if "show_line_numbers" not in editor_settings:
            editor_settings["show_line_numbers"] = False
        if "default_zoom" not in editor_settings:
            editor_settings["default_zoom"] = 100

        return editor_settings

    def save_editor_settings(self, settings):
        """Save editor settings to config"""
        if not self.config:
            return

        # Update settings
        self.editor_settings = settings

        # Ensure editor section exists
        if 'editor' not in self.config:
            self.config['editor'] = {}

        # Update config
        self.config['editor'].update(settings)

        # Save config
        with open(self.assistivox_dir / "config.json", 'w') as f:
            import json
            json.dump(self.config, f, indent=2)

        # Apply settings
        self.apply_editor_settings()

    def apply_editor_settings(self):
        """Apply editor settings to the UI"""
        # Show/hide toolbar
        if hasattr(self, 'toolbar'):
            self.toolbar.setVisible(self.editor_settings.get("show_toolbar", True))

        # Show/hide line numbers
        if hasattr(self, 'line_number_area'):
            self.line_number_area.setVisible(self.editor_settings.get("show_line_numbers", False))

    def setup_ui(self, initial_text):
        """Set up the user interface components"""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top section with toolbar
        top_section = QWidget()
        top_layout = QHBoxLayout(top_section)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        # Create toolbar
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(QSize(16, 16))
        top_layout.addWidget(self.toolbar, 1)  # Stretch factor 1

        # Add top section to main layout
        layout.addWidget(top_section)

        # Add separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # Editor layout (includes line numbers + text editor)
        editor_layout = QHBoxLayout()
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        # Create text editor with maintained formatting
        self.text_edit = FormattingTextEdit()
        self.text_edit.setPlainText(initial_text)
        self.text_edit.textChanged.connect(self.on_text_changed)
        self.text_edit.cursorPositionChanged.connect(self.update_line_numbers)
        self.text_edit.cursorPositionChanged.connect(self.on_cursor_position_changed)
        self.text_edit.selectionChanged.connect(self.on_selection_changed)

        # Create line number area
        self.line_number_area = LineNumberArea(self.text_edit)

        # Add components to editor layout
        editor_layout.addWidget(self.line_number_area)
        editor_layout.addWidget(self.text_edit)

        # Add editor layout to main layout
        layout.addLayout(editor_layout)

        # Add toolbar actions
        self.setup_toolbar()

    def setup_toolbar(self):
        """Set up the toolbar with formatting actions"""
        # File operations
        save_action = QAction("Save", self)
        save_action.triggered.connect(self.save_document)
        self.toolbar.addAction(save_action)
    
        save_as_action = QAction("Save As", self)
        save_as_action.triggered.connect(self.save_document_as)
        self.toolbar.addAction(save_as_action)
    
        self.toolbar.addSeparator()
    
        # Font family
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(self.text_edit.font())
        self.font_combo.currentFontChanged.connect(self.change_font_family)
        self.toolbar.addWidget(self.font_combo)
    
        # Font size
        self.font_size_spinner = QSpinBox()
        self.font_size_spinner.setRange(8, 72)
        self.font_size_spinner.setValue(self.text_edit.font().pointSize())
        self.font_size_spinner.valueChanged.connect(self.change_font_size)
        self.toolbar.addWidget(self.font_size_spinner)
    
        self.toolbar.addSeparator()
    
        # Bold, italic, underline
        bold_action = QAction("Bold", self)
        bold_action.setShortcut(QKeySequence.Bold)
        bold_action.setCheckable(True)
        bold_action.triggered.connect(self.toggle_bold)
        self.toolbar.addAction(bold_action)
    
        italic_action = QAction("Italic", self)
        italic_action.setShortcut(QKeySequence.Italic)
        italic_action.setCheckable(True)
        italic_action.triggered.connect(self.toggle_italic)
        self.toolbar.addAction(italic_action)
    
        underline_action = QAction("Underline", self)
        underline_action.setShortcut(QKeySequence.Underline)
        underline_action.setCheckable(True)
        underline_action.triggered.connect(self.toggle_underline)
        self.toolbar.addAction(underline_action)
    
        self.toolbar.addSeparator()
    
        # Alignment
        align_left_action = QAction("Align Left", self)
        align_left_action.triggered.connect(lambda: self.text_edit.setAlignment(Qt.AlignLeft))
        self.toolbar.addAction(align_left_action)
    
        align_center_action = QAction("Center", self)
        align_center_action.triggered.connect(lambda: self.text_edit.setAlignment(Qt.AlignCenter))
        self.toolbar.addAction(align_center_action)
    
        align_right_action = QAction("Align Right", self)
        align_right_action.triggered.connect(lambda: self.text_edit.setAlignment(Qt.AlignRight))
        self.toolbar.addAction(align_right_action)
    
        self.toolbar.addSeparator()
    
        # Lists
        bullet_list_action = QAction("Bullet List", self)
        bullet_list_action.triggered.connect(self.toggle_bullet_list)
        self.toolbar.addAction(bullet_list_action)
    
        numbered_list_action = QAction("Numbered List", self)
        numbered_list_action.triggered.connect(self.toggle_numbered_list)
        self.toolbar.addAction(numbered_list_action)
    
        # Note: Dictation button is added later in setup_dictation_toolbar

    def setup_dictation_toolbar(self):
        """Set up dictation-related toolbar items"""
        # Dictation button (only if available)
        if self.dictation_manager.is_available():
            self.toolbar.addSeparator()
            # Create action WITHOUT a shortcut
            dictation_action = QAction("Toggle Dictation", self)
            dictation_action.setCheckable(True)
            dictation_action.triggered.connect(self.toggle_dictation)
            self.toolbar.addAction(dictation_action)

            # Register the action with the dictation manager
            self.dictation_manager.register_dictation_action(dictation_action)

    def on_cursor_position_changed(self):
        """Update formatting controls based on current cursor position"""
        cursor = self.text_edit.textCursor()
        format = cursor.charFormat()

        # Update font family
        font = format.font()
        if font.family():
            self.font_combo.blockSignals(True)
            self.font_combo.setCurrentFont(font)
            self.font_combo.blockSignals(False)

        # Update font size
        size = format.fontPointSize()
        if size > 0:  # Valid font size
            self.font_size_spinner.blockSignals(True)
            self.font_size_spinner.setValue(int(size))
            self.font_size_spinner.blockSignals(False)

    def on_selection_changed(self):
        """Set cursor position to the start of selected text when selection changes"""
        # Skip repositioning during active dictation to avoid conflicts
        if (hasattr(self, 'dictation_manager') and self.dictation_manager and 
            self.dictation_manager.is_running()):
            return
            
        try:
            cursor = self.text_edit.textCursor()
            if not cursor.hasSelection():
                return
            
            # Get selection positions
            selection_start = cursor.selectionStart()
            selection_end = cursor.selectionEnd()
            
            # Validate positions are within document bounds
            document = cursor.document()
            if document is None:
                return
                
            max_position = document.characterCount() - 1
            if selection_start < 0 or selection_start > max_position:
                return
            if selection_end < 0 or selection_end > max_position:
                return
            
            # Only proceed if cursor is not already at selection start
            if cursor.position() == selection_start:
                return
            
            # Create a new cursor and set it to selection start
            new_cursor = QTextCursor(document)
            new_cursor.setPosition(selection_start)
            new_cursor.setPosition(selection_end, QTextCursor.KeepAnchor)
            
            # Temporarily disconnect the signal to avoid recursion
            self.text_edit.selectionChanged.disconnect(self.on_selection_changed)
            self.text_edit.setTextCursor(new_cursor)
            self.text_edit.selectionChanged.connect(self.on_selection_changed)
            
        except Exception as e:
            print(f"DEBUG: Error in on_selection_changed: {e}")
            # Reconnect signal if there was an error
            try:
                self.text_edit.selectionChanged.connect(self.on_selection_changed)
            except:
                pass

    def show_settings_dialog(self):
        """Show editor settings dialog"""
        from gui.components.text_editor_settings import EditorSettingsDialog
        dialog = EditorSettingsDialog(self.editor_settings, self)
        dialog.settingsChanged.connect(self.save_editor_settings)
        dialog.exec()

    def update_line_numbers(self):
        """Update line numbers when cursor position changes"""
        if hasattr(self, 'line_number_area'):
            self.line_number_area.update()

    def change_font_family(self, font):
        """Change the font family of selected text"""
        self.text_edit.setCurrentFont(font)

    def change_font_size(self, size):
        """Change the font size of selected text"""
        self.text_edit.setFontPointSize(size)

    def toggle_bold(self, checked):
        """Toggle bold formatting for selected text"""
        if checked:
            self.text_edit.setFontWeight(QFont.Bold)
        else:
            self.text_edit.setFontWeight(QFont.Normal)

    def toggle_italic(self, checked):
        """Toggle italic formatting for selected text"""
        self.text_edit.setFontItalic(checked)

    def toggle_underline(self, checked):
        """Toggle underline formatting for selected text"""
        self.text_edit.setFontUnderline(checked)

    def toggle_bullet_list(self):
        """Toggle bullet list at current position"""
        cursor = self.text_edit.textCursor()

        # Get the current list format or create a new one
        list_format = QTextListFormat()
        list_format.setStyle(QTextListFormat.ListDisc)

        # Toggle the list
        cursor.createList(list_format)

    def toggle_numbered_list(self):
        """Toggle numbered list at current position"""
        cursor = self.text_edit.textCursor()

        # Get the current list format or create a new one
        list_format = QTextListFormat()
        list_format.setStyle(QTextListFormat.ListDecimal)

        # Toggle the list
        cursor.createList(list_format)

    def toggle_dictation(self):
        """Toggle dictation on/off using the dictation manager"""
        if hasattr(self, 'dictation_manager') and self.dictation_manager:
            self.dictation_manager.toggle_dictation()

    def insert_dictated_text(self, text):
        """Insert text from dictation at cursor position"""
        if text.strip():
            # Apply sentence formatting if enabled
            formatted_text = self.apply_sentence_formatting(text.strip())
            self.text_edit.insertPlainText(formatted_text + " ")

    def on_text_changed(self):
        """Handle text changes with localized node updates"""
        self.is_modified = True
        self.update_line_numbers()
    
    def on_file_loaded(self, file_path, content_type):
        """Handle file loaded signal from file manager"""
        self.is_modified = False
        self.update_line_numbers()
    
        # Reset TTS sentence index when loading new document
        self.tts_manager.reset_sentence_index()
    
        # Apply zoom settings after loading the document
        if self.zoom_level != 100:
            self.apply_zoom()

    def _delayed_structure_sync(self):
        """Update document structure after file loading is complete"""
        print("DEBUG: File loaded, updating document structure")
        self.sync_document_structure_from_text()

    def on_file_saved(self, text_content, file_path):
        """Handle file saved signal from file manager"""
        self.is_modified = False
        self.textSaved.emit(text_content, file_path)

    def save_document(self):
        """Save the current document - goes directly to markdown save for Ctrl+S"""
        if self.file_manager.get_current_file_path():
            # File already has a path, use normal save
            return self.file_manager.save_document()
        else:
            # New file, go directly to file explorer with markdown assumption
            return self.save_as_markdown_directly()

    def save_document_as(self):
        """Save the document with a new filename using file manager"""
        return self.file_manager.save_document_as()

    def get_text(self):
        """Get the current text content"""
        return self.text_edit.toPlainText()

    def get_html(self):
        """Get the current HTML content"""
        return self.text_edit.toHtml()

    def set_text(self, text):
        """Set the text content"""
        self.text_edit.setPlainText(text)
        self.is_modified = False
        self.update_line_numbers()
        # Reset TTS sentence index when setting new text
        self.tts_manager.reset_sentence_index()
    
    def is_document_modified(self):
        """Check if the document has been modified"""
        return self.is_modified

    def add_shortcuts(self):
        """Add keyboard shortcuts for the text editor"""
        # Control+O for open
        self.open_shortcut = QShortcut(QKeySequence.Open, self)  # Ctrl+O
        self.open_shortcut.activated.connect(self.file_manager.open_file_dialog)

        # Alt+S for text-to-speech
        self.speech_shortcut = QShortcut(QKeySequence("Alt+S"), self)
        self.speech_shortcut.activated.connect(self.toggle_speech)

        # Alt+D for dictation (only register here, not on the toolbar action)
        if hasattr(self, 'dictation_manager') and self.dictation_manager and self.dictation_manager.is_available():
            self.dictation_shortcut = QShortcut(QKeySequence("Alt+D"), self)
            self.dictation_shortcut.activated.connect(self.toggle_dictation)

        # Zoom shortcuts
        self.zoom_in_shortcut = QShortcut(QKeySequence.ZoomIn, self)  # Ctrl++
        self.zoom_in_shortcut.activated.connect(self.zoom_in)

        self.zoom_out_shortcut = QShortcut(QKeySequence.ZoomOut, self)  # Ctrl+-
        self.zoom_out_shortcut.activated.connect(self.zoom_out)

        self.zoom_reset_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        self.zoom_reset_shortcut.activated.connect(self.zoom_reset)

        # Add shortcut for Alt+O to open original PDF
        self.original_pdf_shortcut = QShortcut(QKeySequence("Alt+O"), self)
        self.original_pdf_shortcut.activated.connect(self.open_original_pdf)

        # Alt+E for export
        self.export_shortcut = QShortcut(QKeySequence("Alt+E"), self)
        self.export_shortcut.activated.connect(self.show_export_format_modal)

        # Control+] for next semantic element
        self.next_element_shortcut = QShortcut(QKeySequence("Ctrl+]"), self)
        self.next_element_shortcut.activated.connect(self.navigate_to_next_element)

        # Control+[ for previous semantic element
        self.prev_element_shortcut = QShortcut(QKeySequence("Ctrl+["), self)
        self.prev_element_shortcut.activated.connect(self.navigate_to_previous_element)

        # Control+Page Down for next heading
        self.next_heading_shortcut = QShortcut(QKeySequence("Ctrl+PgDown"), self)
        self.next_heading_shortcut.activated.connect(self.navigate_to_next_heading)

        # Control+Page Up for previous heading
        self.prev_heading_shortcut = QShortcut(QKeySequence("Ctrl+PgUp"), self)
        self.prev_heading_shortcut.activated.connect(self.navigate_to_previous_heading)

        # Shift+Control+Page Down for next page
        horizontal_rule_next_shortcut = QShortcut(QKeySequence("Shift+Ctrl+PgDown"), self)
        horizontal_rule_next_shortcut.activated.connect(self.navigate_to_next_page)

        # Shift+Control+Page Up for previous page
        horizontal_rule_prev_shortcut = QShortcut(QKeySequence("Shift+Ctrl+PgUp"), self)
        horizontal_rule_prev_shortcut.activated.connect(self.navigate_to_previous_page)

        # Alt+G for go to page
        self.go_to_page_shortcut = QShortcut(QKeySequence("Alt+G"), self)
        self.go_to_page_shortcut.activated.connect(self.show_go_to_page_dialog)

    def navigate_to_next_sentence(self):
        """Navigate to next sentence during TTS"""
        print(f"DEBUG: Alt+] pressed. TTS manager exists: {hasattr(self, 'tts_manager') and self.tts_manager is not None}")
        if hasattr(self, 'tts_manager') and self.tts_manager:
            print(f"DEBUG: TTS is_speaking: {self.tts_manager.is_speaking}")
            if self.tts_manager.is_speaking:
                print("DEBUG: Calling navigate_to_next_sentence()")
                result = self.tts_manager.navigate_to_next_sentence()
                print(f"DEBUG: Navigate result: {result}")
            else:
                print("DEBUG: TTS not speaking, ignoring navigation")

    def navigate_to_previous_sentence(self):
        """Navigate to previous sentence during TTS"""
        print(f"DEBUG: Alt+[ pressed. TTS manager exists: {hasattr(self, 'tts_manager') and self.tts_manager is not None}")
        if hasattr(self, 'tts_manager') and self.tts_manager:
            print(f"DEBUG: TTS is_speaking: {self.tts_manager.is_speaking}")
            if self.tts_manager.is_speaking:
                print("DEBUG: Calling navigate_to_previous_sentence()")
                result = self.tts_manager.navigate_to_previous_sentence()
                print(f"DEBUG: Navigate result: {result}")
            else:
                print("DEBUG: TTS not speaking, ignoring navigation")

    def zoom_reset(self):
        """Reset zoom to the default level from settings"""
        default_zoom = self.editor_settings.get('default_zoom', 100)
        if self.zoom_level != default_zoom:
            self.zoom_level = default_zoom
            self.apply_zoom()
            self.zoomChanged.emit(self.zoom_level)

    def apply_zoom(self):
        """Apply the current zoom level to the text editor by scaling the base font"""
        # Get base font size from config
        base_font_size = 14  # Default fallback
        if self.config and 'appearance' in self.config:
            appearance = self.config['appearance']
            base_font_size = appearance.get('editor_font_size', 14)

        # Calculate new base font size according to zoom level
        new_base_size = base_font_size * (self.zoom_level / 100.0)

        # Store cursor position and scroll position
        cursor_position = self.text_edit.textCursor().position()
        scroll_position = self.text_edit.verticalScrollBar().value()

        # Set the base font for the text editor and document
        # This affects the default font size while preserving all rich text formatting
        font = self.text_edit.font()
        font.setPointSizeF(new_base_size)
        self.text_edit.setFont(font)

        # Set the default font for the document (affects display scaling)
        document = self.text_edit.document()
        document.setDefaultFont(font)

        # Restore cursor and scroll positions
        cursor = self.text_edit.textCursor()
        cursor.setPosition(min(cursor_position, document.characterCount() - 1))
        self.text_edit.setTextCursor(cursor)
        self.text_edit.verticalScrollBar().setValue(scroll_position)

        # Update UI elements
        if hasattr(self, 'line_number_area'):
            self.line_number_area.update_width()

        # Emit signal
        self.zoomChanged.emit(self.zoom_level)

    def zoom_in(self):
        """Increase the zoom level by 10%"""
        if self.zoom_level < 300:  # Max zoom level: 300%
            self.zoom_level += 10
            self.apply_zoom()

    def zoom_out(self):
        """Decrease the zoom level by 10%"""
        if self.zoom_level > 50:  # Min zoom level: 50%
            self.zoom_level -= 10
            self.apply_zoom()

    def wheelEvent(self, event):
        """Handle mouse wheel events for zooming when Ctrl is pressed"""
        # Check if Ctrl key is pressed
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            event.accept()
        else:
            # Pass the event to the parent for normal scrolling
            super().wheelEvent(event)

    def open_original_pdf(self):
        """Open the original PDF in a shared window or bring existing one to front, jumping to current page"""
        # Get current page number first
        current_page = self.get_current_page_number()
        print(f"DEBUG: Text editor Alt+O - jumping to page {current_page}")
        
        # Check if we already have a PDF viewer window open
        if self.pdf_viewer_window and not self.pdf_viewer_window.isHidden():
            # Bring existing window to front and jump to page
            self.pdf_viewer_window.raise_()
            self.pdf_viewer_window.activateWindow()
            print(f"DEBUG: Calling go_to_page({current_page}) on existing window")
            self.pdf_viewer_window.go_to_page(current_page)
        else:
            # Create new PDF viewer window using file manager
            self.pdf_viewer_window = self.file_manager.open_original_pdf()
            if self.pdf_viewer_window:
                # Use a timer to jump to the page after the PDF is loaded
                from PySide6.QtCore import QTimer
                def delayed_jump():
                    print(f"DEBUG: Delayed calling go_to_page({current_page}) on new window")
                    print(f"DEBUG: PDF viewer total_pages: {self.pdf_viewer_window.total_pages}")
                    self.pdf_viewer_window.go_to_page(current_page)
                
                # Try immediately first
                self.pdf_viewer_window.go_to_page(current_page)
                # Then try again after 500ms delay to ensure PDF is loaded
                QTimer.singleShot(500, delayed_jump)
                # And one more try after 1 second if needed
                QTimer.singleShot(1000, delayed_jump)

    def cleanup_audio_resources(self):
        """Clean up audio resources when widget is being closed"""
        # Stop TTS if active
        if hasattr(self, 'tts_manager'):
            self.tts_manager.cleanup_resources()

        # Stop dictation if active
        if hasattr(self, 'dictation_manager'):
            self.dictation_manager.cleanup_resources()

    def toggle_speech(self):
        """Toggle text-to-speech on/off by opening read-only TTS window from current block"""
        # Import here to avoid circular imports
        from gui.components.readonly_tts_widget import ReadOnlyTTSWidget
    
        # Check if document has content
        document = self.text_edit.document()
        if document.isEmpty():
            return  # Nothing to speak
    
        # Get current cursor position and block
        cursor = self.text_edit.textCursor()
        current_block_number = cursor.blockNumber()
        current_block = cursor.block()
        
        # Get a position that's clearly inside the current block (not at the boundary)
        # Use position + 1 to ensure we're inside the block, not at the boundary
        block_start_position = current_block.position()
        if current_block.text().strip():  # If block has content
            block_start_position += 1  # Move 1 character into the block to avoid boundary issues
        
        print(f"DEBUG: Alt+S pressed - cursor at block {current_block_number}, block start position {block_start_position}")
    
        # Check if TTS window already exists and is visible
        if hasattr(self, 'tts_window') and self.tts_window and not self.tts_window.isHidden():
            # TTS window exists and is visible, bring it to front and jump to current block
            print("DEBUG: TTS window exists, bringing to front and jumping to block")
            self.tts_window.raise_()
            self.tts_window.activateWindow()
            self.tts_window.jump_to_cursor_position_and_start(block_start_position)
        else:
            # Create new TTS window
            print("DEBUG: Creating new TTS window")
            self.tts_window = ReadOnlyTTSWidget(
                parent=self,
                config=self.config,
                assistivox_dir=self.assistivox_dir
            )
    
            # Get markdown content from the document
            from gui.components.markdown_handler import MarkdownHandler
            markdown_content = MarkdownHandler.rich_text_to_markdown(document)
            
            # Set the document content in the TTS widget
            self.tts_window.set_document_content(markdown_content)
            
            # Show the window
            self.tts_window.show()
            
            # Start TTS from the current block
            self.tts_window.start_tts_from_cursor_position(block_start_position)

    def show_voice_settings(self):
        """Show the voice settings dialog"""
        # Only show if we have config and assistivox_dir
        if not self.config or not self.assistivox_dir:
            return

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
        if self.assistivox_dir:
            config_path = os.path.join(self.assistivox_dir, "config.json")
            try:
                with open(config_path, 'r') as f:
                    import json
                    self.config = json.load(f)
            except Exception as e:
                print(f"Error reloading config: {e}")

        # Update dictation configuration if needed
        if hasattr(self, 'dictation_manager') and self.dictation_manager:
            if hasattr(self.dictation_manager, 'dictation') and self.dictation_manager.dictation:
                self.dictation_manager.dictation.config = self.dictation_manager.dictation._load_config()

    def insert_partial_text(self, text):
        """Insert partial text from dictation in gray color while user is speaking"""
        cursor = self.text_edit.textCursor()

        # If there's an active selection, clear it and start dictation from that position
        if cursor.hasSelection():
            # Clear any existing partial text tracking first
            self.partial_text_start_pos = -1
            self.partial_text_length = 0
            self.partial_text_max_length = 0

            # Remove the selected text and start fresh
            cursor.removeSelectedText()
            self.partial_text_start_pos = cursor.position()
            self.text_edit.setTextCursor(cursor)
        elif self.partial_text_start_pos >= 0 and self.partial_text_length > 0:
            # If we have existing partial text, remove it first
            cursor.setPosition(self.partial_text_start_pos)
            cursor.setPosition(self.partial_text_start_pos + self.partial_text_length, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            # Reset cursor position to where partial text started
            cursor.setPosition(self.partial_text_start_pos)
            self.text_edit.setTextCursor(cursor)
        else:
            # First partial text - remember starting position
            self.partial_text_start_pos = cursor.position()

        # Insert new partial text in gray color if enabled
        if text.strip():  # Only insert if there's actual text
            # Check if partial text display is enabled
            show_partial = True
            if (self.config and
                "vosk_settings" in self.config):
                show_partial = self.config["vosk_settings"].get("show_partial_text", False)

            if show_partial:
                # Save current format
                original_format = cursor.charFormat()

                # Create gray format for partial text
                gray_format = QTextCharFormat(original_format)
                gray_format.setForeground(QColor(128, 128, 128))  # Gray color

                # Insert partial text with gray formatting
                cursor.insertText(text, gray_format)

                # Update partial text tracking
                self.partial_text_length = len(text)
                self.partial_text_max_length = max(self.partial_text_max_length, len(text))

                # Move cursor to end of partial text
                cursor.setPosition(self.partial_text_start_pos + self.partial_text_length)
                self.text_edit.setTextCursor(cursor)
            else:
                # Don't show partial text and don't track positions since no text is inserted
                # Keep tracking variables at their default values
                pass

    def insert_final_text(self, text):
        """Insert final text from dictation, replacing any partial text"""
        cursor = self.text_edit.textCursor()

        # Remove the last partial transcription before inserting the final text
        cursor.setPosition(self.partial_text_start_pos)
        cursor.setPosition(self.partial_text_start_pos + self.partial_text_length, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()


        # Remove any existing partial text
        if self.partial_text_start_pos >= 0 and self.partial_text_max_length > 0:
            # Select the entire partial text region
            cursor.setPosition(self.partial_text_start_pos)
            cursor.setPosition(self.partial_text_start_pos + self.partial_text_max_length, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            # Reset cursor to start of where partial text was
            cursor.setPosition(self.partial_text_start_pos)
            self.text_edit.setTextCursor(cursor)

        if text.strip():
            # Apply sentence formatting if enabled
            formatted_text = self.apply_sentence_formatting(text.strip())

            # Insert the formatted text with default formatting
            default_format = QTextCharFormat()
            cursor.insertText(formatted_text + " ", default_format)

            # Move cursor to end of inserted text
            cursor.setPosition(self.partial_text_start_pos + len(formatted_text + " "))
            self.text_edit.setTextCursor(cursor)

        # Reset tracking
        self.partial_text_start_pos = -1
        self.partial_text_length = 0
        self.partial_text_max_length = 0

    def apply_sentence_formatting(self, text):
        """Apply automatic sentence formatting if enabled in Vosk settings"""
        # Check if auto sentence formatting is enabled
        if (self.config and
            "vosk_settings" in self.config and
            self.config["vosk_settings"].get("auto_sentence_format", True)):

            # First apply punctuation translation from cmd_transcribe.json
            text = self.apply_punctuation_translation(text)

            # Then apply sentence formatting
            # Capitalize first letter if it's a letter
            if text and text[0].isalpha():
                text = text[0].upper() + text[1:]

            # Add period if it doesn't end with punctuation, unless the last punctuation has no_period feature
            if text and text[-1] not in '.!?':
                # Check if we should skip adding period due to no_period feature
                should_add_period = True

                # Check if we have tracked no_period punctuation from apply_punctuation_translation
                if hasattr(self, '_no_period_punctuation'):
                    # Check if text ends with any no_period punctuation
                    for punct in self._no_period_punctuation:
                        if text.endswith(punct):
                            should_add_period = False
                            break

                if should_add_period:
                    text = text + '.'

        return text

    def apply_punctuation_translation(self, text):
        """Translate spoken punctuation to actual punctuation using cmd_transcribe.json with features"""
        import json
        import os
        import re

        # Get the project root directory
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        # Path to the punctuation translation file
        json_path = os.path.join(project_root, "transcribe", "cmd_transcribe.json")

        try:
            # Load the punctuation translation table
            with open(json_path, 'r') as f:
                punctuation_map = json.load(f)

            # Keep track of which substitutions have "no_period" feature for later use
            no_period_punctuation = set()

            # Apply punctuation translations with features
            for spoken, config in punctuation_map.items():
                # Handle both old format (string) and new format (object)
                if isinstance(config, str):
                    # Old format - just do simple replacement
                    actual = config
                    features = []
                else:
                    # New format with features
                    actual = config.get("to", "")
                    features = config.get("features", [])

                    # Track punctuation that should not have period added
                    if "no_period" in features:
                        no_period_punctuation.add(actual)

                # Create a regex pattern that matches the spoken punctuation as a whole word
                pattern = r'\b' + re.escape(spoken) + r'\b *'

                # Apply the replacement
                if "no_space_before" in features:
                    # Special handling for no_space_before: remove any space before AND after the pattern
                    pattern_with_space = r' *\b' + re.escape(spoken) + r'\b *'
                    # Use a lambda function to avoid regex escape issues
                    text = re.sub(pattern_with_space, lambda m: actual, text, flags=re.IGNORECASE)
                else:
                    # Normal replacement - use lambda to avoid regex escape issues
                    text = re.sub(pattern, lambda m: actual, text, flags=re.IGNORECASE)

            # Handle cap_next feature in a second pass
            # We need to track which exact punctuation instances should have cap_next applied
            # by marking them during the first pass and only applying cap_next to those marked instances

            cap_next_punctuation = {}  # Map actual punctuation to whether it should cap_next

            for spoken, config in punctuation_map.items():
                if isinstance(config, dict):
                    actual = config.get("to", "")
                    features = config.get("features", [])

                    if "cap_next" in features:
                        # Store this punctuation for cap_next processing
                        # Use the full actual string (including any trailing space)
                        cap_next_punctuation[actual] = True

            # Apply cap_next only to punctuation that explicitly has this feature
            for punct_with_space, should_cap in cap_next_punctuation.items():
                if should_cap:
                    # Pattern: exact punctuation string + letter (no optional whitespace since
                    # the punctuation already includes its required spacing)
                    punct_pattern = re.escape(punct_with_space)
                    pattern = punct_pattern + r'([a-zA-Z])'

                    def cap_replacement(match):
                        return punct_with_space + match.group(1).upper()
        
                    text = re.sub(pattern, cap_replacement, text)
            
            # Store information about no_period punctuation for use by apply_sentence_formatting
            # We'll add this as an attribute to track across method calls
            self._no_period_punctuation = no_period_punctuation

            return text

        except (FileNotFoundError, json.JSONDecodeError) as e:
            # If file doesn't exist or is invalid, return text unchanged
            print(f"Warning: Could not load punctuation translation file: {e}")
            return text

    def show_save_format_modal(self):
        """Show the format selection modal and handle the save flow"""
        # Create and show the format selection modal
        format_modal = SaveFormatModal(self)
        format_modal.formatSelected.connect(self.on_format_selected)
        format_modal.exec()
        
        return True  # Return True to indicate save process initiated

    def on_format_selected(self, file_format):
        """Handle format selection and open file explorer in save-here mode"""
        # Get documents directory
        documents_dir = self.assistivox_dir / "documents" if self.assistivox_dir else Path.home()
        documents_dir.mkdir(exist_ok=True)

        # Open file explorer in save-here mode
        from gui.file_explorer.file_explorer_dialog import FileExplorerDialog

        dialog = FileExplorerDialog(
                parent=self,
                start_dir=str(documents_dir),
                mode="save",
                config=self.config,
                assistivox_dir=self.assistivox_dir,
                save_here_mode=True,
                file_format=file_format
            )

        # Pass original PDF name if available for filename suggestion
        if self.file_manager.original_pdf_path:
            dialog.original_pdf_name = self.file_manager.original_pdf_path

        dialog.fileSelected.connect(lambda path: self.save_with_format(path, file_format))
        dialog.exec()

    def save_with_format(self, file_path, file_format):
        """Save the document with the specified format"""
        try:
            if file_format == "markdown":
                # Save as markdown
                from gui.components.markdown_handler import MarkdownHandler
                markdown_text = MarkdownHandler.rich_text_to_markdown(self.text_edit.document())
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(markdown_text)
            elif file_format == "pdf":
                # Save as PDF
                from gui.components.pdf_converter import PDFConverter
                from gui.components.markdown_handler import MarkdownHandler

                # Get markdown content from document
                markdown_text = MarkdownHandler.rich_text_to_markdown(self.text_edit.document())

                # Convert to PDF
                pdf_converter = PDFConverter()

                # Check if Docker is available
                if not pdf_converter.is_docker_available():
                    QMessageBox.critical(self, "PDF Export Error",
                        "Docker is not available. Please ensure Docker is installed and running.")
                    return False
    
                success = pdf_converter.convert_markdown_to_pdf(markdown_text, file_path)
                if not success:
                    QMessageBox.critical(self, "PDF Export Error",
                        "Failed to convert document to PDF. Please check that Docker is running.")
                    return False
            else:
                # Save as plain text
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(self.text_edit.toPlainText())

            # Update file manager state ONLY if this was a markdown save (Ctrl+S), not export (Alt+E)
            if file_format == "markdown":
                self.file_manager.set_current_file_path(file_path)
            # For other formats (txt, pdf), this is export only - don't update current_file_path

            self.is_modified = False

            # Emit signal
            self.textSaved.emit(self.text_edit.toPlainText(), file_path)

            return True

        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save document: {str(e)}")
            return False

    def save_as_markdown_directly(self):
        """Save document directly as markdown without format modal"""
        # Get documents directory
        documents_dir = self.assistivox_dir / "documents" if self.assistivox_dir else Path.home()
        documents_dir.mkdir(exist_ok=True)
    
        # Open file explorer in save-here mode for markdown
        from gui.file_explorer.file_explorer_dialog import FileExplorerDialog
    
        dialog = FileExplorerDialog(
            parent=self,
            start_dir=str(documents_dir),
            mode="save",
            config=self.config,
            assistivox_dir=self.assistivox_dir,
            save_here_mode=True,
            file_format="markdown"
        )
    
        # Pass original PDF name if available for filename suggestion
        if self.file_manager.original_pdf_path:
            dialog.original_pdf_name = self.file_manager.original_pdf_path
    
        dialog.fileSelected.connect(lambda path: self.save_with_format(path, "markdown"))
        dialog.exec()
    
        return True

    def show_export_format_modal(self):
        """Show the export format modal (Alt+E) - text only"""
        # Create and show the export format modal (text only)
        format_modal = ExportFormatModal(self)
        format_modal.formatSelected.connect(self.on_format_selected)
        format_modal.exec()
    
        return True

    def sync_document_structure_from_text(self):
        """Sync the linked list structure from current text content"""
        print("DEBUG: ===== SYNCING DOCUMENT STRUCTURE FROM TEXT =====")
    
        try:
            # Get the current content directly from the text editor as plain text
            # Get the RAW MARKDOWN content from the original file, not the rendered text
            if self.file_manager and self.file_manager.get_current_file_path():
                # Read the actual .md file directly
                file_path = self.file_manager.get_current_file_path()
                with open(file_path, 'r', encoding='utf-8') as f:
                    current_text = f.read()
                print("DEBUG: Reading raw markdown from original file")
            else:
                # Fallback: use plain text (may not have markdown syntax)
                current_text = self.text_edit.toPlainText()
                print("DEBUG: Using plain text from editor (fallback - may lack markdown syntax)")           

            # Parse this plain text as markdown structure
            print("DEBUG: Parsing content as markdown structure")
            self.document_structure.parse_from_markdown(current_text)
            
            # BUILD THE LINE-TO-NODE MAPPING (NEW)
            print("DEBUG: Building line-to-node mappings...")
            self.document_structure.build_line_to_node_mapping()
            
            # Show mapping status for debugging
            self.document_structure.debug_mapping_status()
            
            # Show statistics
            self.get_document_statistics()
            
        except Exception as e:
            print(f"DEBUG: ERROR syncing document structure: {e}")
            import traceback
            traceback.print_exc()

    def get_document_statistics(self):
        """Get statistics about the document structure"""
        if not hasattr(self, 'document_structure'):
            return {}
    
        stats = {
            'total_nodes': self.document_structure.node_count,
            'headers': len(self.document_structure.get_all_headers()),
            'paragraphs': 0,
            'code_blocks': 0
        }
    
        current = self.document_structure.head
        while current:
            if current.type == 'paragraph':
                stats['paragraphs'] += 1
            elif current.type == 'code_block':
                stats['code_blocks'] += 1
            current = current.next
    
        print(f"DEBUG: Document statistics: {stats}")
        return stats

    def _on_return_pressed(self, new_line_number):
        """Handle Return key press - may have created a blank line"""
        print(f"DEBUG: Return pressed, new blank line potentially at line {new_line_number}")
        
        # The on_text_changed handler will be called automatically by Qt
        # and will detect this as a line insertion, creating the appropriate blank node
        # No additional action needed here since the localized change handler will handle it

    def _handle_localized_text_change(self):
        """Handle text changes by updating only affected nodes"""
        try:
            # Get current document lines
            from gui.components.markdown_handler import MarkdownHandler
            current_text = MarkdownHandler.rich_text_to_markdown(self.text_edit.document())
            current_lines = current_text.split('\n')
            current_line_count = len(current_lines)

            print(f"DEBUG: ===== LOCALIZED TEXT CHANGE =====")
            print(f"DEBUG: Previous line count: {self.previous_line_count}")
            print(f"DEBUG: Current line count: {current_line_count}")
    
            # Handle different change scenarios
            if self.previous_line_count == 0:
                # First time or empty document - do full parse
                print("DEBUG: Initial document load - performing full parse")
                self._full_reparse()
            elif current_line_count > self.previous_line_count:
                # Lines added
                lines_added = current_line_count - self.previous_line_count
                print(f"DEBUG: {lines_added} line(s) added")
                self._handle_lines_added(current_lines, lines_added)
            elif current_line_count < self.previous_line_count:
                # Lines deleted
                lines_deleted = self.previous_line_count - current_line_count
                print(f"DEBUG: {lines_deleted} line(s) deleted")
                self._handle_lines_deleted(current_lines, lines_deleted)
            else:
                # Same number of lines - content changed
                print("DEBUG: Content modified (same line count)")
                self._handle_content_modified(current_lines)
    
            # Update tracking variables
            self.previous_line_count = current_line_count
            self.previous_lines = current_lines[:]
    
            print("DEBUG: ===== END LOCALIZED TEXT CHANGE =====")
    
        except Exception as e:
            print(f"DEBUG: ERROR in localized update: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to full reparse on error
            print("DEBUG: Falling back to full reparse due to error")
            self._full_reparse()
    
    def _handle_lines_added(self, current_lines, lines_added):
        """Handle addition of new lines"""
        print(f"DEBUG: ===== HANDLING {lines_added} ADDED LINE(S) =====")
    
        # Find where the lines were added by comparing with previous lines
        insertion_point = self._find_insertion_point(current_lines)
    
        if insertion_point is not None:
            print(f"DEBUG: Lines inserted starting at line {insertion_point + 1}")
    
            # Insert new nodes for each added line
            for i in range(lines_added):
                line_number = insertion_point + 1 + i
                if line_number <= len(current_lines):
                    line_content = current_lines[line_number - 1]  # Convert to 0-based
                    print(f"DEBUG: Inserting line {line_number}: '{line_content[:50]}...'")
                    self.document_structure.handle_line_insertion(line_number, line_content)
        else:
            print("DEBUG: Could not determine insertion point, doing full reparse")
            self._full_reparse()
    
    def _handle_lines_deleted(self, current_lines, lines_deleted):
        """Handle deletion of lines"""
        print(f"DEBUG: ===== HANDLING {lines_deleted} DELETED LINE(S) =====")
    
        # Find where the lines were deleted by comparing with previous lines
        deletion_point = self._find_deletion_point(current_lines)
    
        if deletion_point is not None:
            print(f"DEBUG: Lines deleted starting at line {deletion_point + 1}")
    
            # Delete nodes for each removed line (delete from end to avoid index shifting)
            for i in range(lines_deleted):
                line_number = deletion_point + 1  # Always delete the same line number
                print(f"DEBUG: Deleting line {line_number}")
                self.document_structure.handle_line_deletion(line_number)
        else:
            print("DEBUG: Could not determine deletion point, doing full reparse")
            self._full_reparse()
    
    def _handle_content_modified(self, current_lines):
        """Handle modification of existing lines"""
        print("DEBUG: ===== HANDLING CONTENT MODIFICATION =====")
    
        # Find which specific lines changed
        changed_lines = []
    
        for i, (current, previous) in enumerate(zip(current_lines, self.previous_lines)):
            if current != previous:
                changed_lines.append(i + 1)  # Convert to 1-based line number
    
        print(f"DEBUG: Changed lines: {changed_lines}")
    
        # Update each changed line's corresponding node
        for line_number in changed_lines:
            if line_number <= len(current_lines):
                new_content = current_lines[line_number - 1]  # Convert to 0-based
                print(f"DEBUG: Updating line {line_number} content: '{new_content[:50]}...'")
                self.document_structure.update_node_at_line(line_number, new_content)
    
    def _find_insertion_point(self, current_lines):
        """Find where new lines were inserted"""
        if not self.previous_lines:
            return 0  # Insert at beginning if no previous lines
    
        # Compare from start to find first difference
        for i in range(min(len(current_lines), len(self.previous_lines))):
            if current_lines[i] != self.previous_lines[i]:
                return i
    
        # If all compared lines match, new lines were added at the end
        return len(self.previous_lines)
    
    def _find_deletion_point(self, current_lines):
        """Find where lines were deleted"""
        if not current_lines:
            return 0  # Delete from beginning if no current lines
    
        # Compare from start to find first difference
        for i in range(min(len(current_lines), len(self.previous_lines))):
            if current_lines[i] != self.previous_lines[i]:
                return i
    
        # If all compared lines match, lines were deleted from the end
        return len(current_lines)
    
    def _full_reparse(self):
        """Perform full document reparse (fallback method)"""
        print("DEBUG: Performing full document reparse")
        self.document_change_lock = True
        try:
            self.sync_document_structure_from_text()
        finally:
            self.document_change_lock = False

    def _jump_to_node(self, node_id: str):
        """Jump cursor to the specified node"""
        # Use the simpler line-based navigation method instead of content matching
        success = self.set_cursor_to_node_id(node_id)

        if success:
            node = self.document_structure.get_node(node_id)
            if node:
                print(f"DEBUG: Jumped to {node.type}: '{node.content[:50]}...'")
        else:
            print(f"DEBUG: Failed to jump to node {node_id[:8]}...")

    def navigate_to_next_element(self):
        """Navigate to next semantic element"""
        cursor = self.text_edit.textCursor()
        current_block = cursor.block()
        
        # Just get the next block
        next_block = current_block.next()
        
        if next_block.isValid():
            new_cursor = QTextCursor(next_block)
            new_cursor.setPosition(next_block.position())
            self.text_edit.setTextCursor(new_cursor)
            
            text = next_block.text().strip()
            print(f"DEBUG: Jumped to next block: '{text[:50]}...'")
        else:
            print("DEBUG: No more blocks found")
    
    def navigate_to_previous_element(self):
        """Navigate to previous semantic element"""
        cursor = self.text_edit.textCursor()
        current_block = cursor.block()
        
        # Just get the previous block
        prev_block = current_block.previous()
        
        if prev_block.isValid():
            new_cursor = QTextCursor(prev_block)
            new_cursor.setPosition(prev_block.position())
            self.text_edit.setTextCursor(new_cursor)
            
            text = prev_block.text().strip()
            print(f"DEBUG: Jumped to previous block: '{text[:50]}...'")
        else:
            print("DEBUG: No more blocks found")
    
    def _is_heading_block(self, block):
        """Check if a block is formatted as a heading"""
        from PySide6.QtGui import QTextBlockFormat
        
        # Get the block format
        block_format = block.blockFormat()
        
        # Qt markdown renderer sets heading level as a property
        heading_level = block_format.headingLevel()
        
        return heading_level > 0
    
    def navigate_to_next_heading(self):
        """Navigate to next heading"""
        cursor = self.text_edit.textCursor()
        current_block = cursor.block()
    
        block = current_block.next()
        while block.isValid():
            if self._is_heading_block(block):
                new_cursor = QTextCursor(block)
                new_cursor.setPosition(block.position())
                self.text_edit.setTextCursor(new_cursor)
                text = block.text().strip()
                print(f"DEBUG: Jumped to heading: '{text[:50]}...'")
                return
            block = block.next()
        
        print("DEBUG: No more headings found")
    
    def navigate_to_previous_heading(self):
        """Navigate to previous heading"""
        cursor = self.text_edit.textCursor()
        current_block = cursor.block()
        
        block = current_block.previous()
        while block.isValid():
            if self._is_heading_block(block):
                new_cursor = QTextCursor(block)
                new_cursor.setPosition(block.position())
                self.text_edit.setTextCursor(new_cursor)
                text = block.text().strip()
                print(f"DEBUG: Jumped to heading: '{text[:50]}...'")
                return
            block = block.previous()
        
        print("DEBUG: No previous headings found")
    
    def _find_next_semantic_element(self, current_block):
        """Find next semantic element, treating consecutive text as one paragraph"""
        # Get the type of current element
        current_text = current_block.text().strip()
        current_type = self._get_element_type(current_text) if current_text else 'empty'
        
    # Start from next block
        block = current_block.next()
        
        # Skip empty lines
        while block.isValid() and not block.text().strip():
            block = block.next()
        
        if not block.isValid():
            return None
        
        # If we're NOT in a paragraph, return the first content block we find
        if current_type != 'paragraph':
            return block
        
        # If we ARE in a paragraph, skip to end of current paragraph
        while block.isValid():
            text = block.text().strip()
            if not text:  # Empty line ends paragraph
                while block.isValid() and not block.text().strip():
                    block = block.next()
                return block if block.isValid() else None
            
            block_type = self._get_element_type(text)
            if block_type != 'paragraph':  # Different element ends paragraph
                return block
                
            block = block.next()
        
        return None

    def _find_previous_semantic_element(self, current_block):
        """Find previous semantic element, treating consecutive text as one paragraph"""
        block = current_block.previous()
        
        # Skip empty lines going backwards
        while block.isValid() and not block.text().strip():
            block = block.previous()
        
        if not block.isValid():
            return None
        
        # If this block is not a paragraph, return it
        text = block.text().strip()
        block_type = self._get_element_type(text)
        
        if block_type != 'paragraph':
            return block
        
        # It's a paragraph - find the start of this paragraph
        while block.previous().isValid():
            prev_block = block.previous()
            prev_text = prev_block.text().strip()
            
            if not prev_text:  # Empty line - current block is paragraph start
                break
            
            prev_type = self._get_element_type(prev_text)
            if prev_type != 'paragraph':  # Different element - current block is paragraph start
                break
            
            block = prev_block
        
        return block
    
    def _find_next_heading(self, current_block):
        """Find the next heading block"""
        block = current_block.next()
        
        while block.isValid():
            text = block.text().strip()
            if self._is_heading(text):
                return block
            block = block.next()
        
        return None
    
    def _find_previous_heading(self, current_block):
        """Find the previous heading block"""
        block = current_block.previous()
        
        while block.isValid():
            text = block.text().strip()
            if self._is_heading(text):
                return block
            block = block.previous()
        
        return None
    
    def _get_element_type(self, text):
        """Determine the type of semantic element from text"""
        import re
        
        if not text:
            return 'empty'
        
        # Check for headings
        if re.match(r'^#{1,6}\s+', text):
            return 'heading'
        
        # Check for code block markers
        if text.startswith('```'):
            return 'code_block'
        
        # Check for horizontal rules
        if re.match(r'^(-\s*-\s*-+|\*\s*\*\s*\*+|_\s*_\s*_+)$', text):
            return 'horizontal_rule'
    
        # Check for list items
        if re.match(r'^[\s]*[-*+]\s+', text) or re.match(r'^[\s]*\d+\.\s+', text):
            return 'list_item'
        
        # Check for tables (contains |)
        if '|' in text and len(text.split('|')) > 2:
            return 'table'
        
        # Check for asvx tags
        if text.startswith('{asvx|') and text.endswith('}'):
            return 'asvx_tag'
        
        # Everything else is a paragraph
        return 'paragraph'
    
    def _jump_to_block(self, target_block):
        """Jump cursor to the specified block"""
        from PySide6.QtGui import QTextCursor
        
        cursor = QTextCursor(target_block)
        cursor.setPosition(target_block.position())
        self.text_edit.setTextCursor(cursor)
        
        text = target_block.text().strip()
        element_type = self._get_element_type(text)
        print(f"DEBUG: Jumped to {element_type}: '{text[:50]}...'")

    def _jump_to_document_start(self):
        """Jump cursor to the first non-empty element in the document"""
        document = self.text_edit.document()
        first_block = document.firstBlock()
        
        # Find first non-empty block
        while first_block.isValid() and not first_block.text().strip():
            first_block = first_block.next()
        
        if first_block.isValid():
            self._jump_to_block(first_block)
            print(f"DEBUG: Jumped to document start: '{first_block.text()[:50]}...'")
        else:
            # Document is completely empty, go to beginning
            cursor = self.text_edit.textCursor()
            cursor.movePosition(cursor.Start)
            self.text_edit.setTextCursor(cursor)
            print("DEBUG: Document is empty, jumped to start position")

    def get_current_page_number(self):
        """Get the current page number based on cursor position using actual page numbers"""
        import re

        cursor = self.text_edit.textCursor()
        current_block_number = cursor.blockNumber()
        document = self.text_edit.document()

        block = document.findBlockByNumber(current_block_number)
        while block.isValid():
            text = block.text().strip()

            # Check if text matches "PAGE" followed by positive integer
            page_match = re.match(r'^PAGE (\d+)$', text)
            if page_match:
                print(f"DEBUG: Found potential PAGE at block {block.blockNumber()}: '{text}'")

                # Check the formatting of the PAGE
                block_format = block.blockFormat()

                # Get character format for the block
                cursor = self.text_edit.textCursor()
                cursor.setPosition(block.position())
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                char_format = cursor.charFormat()
    
                # Check formatting matches: bold, center, margins 20/5 for first block
                is_bold = char_format.fontWeight() == QFont.Bold
                is_center = block_format.alignment() == Qt.AlignCenter
                top_margin = block_format.topMargin()
                bottom_margin = block_format.bottomMargin()
    
                print(f"DEBUG: Block {block.blockNumber()} formatting - Bold: {is_bold}, Center: {is_center}, TopMargin: {top_margin}, BottomMargin: {bottom_margin}")
    
                # Check if first block formatting matches: bold, center, margin top 20, margin bottom 5
                if is_bold and is_center and top_margin == 5 and bottom_margin == 20:
                    page_num = page_match.group(1)
                    print(f"DEBUG: Found current PAGE {page_num} at block {block.blockNumber()}")
                    return int(page_num)

            block = block.previous()

        return 1

    def show_go_to_page_dialog(self):
        """Show go to page dialog for text editor"""

        current_page = self.get_current_page_number()
        total_pages = self.count_pages()
        
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
                    self.goto_page(page_number)
            except ValueError:
                pass
    
    def goto_page(self, page_number):
        """Navigate to a specific page by page number"""
        import re
    
        document = self.text_edit.document()
        block = document.begin()
    
        while block.isValid():
            text = block.text().strip()
    
            # Check if text matches "PAGE" followed by positive integer
            page_match = re.match(r'^PAGE (\d+)$', text)
            if page_match:
                # Check the formatting of the PAGE block
                block_format = block.blockFormat()
    
                # Get character format for the block
                cursor = self.text_edit.textCursor()
                cursor.setPosition(block.position())
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                char_format = cursor.charFormat()
    
                # Check formatting matches: bold, center, margin top 5, margin bottom 20
                is_bold = char_format.fontWeight() == QFont.Bold
                is_center = block_format.alignment() == Qt.AlignCenter
                top_margin = block_format.topMargin()
                bottom_margin = block_format.bottomMargin()
    
                # Check if formatting matches required pattern
                if is_bold and is_center and top_margin == 5 and bottom_margin == 20:
                    # Check if this is the target page number
                    found_page_num = int(page_match.group(1))
                    if found_page_num == page_number:
                        # Put cursor on the next block
                        next_block = block.next()
                        if next_block.isValid():
                            cursor = self.text_edit.textCursor()
                            cursor.setPosition(next_block.position())
                            self.text_edit.setTextCursor(cursor)
                            self.ensure_block_visible(cursor.blockNumber()-3)
                            self.ensure_block_visible(cursor.blockNumber()+1)
                            self.ensure_block_visible(cursor.blockNumber())
                        return
    
            block = block.next()

    def page_exists(self, page_number):
        """Check if a page with the given number exists in the document"""
        import re
    
        document = self.text_edit.document()
        block = document.begin()
    
        while block.isValid():
            text = block.text().strip()
    
            # Check if text matches "PAGE" followed by positive integer
            page_match = re.match(r'^PAGE (\d+)$', text)
            if page_match:
                # Check the formatting of the PAGE
                block_format = block.blockFormat()
    
                # Get character format for the block
                cursor = self.text_edit.textCursor()
                cursor.setPosition(block.position())
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                char_format = cursor.charFormat()
    
                # Check formatting matches: bold, center, margin top 5, margin bottom 20
                is_bold = char_format.fontWeight() == QFont.Bold
                is_center = block_format.alignment() == Qt.AlignCenter
                top_margin = block_format.topMargin()
                bottom_margin = block_format.bottomMargin()
    
                if is_bold and is_center and top_margin == 5 and bottom_margin == 20:
                    found_page_num = int(page_match.group(1))
                    
                    if found_page_num == page_number:
                        return True
                    elif found_page_num > page_number:
                        return False
    
            block = block.next()
    
        return False

    def navigate_to_next_page(self):
        """Navigate to the next page"""
        import re
    
        cursor = self.text_edit.textCursor()
        current_block_number = cursor.blockNumber()
        document = self.text_edit.document()

        block = document.findBlockByNumber(current_block_number)
    
        while block.isValid():
            text = block.text().strip()
    
            # Check if text matches "PAGE" followed by positive integer
            page_match = re.match(r'^PAGE (\d+)$', text)
            if page_match:
                # Check the formatting of the PAGE block
                block_format = block.blockFormat()
    
                # Get character format for the block
                cursor = self.text_edit.textCursor()
                cursor.setPosition(block.position())
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                char_format = cursor.charFormat()
    
                # Check formatting matches: bold, center, margin top 5, margin bottom 20
                is_bold = char_format.fontWeight() == QFont.Bold
                is_center = block_format.alignment() == Qt.AlignCenter
                top_margin = block_format.topMargin()
                bottom_margin = block_format.bottomMargin()
    
                # Check if formatting matches required pattern
                if is_bold and is_center and top_margin == 5 and bottom_margin == 20:
                    # Put cursor on the next block
                    next_block = block.next()
                    if next_block.isValid():
                        cursor = self.text_edit.textCursor()
                        cursor.setPosition(next_block.position())
                        self.text_edit.setTextCursor(cursor)
                        self.ensure_block_visible(cursor.blockNumber()+2)
                        self.ensure_block_visible(cursor.blockNumber())
                    return
    
            block = block.next()

    def navigate_to_previous_page(self):
        """Navigate to the previous page"""
        import re

        cursor = self.text_edit.textCursor()
        current_block_number = cursor.blockNumber()
        document = self.text_edit.document()

        block = document.findBlockByNumber(current_block_number)
        top = self.cursor_is_at_page_top()
        if top > -1:
            block = document.findBlockByNumber(top-2)
            if block.isValid():
                cursor = self.text_edit.textCursor()
                cursor.setPosition(block.position())
                self.text_edit.setTextCursor(cursor)

        top = self.goto_page_top()
        self.ensure_block_visible(top-4)
        self.ensure_block_visible(top)

    def goto_page_top(self):
        """Goto the top of the current page"""
        import re

        cursor = self.text_edit.textCursor()
        current_block_number = cursor.blockNumber()
        document = self.text_edit.document()

        block = document.findBlockByNumber(current_block_number)
        while block.isValid():
            text = block.text().strip()

            # Check if text matches "PAGE" followed by positive integer
            page_match = re.match(r'^PAGE (\d+)$', text)
            if page_match:
                print(f"DEBUG: Found potential PAGE at block {block.blockNumber()}: '{text}'")

                # Check the formatting of the PAGE
                block_format = block.blockFormat()

                # Get character format for the block
                cursor = self.text_edit.textCursor()
                cursor.setPosition(block.position())
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                char_format = cursor.charFormat()
    
                # Check formatting matches: bold, center, margins 20/5 for first block
                is_bold = char_format.fontWeight() == QFont.Bold
                is_center = block_format.alignment() == Qt.AlignCenter
                top_margin = block_format.topMargin()
                bottom_margin = block_format.bottomMargin()
    
                print(f"DEBUG: Block {block.blockNumber()} formatting - Bold: {is_bold}, Center: {is_center}, TopMargin: {top_margin}, BottomMargin: {bottom_margin}")
    
                # Check if first block formatting matches: bold, center, margin top 20, margin bottom 5
                if is_bold and is_center and top_margin == 5 and bottom_margin == 20:
                    # Put cursor on the next block
                    next_block = block.next()
                    if next_block.isValid():
                        cursor = self.text_edit.textCursor()
                        cursor.setPosition(next_block.position())
                        self.text_edit.setTextCursor(cursor)
                        self.ensure_block_visible(cursor.blockNumber())

                    cursor = self.text_edit.textCursor()
                    return cursor.blockNumber()

            block = block.previous()

    def cursor_is_at_page_top(self):
        """Gheck if the cursor is at the top of the current page"""
        cursor = self.text_edit.textCursor()
        current_block_number = cursor.blockNumber()

        if current_block_number == self.goto_page_top():
            return current_block_number
        return -1

    def ensure_block_visible(self, block_number):
        if block_number < 1:
            return

        document = self.text_edit.document()
        block = document.findBlockByNumber(block_number)
        if block.isValid():
            # Move the cursor to the start of the block
            cursor = self.text_edit.textCursor()
            cursor.setPosition(block.position())
            self.text_edit.setTextCursor(cursor)
            # Ensure that the new cursor is visible in the viewport
            self.text_edit.ensureCursorVisible()

    def count_pages(self):
        """Count the number of document pages"""
        import re
    
        total_pages = 0
        document = self.text_edit.document()
        block = document.begin()

        while block.isValid():
            text = block.text().strip()
    
            # Check if text matches "PAGE" followed by positive integer
            page_match = re.match(r'^PAGE (\d+)$', text)
            if page_match:
                # Check the formatting of the PAGE block
                block_format = block.blockFormat()
    
                # Get character format for the block
                cursor = self.text_edit.textCursor()
                cursor.setPosition(block.position())
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                char_format = cursor.charFormat()
    
                # Check formatting matches: bold, center, margin top 5, margin bottom 20
                is_bold = char_format.fontWeight() == QFont.Bold
                is_center = block_format.alignment() == Qt.AlignCenter
                top_margin = block_format.topMargin()
                bottom_margin = block_format.bottomMargin()
    
                # Check if formatting matches required pattern
                if is_bold and is_center and top_margin == 5 and bottom_margin == 20:
                    total_pages += 1
    
            block = block.next()

        return total_pages
