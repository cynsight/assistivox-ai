# gui/components/pdf_extraction_dialog.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QWidget, QProgressBar
)
from PySide6.QtCore import Qt, QProcess, Signal
from PySide6.QtGui import QShortcut, QKeySequence, QFont
import sys
import tempfile
import os


class PDFExtractionDialog(QDialog):
    """Dialog for PDF extraction with cancellation using QProcess"""
    
    def __init__(self, pdf_path, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.extraction_process = None
        self.extracted_text = ""
        self.temp_output_file = None
        self.is_cancelling = False  # Track if we're intentionally cancelling
        self.setup_ui()
        self.setup_connections()
        
    def setup_ui(self):
        """Set up the dialog UI"""
        self.setWindowTitle("Extracting PDF Text")
        self.setMinimumWidth(400)
        self.setMinimumHeight(150)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # Title
        title = QLabel("Extracting PDF Text")
        title.setAlignment(Qt.AlignCenter)
        title_font = title.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Status message
        self.status_label = QLabel("Processing document...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Instructions
        self.instruction_label = QLabel("Press Escape to cancel")
        self.instruction_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.instruction_label)

        # Progress bar (initially hidden)
        self.progress_widget = QWidget()
        progress_layout = QVBoxLayout(self.progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("Starting...")
        self.progress_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.progress_label)
        
        self.progress_widget.setVisible(False)  # Hidden initially
        layout.addWidget(self.progress_widget)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_extraction)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
    def setup_connections(self):
        """Set up signal connections and shortcuts"""
        # Add Escape shortcut
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.escape_shortcut.activated.connect(self.cancel_extraction)
        
    def start_extraction(self):
        """Start the PDF extraction process using external Python process"""
        # Create temporary file for output
        self.temp_output_file = tempfile.mktemp(suffix='.md')

        # Get page range from dialog if available
        start_page = getattr(self, 'start_page', 1)
        end_page = getattr(self, 'end_page', None)
        
        # Create extraction script content with progress reporting
        script_content = f'''
import sys
import tempfile

try:
    from pypdf import PdfReader
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import PdfFormatOption
    
    # Get PDF page count using pypdf
    reader = PdfReader("{self.pdf_path}")
    num_pages = len(reader.pages)
    
    start_page = {start_page}
    end_page = {end_page if end_page else 'num_pages'}
    
    # Use page range or full document
    if end_page == 'num_pages':
        end_page = num_pages
        
    # Ensure valid range
    start_page = max(1, min(start_page, num_pages))
    end_page = max(start_page, min(end_page, num_pages))

    page_count = end_page - start_page + 1

    # Report total pages in range
    print(f"TOTAL_PAGES:{{page_count}}")
    sys.stdout.flush()

    # Set up pipeline options
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.do_cell_matching = True
    
    # Create converter with pipeline options
    doc_converter = DocumentConverter(
        format_options={{
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }}
    )
    
    # Extract each page separately and build ASVX content
    asvx_parts = []
    
    for page_num in range(start_page, end_page + 1):  # Docling is 1-indexed
        # Add ASVX page tag with actual PDF page number
        asvx_parts.append("{{"+f"asvx|page|num:{{page_num}}"+"}}\\n\\n")
        
        result = doc_converter.convert("{self.pdf_path}", page_range=(page_num, page_num))
        md_text = result.document.export_to_markdown()
        
        # Add the page content
        asvx_parts.append(md_text)
        
        # Add spacing between pages (except for the last page)
        if page_num < end_page:
            asvx_parts.append("\\n\\n")
        
        # Report progress after each page
        print(f"PAGE_COMPLETE:{{page_num - start_page + 1}}")
        sys.stdout.flush()
    
    # Combine all parts into final ASVX content
    final_asvx = "".join(asvx_parts)
    
    # Write result to temp file
    with open("{self.temp_output_file}", "w", encoding="utf-8") as f:
        f.write(final_asvx)
    
    print("SUCCESS")
    
except Exception as e:
    print(f"ERROR: {{str(e)}}")
    sys.exit(1)
'''

        # Write script to temporary file
        self.temp_script_file = tempfile.mktemp(suffix='.py')
        with open(self.temp_script_file, 'w', encoding='utf-8') as f:
            f.write(script_content)
    
        # Create and start process
        self.extraction_process = QProcess(self)
        self.extraction_process.finished.connect(self.on_process_finished)
        self.extraction_process.errorOccurred.connect(self.on_process_error)
        self.extraction_process.readyReadStandardOutput.connect(self.on_process_output)
    
        # Initialize progress tracking
        self.total_pages = 0
        self.completed_pages = 0
        
        # Start the process
        self.extraction_process.start(sys.executable, [self.temp_script_file])
        self.status_label.setText("Starting extraction...")
        
        # Show progress bar
        self.progress_widget.setVisible(True)

    def on_process_finished(self, exit_code, exit_status):
        """Handle process completion"""
        # If we're cancelling, don't show error messages
        if self.is_cancelling:
            return
            
        if exit_code == 0 and exit_status == QProcess.NormalExit:
            # Process completed successfully, read the result
            try:
                with open(self.temp_output_file, 'r', encoding='utf-8') as f:
                    self.extracted_text = f.read()
                
                self.status_label.setText("Extraction complete!")
                
                # Clean up temp files
                self.cleanup_temp_files()
                
                # Close dialog with success
                self.accept()
                
            except Exception as e:
                self.on_extraction_error(f"Failed to read extraction result: {str(e)}")
        else:
            self.on_extraction_error("PDF extraction process failed")
    
    def on_process_error(self, error):
        """Handle process error"""
        # If we're cancelling, don't show error messages
        if self.is_cancelling:
            return
            
        self.on_extraction_error(f"Process error: {error}")
    
    def on_extraction_error(self, error_message):
        """Handle extraction error"""
        # If we're cancelling, don't show error messages
        if self.is_cancelling:
            return
            
        self.status_label.setText("Extraction failed")
        
        # Clean up
        self.cleanup_temp_files()
        
        # Show error and close
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "PDF Extraction Error", f"Failed to extract PDF text:\n{error_message}")
        self.reject()
    
    def cancel_extraction(self):
        """Cancel the extraction process"""
        # Set cancelling flag to prevent error dialogs
        self.is_cancelling = True

        # Hide progress bar
        self.progress_widget.setVisible(False)
        
        if self.extraction_process and self.extraction_process.state() == QProcess.Running:
            self.status_label.setText("Cancelling...")
            self.instruction_label.setText("Stopping extraction...")
            self.cancel_button.setEnabled(False)
            
            # Kill the process
            self.extraction_process.kill()
            self.extraction_process.waitForFinished(2000)  # Wait up to 2 seconds
        
        # Clean up and close
        self.cleanup_temp_files()
        self.reject()
    
    def cleanup_temp_files(self):
        """Clean up temporary files"""
        if hasattr(self, 'temp_output_file') and self.temp_output_file and os.path.exists(self.temp_output_file):
            try:
                os.unlink(self.temp_output_file)
            except:
                pass
                
        if hasattr(self, 'temp_script_file') and self.temp_script_file and os.path.exists(self.temp_script_file):
            try:
                os.unlink(self.temp_script_file)
            except:
                pass
    
    def get_extracted_text(self):
        """Get the extracted text"""
        return self.extracted_text
    
    def closeEvent(self, event):
        """Handle dialog close event"""
        if self.extraction_process and self.extraction_process.state() == QProcess.Running:
            # Cancel extraction if running
            self.cancel_extraction()
        event.accept()
    
    def reject(self):
        """Handle dialog rejection (Escape, X button)"""
        if self.extraction_process and self.extraction_process.state() == QProcess.Running:
            self.cancel_extraction()
        else:
            self.cleanup_temp_files()
            super().reject()

    def on_process_output(self):
        """Handle process output for progress updates"""
        if not self.extraction_process:
            return
            
        data = self.extraction_process.readAllStandardOutput()
        output = bytes(data).decode('utf-8')
        
        for line in output.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('TOTAL_PAGES:'):
                try:
                    self.total_pages = int(line.split(':')[1])
                    self.progress_bar.setRange(0, self.total_pages)
                    self.progress_label.setText(f"0 of {self.total_pages} pages")
                except ValueError:
                    pass
                    
            elif line.startswith('PAGE_COMPLETE:'):
                try:
                    page_num = int(line.split(':')[1])
                    self.completed_pages = page_num
                    self.progress_bar.setValue(page_num)
                    self.progress_label.setText(f"{page_num} of {self.total_pages} pages")
                    self.status_label.setText(f"Processing page {page_num} of {self.total_pages}...")
                except ValueError:
                    pass
