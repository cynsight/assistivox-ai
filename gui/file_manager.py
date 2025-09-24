# gui/file_manager.py
"""
File Manager for Assistivox
Handles all file operations including open, save, save as, and format conversions
"""

import os
from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QFormLayout
from PySide6.QtGui import QTextDocument
from PySide6.QtCore import QObject, Signal

from gui.file_explorer.file_explorer_dialog import FileExplorerDialog
from gui.components.markdown_handler import MarkdownHandler

class SaveFileDialog(QDialog):
    """Dialog for saving a file with a name"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Document")
        self.setMinimumWidth(400)
        
        # Set up layout
        layout = QVBoxLayout(self)
        
        # File name field
        form_layout = QFormLayout()
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("Enter filename (without extension)")
        form_layout.addRow("Filename:", self.filename_edit)
        layout.addLayout(form_layout)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        save_btn.setDefault(True)
        
        buttons_layout.addWidget(cancel_btn)
        buttons_layout.addWidget(save_btn)
        layout.addLayout(buttons_layout)
        
        # Set focus to filename field
        self.filename_edit.setFocus()
    
    def get_filename(self):
        """Get the entered filename"""
        filename = self.filename_edit.text().strip()
        if filename and not filename.lower().endswith('.txt'):
            filename += '.txt'
        return filename


class FileManager(QObject):
    """
    File Manager class for handling all file operations in Assistivox
    """
    
    # Signals
    fileLoaded = Signal(str, str)  # file_path, content_type ('text', 'html', 'markdown', 'pdf')
    fileSaved = Signal(str, str)   # text_content, file_path
    
    def __init__(self, text_editor, config=None, assistivox_dir=None, parent=None):
        super().__init__(parent)
        self.text_editor = text_editor
        self.config = config
        self.assistivox_dir = assistivox_dir
        self.current_file_path = None
        self.original_pdf_path = None
        
    def open_file_dialog(self):
        """Open the custom file explorer dialog"""
        # Default start directory
        default_dir = self.assistivox_dir / "documents" if self.assistivox_dir else Path.home()
        if self.assistivox_dir and not default_dir.exists():
            default_dir.mkdir(exist_ok=True)
    
        start_dir = default_dir
    
        # Check config for last_open directory
        if self.config and "file_settings" in self.config:
            last_open_path = self.config["file_settings"].get("last_open")
            if last_open_path:
                last_open_dir = Path(last_open_path)
                # Only use if it exists and is a directory
                if last_open_dir.exists() and last_open_dir.is_dir():
                    start_dir = last_open_dir

        dialog = FileExplorerDialog(self.parent(), str(start_dir), mode="open", config=self.config, assistivox_dir=self.assistivox_dir)
        dialog.fileSelected.connect(self.load_document)
        dialog.exec()

    def load_document(self, file_path):
        """Load a document from the given file path"""
        try:
            # Check if this is a PDF file
            if file_path.lower().endswith('.pdf'):
                self.load_pdf_document(file_path)
                return

            # For non-PDF files, load as text
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()

            # Import ASVXHandler
            from gui.components.asvx_handler import ASVXHandler

            # Check if this is an ASVX file
            if ASVXHandler.is_asvx_file(file_path):
                # Load as ASVX
                metadata = ASVXHandler.asvx_to_rich_text(self.text_editor.document(), content)
                content_type = 'asvx'
            
                # Set PDF path from metadata
                if metadata and 'pdf_path' in metadata:
                    self.original_pdf_path = metadata['pdf_path']
                else:
                    self.original_pdf_path = None
                
            elif MarkdownHandler.is_markdown_file(file_path):
                # Check for assistivox tags at the beginning of markdown files
                assistivox_pdf_path, modified_content = self._parse_assistivox_tags(content, file_path)
            
                # Use modified content (may have tag removed if user chose "No")
                final_content = modified_content if modified_content is not None else content
                
                # Convert horizontal rules to page breaks before rendering
                final_content = self._convert_horizontal_rules_to_page_breaks(final_content)
            
                # Load as markdown into the text editor
                MarkdownHandler.markdown_to_rich_text(self.text_editor.document(), final_content)
                content_type = 'markdown'
    
                # Set PDF path if found and valid, otherwise clear it for markdown files
                if assistivox_pdf_path:
                    self.original_pdf_path = assistivox_pdf_path
                else:
                    self.original_pdf_path = None  # Clear PDF path for markdown files without tags
    
            elif file_path.lower().endswith('.rtf'):
                # Load as rich text
                self.text_editor.setHtml(content)
                content_type = 'html'
            else:
                # Load as plain text
                self.text_editor.setPlainText(content)
                content_type = 'text'
    
            # Update state
            self.current_file_path = file_path
            if not MarkdownHandler.is_markdown_file(file_path) and not ASVXHandler.is_asvx_file(file_path):
                self.original_pdf_path = None  # Clear PDF path for non-markdown/non-asvx files
    
            # Emit signal
            self.fileLoaded.emit(file_path, content_type)
    
            # Update last_open directory in config
            if self.config is not None:
                file_directory = str(Path(file_path).parent)
    
                # Ensure file_settings section exists
                if "file_settings" not in self.config:
                    self.config["file_settings"] = {}
    
                # Update last_open with the directory path
                self.config["file_settings"]["last_open"] = file_directory
    
                # Save config to file
                if hasattr(self, 'assistivox_dir') and self.assistivox_dir:
                    config_path = self.assistivox_dir / "config.json"
                    try:
                        import json
                        with open(config_path, 'w') as f:
                            json.dump(self.config, f, indent=2)
                    except Exception as e:
                        print(f"Error saving config: {e}")
    
        except Exception as e:
            QMessageBox.critical(self.parent(), "Open Error", f"Failed to open document: {str(e)}")
    
    def load_pdf_document(self, file_path):
        """Load a PDF document into the editor using the PDF processing dialog"""
        try:
            from gui.vision.pdf_processing_dialog import PDFProcessingDialog
            from PySide6.QtWidgets import QDialog
    
            # Create and show the PDF processing dialog
            dialog = PDFProcessingDialog(
                pdf_path=file_path,
                config=self.config,
                assistivox_dir=self.assistivox_dir,
                parent=self.parent()
            )
            
            # Show the dialog
            result = dialog.exec()
            
            # If user cancelled, do nothing
            if result != QDialog.Accepted:
                return
            
            # Get the processing settings and page range
            settings = dialog.get_processing_settings()
            start_page, end_page = dialog.get_selected_page_range()
            
            # Process the PDF based on selected method
            if settings["method"] == "extraction":
                # Use docling extraction with page range
                from gui.components.pdf_extraction_dialog import PDFExtractionDialog
                from PySide6.QtWidgets import QDialog
                from gui.components.markdown_handler import MarkdownHandler
                
                # Create extraction dialog with page range
                extraction_dialog = PDFExtractionDialog(file_path, parent=self.parent())
                extraction_dialog.start_page = start_page
                extraction_dialog.end_page = end_page
                
                # Start extraction and show dialog
                extraction_dialog.start_extraction()
                extraction_result = extraction_dialog.exec()
                
                if extraction_result == QDialog.Accepted:
                    # Extraction completed successfully
                    final_asvx = extraction_dialog.get_extracted_text()
                    if final_asvx:
                        # Add asvx PDF tag at the beginning
                        asvx_tag = "{"+f"asvx|pdf:{file_path}"+"}\n\n"
                        final_asvx = asvx_tag + final_asvx
                
                        # Load ASVX content using ASVX handler
                        from gui.components.asvx_handler import ASVXHandler
                        self.text_editor.document().clear()
                        metadata = ASVXHandler.asvx_to_rich_text(self.text_editor.document(), final_asvx)
                        
                        # Set original PDF path from metadata
                        if metadata and 'pdf_path' in metadata:
                            self.original_pdf_path = metadata['pdf_path']
                
                        # Store the original PDF path in document metadata
                        from PySide6.QtGui import QTextDocument
                        self.text_editor.document().setMetaInformation(QTextDocument.DocumentUrl, file_path)

            elif settings["method"] == "ocr":
                # Use OCR processing with page range
                from gui.vision.ocr_dialog import OCRDialog
    
                # Create OCR dialog with page range - it will read settings from config
                ocr_dialog = OCRDialog(
                    pdf_path=file_path,
                    config=self.config,
                    assistivox_dir=self.assistivox_dir,
                    parent=self.parent()
                )
                
                # Set page range
                ocr_dialog.start_page = start_page
                ocr_dialog.end_page = end_page
    
                # Show the OCR progress dialog - it will start processing automatically
                ocr_result = ocr_dialog.exec()
                
                if ocr_result == QDialog.Accepted:
                    # OCR completed successfully
                    final_asvx = ocr_dialog.get_ocr_result()
                    if final_asvx:
                        # Add asvx PDF tag at the beginning
                        asvx_tag = "{"+f"asvx|pdf:{file_path}"+"}\n\n"
                        final_asvx = asvx_tag + final_asvx
                        
                        # Load ASVX content using ASVX handler
                        from gui.components.asvx_handler import ASVXHandler
                        self.text_editor.document().clear()
                        metadata = ASVXHandler.asvx_to_rich_text(self.text_editor.document(), final_asvx)
                        
                        # Set original PDF path from metadata
                        if metadata and 'pdf_path' in metadata:
                            self.original_pdf_path = metadata['pdf_path']

                        # Store the original PDF path in document metadata
                        from PySide6.QtGui import QTextDocument
                        self.text_editor.document().setMetaInformation(QTextDocument.DocumentUrl, file_path)
                        
                        # Signal that file was loaded
                        self.fileLoaded.emit(file_path, 'pdf')

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self.parent(), "PDF Error", f"Failed to process PDF: {str(e)}")

    def save_document(self):
        """Save the current document"""
        if not self.current_file_path:
            return self.save_document_as()

        return self._save_to_file(self.current_file_path)
    
    def save_document_as(self):
        """Save the document with a new filename"""
        # Get the documents directory path
        documents_dir = self.assistivox_dir / "documents" if self.assistivox_dir else Path.home()
        documents_dir.mkdir(exist_ok=True)
    
        # Open file dialog - default to ASVX format
        file_path, _ = QFileDialog.getSaveFileName(
            self.parent(),
            "Save Document",
            str(documents_dir),
            "ASVX Documents (*.asvx);;All Files (*)"
        )

        if not file_path:
            return False

        return self._save_to_file(file_path)

    def save_document_with_dialog(self):
        """Save document using custom dialog for filename input"""
        # Create and show the save dialog
        dialog = SaveFileDialog(self.parent())
        if dialog.exec() == QDialog.Accepted:
            filename = dialog.get_filename()
            if filename:
                # Create documents directory if it doesn't exist
                documents_dir = self.assistivox_dir / "documents" if self.assistivox_dir else Path.home()
                documents_dir.mkdir(exist_ok=True)
                
                # Full path for the file
                file_path = documents_dir / filename
                
                # Save the document
                return self._save_to_file(str(file_path))
        
        return False
    
    def _save_to_file(self, file_path):
        """Save the document to the specified file - always saves as ASVX format"""
        try:
            from gui.components.asvx_handler import ASVXHandler
        
            # Always save as ASVX format
            # Ensure the file has .asvx extension
            if not file_path.lower().endswith('.asvx'):
                file_path = str(Path(file_path).with_suffix('.asvx'))
            
            # Prepare metadata
            metadata = {}
            if self.original_pdf_path:
                metadata['pdf_path'] = self.original_pdf_path
            
            # Convert document to ASVX format
            asvx_content = ASVXHandler.rich_text_to_asvx(self.text_editor.document(), metadata)
            
            # Save to file
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(asvx_content)
    
            # Update state
            self.current_file_path = file_path
    
            # Emit signal
            self.fileSaved.emit(self.text_editor.toPlainText(), file_path)
    
            return True
    
        except Exception as e:
            QMessageBox.critical(self.parent(), "Save Error", f"Failed to save document: {str(e)}")
            return False
    
    def open_original_pdf(self):
        """Open the original PDF in an independent window"""
        if not self.original_pdf_path:
            # Try to get it from the document metadata
            from gui.components.pdf_handler import PDFHandler
            self.original_pdf_path = PDFHandler.get_original_pdf_path(self.text_editor.document())

        if not self.original_pdf_path or not os.path.exists(self.original_pdf_path):
            QMessageBox.information(self.parent(), "Original PDF", "No original PDF file available")
            return

        # Create and show the PDF viewer window
        from gui.components.pdf_handler import PDFViewerWindow

        # Create new window - let the calling code manage window references
        pdf_viewer_window = PDFViewerWindow(self.original_pdf_path, self.parent())
        pdf_viewer_window.show()
        
        return pdf_viewer_window
    
    def get_current_file_path(self):
        """Get the current file path"""
        return self.current_file_path
    
    def get_original_pdf_path(self):
        """Get the original PDF path"""
        return self.original_pdf_path
    
    def set_current_file_path(self, file_path):
        """Set the current file path"""
        self.current_file_path = file_path

    def _parse_assistivox_tags(self, content, file_path):
        """
        Parse assistivox tags from the first line of markdown content
    
        Args:
            content: The markdown file content to parse
            file_path: The path of the file being loaded (for dialog context)
        
        Returns:
            tuple: (pdf_path or None, modified_content or None)
                   modified_content is None if no changes needed,
                   or the content with tag removed if user chose "No"
        """
        if not content:
            return None, None
    
        lines = content.split('\n', 1)  # Split only on first newline
        if not lines:
            return None, None
    
        first_line = lines[0].strip()
    
        # Check for assistivox tag format: {asvx|pdf:/path/to/file.pdf}
        import re
        pattern = r'^\{asvx\|pdf:(.+)\}$'
        match = re.match(pattern, first_line)
    
        if match:
            pdf_path = match.group(1).strip()
        
            # Verify the PDF file exists
            import os
            if os.path.exists(pdf_path) and pdf_path.lower().endswith('.pdf'):
                return pdf_path, None
            else:
                # File doesn't exist - show dialog
                from PySide6.QtWidgets import QMessageBox, QPushButton
                
                msg_box = QMessageBox(self.parent())
                msg_box.setWindowTitle("Missing PDF File")
                msg_box.setText("The linked PDF file does not exist:")
                msg_box.setInformativeText(f"{pdf_path}\n\nLoad the markdown file anyway?")
            
                # Create custom buttons
                yes_button = msg_box.addButton("Yes - Keep the link tag (you can fix the path later)", QMessageBox.YesRole)
                no_button = msg_box.addButton("No - Load without the tag", QMessageBox.NoRole)
            
                # Set focus to No button and enable keyboard shortcut
                msg_box.setDefaultButton(no_button)
            
                # Show dialog and get result
                msg_box.exec()
                clicked_button = msg_box.clickedButton()
                
                if clicked_button == yes_button:
                    # Keep the tag, return None for PDF path (will show error on Alt+O)
                    return None, None
                else:
                    # Remove the tag from content
                    if len(lines) > 1:
                        # Return content without the first line
                        modified_content = lines[1]
                    else:
                        # First line was the only line, return empty content
                        modified_content = ""
                    return None, modified_content
        
        return None, None

    def _convert_horizontal_rules_to_page_breaks(self, content):
        """Convert horizontal rule patterns to numbered PAGE BREAK text"""
        import re

        # Split into lines for processing
        lines = content.split('\n')
        processed_lines = []
        page_break_counter = 0

        for line in lines:
            # Add the original line first
            processed_lines.append(line)

            # Check if line matches 3 hyphens with 0 or more spaces between them
            if re.match(r'^-\s*-\s*-$', line.strip()):
                page_break_counter += 1
                # Insert PAGE BREAK line under the horizontal rule
                processed_lines.append(f'PAGE BREAK {page_break_counter}\n\n')

        return '\n'.join(processed_lines)

