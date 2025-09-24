# gui/components/pdf_handler.py
import os
from PySide6.QtGui import QTextDocument, QFont, QColor
from PySide6.QtWidgets import (
        QMainWindow, QVBoxLayout, QWidget, QLabel, QStatusBar, QDialog,
        QHBoxLayout, QLineEdit, QPushButton, QProgressBar
)
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtPdf import QPdfDocument
from PySide6.QtCore import Qt, QUrl, QPointF, QSize, QTimer
from PySide6.QtGui import QWheelEvent, QShortcut, QKeySequence


class PDFHandler:
    """
    Utility class for handling PDF documents in text editors

    This class provides methods to convert and load PDF content
    into QTextDocument and display original PDFs.
    """

    @staticmethod
    def pdf_to_rich_text(document, pdf_path, config=None, parent=None):
        """
        Convert PDF to rich text using threaded extraction

        Args:
            document: The QTextDocument to load content into
            pdf_path: The path to the PDF file to convert
            config: Application configuration dict to apply styling
            parent: Parent widget for the progress dialog
    
        Returns:
            bool: True if extraction was successful, False if cancelled or failed
        """
        from gui.components.pdf_extraction_dialog import PDFExtractionDialog
        from gui.components.markdown_handler import MarkdownHandler
        from PySide6.QtWidgets import QDialog
    
        # Create extraction dialog
        dialog = PDFExtractionDialog(pdf_path, parent)
    
        # Start extraction and show dialog
        dialog.start_extraction()
        result = dialog.exec()

        if result == QDialog.Accepted:
            # Extraction completed successfully
            final_text = dialog.get_extracted_text()
            if final_text:
                # Add asvx tag at the beginning
                asvx_tag = "{"+f"asvx|pdf:{pdf_path}"+"}\n\n"
                final_text = asvx_tag + final_text
        
                # Load content into document
                document.clear()
                MarkdownHandler.markdown_to_rich_text(document, final_text)
    
                # Store the original PDF path in document metadata
                document.setMetaInformation(QTextDocument.DocumentUrl, pdf_path)
                return True

        return False

    @staticmethod
    def is_pdf_file(filepath):
        """
        Check if a file is a PDF file based on extension

        Args:
            filepath: Path to the file to check

        Returns:
            bool: True if it's a PDF file, False otherwise
        """
        if not filepath:
            return False

        return filepath.lower().endswith('.pdf')

    @staticmethod
    def get_original_pdf_path(document):
        """
        Get the original PDF path from a document

        Args:
            document: QTextDocument that may have been loaded from a PDF

        Returns:
            str: Path to the original PDF file, or None if not available
        """
        return document.metaInformation(QTextDocument.DocumentUrl)


class PageNavigationDialog(QDialog):
    """Dialog for entering a page number to navigate to"""

    def __init__(self, total_pages, current_page=1, parent=None):
        super().__init__(parent)
        self.total_pages = total_pages
        self.setWindowTitle("Go to Page")
        self.setModal(True)
        self.resize(300, 120)

        # Create layout
        layout = QVBoxLayout(self)

        # Instructions
        instruction_label = QLabel(f"Enter page number (1-{total_pages}):")
        layout.addWidget(instruction_label)

        # Page input
        input_layout = QHBoxLayout()
        self.page_input = QLineEdit()
        self.page_input.setText(str(current_page))
        self.page_input.selectAll()  # Select all text for easy replacement
        input_layout.addWidget(QLabel("Page:"))
        input_layout.addWidget(self.page_input)
        layout.addLayout(input_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("OK")
        self.cancel_button = QPushButton("Cancel")

        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        # Set OK as default button and connect Enter key
        self.ok_button.setDefault(True)
        self.page_input.returnPressed.connect(self.accept)

        # Focus on input field
        self.page_input.setFocus()

    def get_page_number(self):
        """Get the entered page number, returns None if invalid"""
        try:
            page_num = int(self.page_input.text().strip())
            if 1 <= page_num <= self.total_pages:
                return page_num
            return None
        except ValueError:
            return None


class PDFViewerWindow(QMainWindow):
    """
    Independent window for viewing original PDF documents with zoom controls
    """

    def __init__(self, pdf_path, parent=None):
        super().__init__(parent)

        # Store parent reference separately to avoid conflict with parent() method
        self.parent_editor = parent

        # Set window flags to make it independent but still associated with the main app
        # Remove WindowStaysOnTopHint to allow natural focus switching
        self.setWindowFlags(Qt.Window)

        # Set up window properties
        self.setWindowTitle(f"PDF Viewer - {os.path.basename(pdf_path)}")
        self.resize(800, 600)
    
        # Initialize zoom factor
        self.zoom_factor = 1.0  # 100%
    
        # Initialize page tracking
        self.current_page = 1
        self.total_pages = 0
    
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create PDF view
        self.pdf_view = PDFView()  # Using our custom PDFView subclass
        self.pdf_view.wheelZoomRequested.connect(self.handle_wheel_zoom)
        layout.addWidget(self.pdf_view)

        # Create PDF document
        self.pdf_document = QPdfDocument()
        self.pdf_view.setDocument(self.pdf_document)
    
        # Load the PDF file
        self.pdf_document.load(pdf_path)

        # Set zoom mode to fit width by default
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)  # Enable scrolling through multiple pages
    
        # Create enhanced status bar
        self.create_status_bar()
    
        # Add keyboard shortcuts
        self.add_shortcuts()
    
        # Connect signals for page tracking
        self.setup_page_tracking()

    def handle_wheel_zoom(self, delta):
        """Handle zoom requests from wheel events"""
        if delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()
    
    def zoom_in_status(self):
        """Increase zoom factor from status bar button"""
        self.zoom_factor = min(self.zoom_factor * 1.2, 5.0)  # Max zoom 500%
        self.apply_zoom()

    def zoom_out_status(self):
        """Decrease zoom factor from status bar button"""
        self.zoom_factor = max(self.zoom_factor / 1.2, 0.2)  # Min zoom 20%
        self.apply_zoom()

    def zoom_in(self):
        """Increase zoom by 10% (for existing shortcuts)"""
        if self.zoom_factor < 5.0:  # Limit maximum zoom to 500%
            self.zoom_factor += 0.1
            self.apply_zoom()

    def zoom_out(self):
        """Decrease zoom by 10% (for existing shortcuts)"""
        if self.zoom_factor > 0.2:  # Limit minimum zoom to 20%
            self.zoom_factor -= 0.1
            self.apply_zoom()

    def zoom_reset(self):
        """Reset zoom to 100%"""
        self.zoom_factor = 1.0
        self.apply_zoom()
    
    def apply_zoom(self):
        """Apply the current zoom factor to the PDF view"""
        # Switch to custom zoom mode
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.pdf_view.setZoomFactor(self.zoom_factor)
        
        # Update zoom indicator
        zoom_percentage = int(self.zoom_factor * 100)
        self.zoom_label.setText(f"Zoom: {zoom_percentage}%")

    def keyPressEvent(self, event):
        """Handle key press events for the PDF viewer window"""
        if event.key() == Qt.Key_Escape:
            # Close the window when Escape is pressed
            self.close()
        elif event.key() == Qt.Key_PageDown:
            # Move to next page
            current_page = self.pdf_view.pageNavigator().currentPage()
            if current_page < self.pdf_document.pageCount() - 1:
                self.pdf_view.pageNavigator().jump(current_page + 1, QPointF(0, 0))
        elif event.key() == Qt.Key_PageUp:
            # Move to previous page
            current_page = self.pdf_view.pageNavigator().currentPage()
            if current_page > 0:
                self.pdf_view.pageNavigator().jump(current_page - 1, QPointF(0, 0))
        elif event.key() == Qt.Key_Home and event.modifiers() & Qt.ControlModifier:
            # Go to first page
            self.pdf_view.pageNavigator().jump(0, QPointF(0, 0))
        elif event.key() == Qt.Key_End and event.modifiers() & Qt.ControlModifier:
            # Go to last page
            self.pdf_view.pageNavigator().jump(self.pdf_document.pageCount() - 1, QPointF(0, 0))
        else:
            # Pass other key events to parent
            super().keyPressEvent(event)

    def create_status_bar(self):
        """Create the enhanced status bar with page info, zoom controls, and progress bar"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
    
        # Create status bar widgets
        status_layout = QHBoxLayout()
        status_widget = QWidget()
        status_widget.setLayout(status_layout)
    
        # Page info (clickable button)
        self.page_info_button = QPushButton("0 / 0")
        self.page_info_button.setFlat(True)  # Make it look less button-like but still clickable
        self.page_info_button.clicked.connect(self.show_go_to_page_dialog)
        status_layout.addWidget(self.page_info_button)
    
        status_layout.addStretch()  # Push zoom controls to the right
    
        # Zoom controls
        self.zoom_label = QLabel("Zoom: 100%")
        status_layout.addWidget(self.zoom_label)

        self.zoom_out_button = QPushButton("-")
        self.zoom_out_button.setMaximumWidth(30)
        self.zoom_out_button.clicked.connect(self.zoom_out_status)
        status_layout.addWidget(self.zoom_out_button)

        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setMaximumWidth(30)
        self.zoom_in_button.clicked.connect(self.zoom_in_status)
        status_layout.addWidget(self.zoom_in_button)

        status_layout.addStretch()  # Push progress bar to the right
    
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setMinimum(1)
        self.progress_bar.setMaximum(1)  # Will be updated when document loads
        self.progress_bar.setValue(1)
        status_layout.addWidget(self.progress_bar)
    
        # Add the status widget to the status bar
        self.status_bar.addPermanentWidget(status_widget, 1)

    def add_shortcuts(self):
        """Add keyboard shortcuts"""
        # Alt+G for go to page
        self.go_to_page_shortcut = QShortcut(QKeySequence("Alt+G"), self)
        self.go_to_page_shortcut.activated.connect(self.show_go_to_page_dialog)
    
        # Zoom shortcuts
        self.zoom_in_shortcut = QShortcut(QKeySequence.ZoomIn, self)
        self.zoom_in_shortcut.activated.connect(self.zoom_in)
    
        self.zoom_out_shortcut = QShortcut(QKeySequence.ZoomOut, self)
        self.zoom_out_shortcut.activated.connect(self.zoom_out)
    
        self.zoom_reset_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        self.zoom_reset_shortcut.activated.connect(self.zoom_reset)

        # Alt+S for TTS from PDF
        self.tts_shortcut = QShortcut(QKeySequence("Alt+S"), self)
        self.tts_shortcut.activated.connect(self.start_tts_from_current_page)

    def setup_page_tracking(self):
        """Set up page tracking when document is loaded"""
        # Connect to document status change to get total pages
        self.pdf_document.statusChanged.connect(self.on_document_status_changed)
    
        # Connect to page navigation changes
        if hasattr(self.pdf_view, 'pageNavigator'):
            nav = self.pdf_view.pageNavigator()
            if nav:
                nav.currentPageChanged.connect(self.on_current_page_changed)
    
        # Use a timer to periodically check and update page info
        self.page_update_timer = QTimer()
        self.page_update_timer.timeout.connect(self.check_page_status)
        self.page_update_timer.start(200)  # Check every 200ms

    def on_document_status_changed(self):
        """Handle document status changes"""
        status = self.pdf_document.status()
        print(f"Document status changed: {status}")
    
        if status == QPdfDocument.Status.Ready:
            # Document is ready, get page count directly
            self.total_pages = self.pdf_document.pageCount()
            print(f"Document ready - Total pages: {self.total_pages}")
        
            if self.total_pages > 0:
                self.progress_bar.setMaximum(self.total_pages)
                # Force an immediate page update
                self.check_page_status()
                print(f"Page tracking initialized with {self.total_pages} pages")
            else:
                # Try again after a short delay
                QTimer.singleShot(300, self.delayed_page_count_check)

    def delayed_page_count_check(self):
        """Delayed check for page count if initial attempt failed"""
        self.total_pages = self.pdf_document.pageCount()
        print(f"Delayed page count check: {self.total_pages}")
        
        if self.total_pages > 0:
            self.progress_bar.setMaximum(self.total_pages)
            self.check_page_status()
            print(f"Delayed initialization successful with {self.total_pages} pages")
        else:
            # One more try with an even longer delay
            QTimer.singleShot(500, self.final_page_count_check)
    
    def final_page_count_check(self):
        """Final attempt to get page count"""
        self.total_pages = self.pdf_document.pageCount()
        print(f"Final page count check: {self.total_pages}")
        
        if self.total_pages > 0:
            self.progress_bar.setMaximum(self.total_pages)
            self.check_page_status()
            print(f"Final initialization successful with {self.total_pages} pages")

    def check_page_status(self):
        """Check and update page status - called by timer"""
        # Always get fresh page count
        current_total = self.pdf_document.pageCount()
        if current_total > 0 and self.total_pages != current_total:
            self.total_pages = current_total
            self.progress_bar.setMaximum(self.total_pages)
            print(f"Page count updated to: {self.total_pages}")
        
        # Get current page
        if self.total_pages > 0:
            nav = self.pdf_view.pageNavigator()
            if nav:
                new_page = nav.currentPage() + 1  # Convert from 0-based to 1-based
                if new_page != self.current_page:
                    self.current_page = new_page
                    self.update_page_display()

    def on_current_page_changed(self, page_index):
        """Handle page navigation changes"""
        if self.total_pages > 0:
            self.current_page = page_index + 1  # Convert from 0-based to 1-based
            self.update_page_display()

    def update_page_display(self):
        """Update the page info display and progress bar"""
        if self.total_pages > 0:
            self.page_info_button.setText(f"{self.current_page} / {self.total_pages}")
            self.progress_bar.setValue(self.current_page)

    def show_go_to_page_dialog(self):
        """Show the go to page dialog"""
        # Force a fresh page count check
        self.total_pages = self.pdf_document.pageCount()
        print(f"Go to page dialog - Fresh page count: {self.total_pages}")
        
        if self.total_pages <= 0:
            print(f"Cannot show dialog: total_pages={self.total_pages}")
            return
    
        dialog = PageNavigationDialog(self.total_pages, self.current_page, self)
        if dialog.exec() == QDialog.Accepted:
            page_number = dialog.get_page_number()
            if page_number is not None:
                self.go_to_page(page_number)
            
    def go_to_page(self, page_number):
        """Navigate to a specific page (1-based)"""
        if 1 <= page_number <= self.total_pages:
            # Convert to 0-based page number for the PDF view
            zero_based_page = page_number - 1
            self.pdf_view.pageNavigator().jump(zero_based_page, QPointF(0, 0))
    
    def zoom_in(self):
        """Increase zoom factor"""
        self.zoom_factor = min(self.zoom_factor * 1.2, 5.0)  # Max zoom 500%
        self.pdf_view.setZoomFactor(self.zoom_factor)
    
    def zoom_out(self):
        """Decrease zoom factor"""
        self.zoom_factor = max(self.zoom_factor / 1.2, 0.2)  # Min zoom 20%
        self.pdf_view.setZoomFactor(self.zoom_factor)

    def start_tts_from_current_page(self):
        """Start TTS reading from the current PDF page (Alt+S)"""
        if not hasattr(self, 'parent_editor') or not self.parent_editor:
            print("DEBUG: No parent editor available for TTS")
            return

        current_page = self.current_page
        print(f"DEBUG: PDF Alt+S - Starting TTS from page {current_page}")

        # Check if TTS window already exists
        if hasattr(self.parent_editor, 'tts_window') and self.parent_editor.tts_window and not self.parent_editor.tts_window.isHidden():
            # TTS window exists, bring it to front and jump to page
            self.parent_editor.tts_window.raise_()
            self.parent_editor.tts_window.activateWindow()
        
            # Jump to page if the method exists
            if hasattr(self.parent_editor.tts_window, 'jump_to_page_and_start'):
                self.parent_editor.tts_window.jump_to_page_and_start(current_page)
        else:
            # Create new TTS window using the existing toggle_speech method
            self.parent_editor.toggle_speech()
            
            # Use a timer to jump after widget is fully loaded
            from PySide6.QtCore import QTimer
            def delayed_jump():
                if hasattr(self.parent_editor, 'tts_window') and self.parent_editor.tts_window:
                    if hasattr(self.parent_editor.tts_window, 'jump_to_page_and_start'):
                        self.parent_editor.tts_window.jump_to_page_and_start(current_page)
            
            QTimer.singleShot(500, delayed_jump)


class PDFView(QPdfView):
    """Custom QPdfView that adds support for Ctrl+Wheel zooming"""
    
    # Signal for wheel zoom requests
    from PySide6.QtCore import Signal
    wheelZoomRequested = Signal(int)  # Positive for zoom in, negative for zoom out
    
    def wheelEvent(self, event):
        """Handle mouse wheel events for zooming when Ctrl is pressed"""
        # Check if Ctrl key is pressed
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            self.wheelZoomRequested.emit(delta)
            event.accept()
        else:
            # Pass the event to the parent for normal scrolling
            super().wheelEvent(event)

