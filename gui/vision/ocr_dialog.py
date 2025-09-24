# gui/vision/ocr_dialog.py
import os
import sys
import json
import tempfile
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QProgressBar, QMessageBox, QWidget, QFrame, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QProcess
from PySide6.QtGui import QKeySequence, QShortcut, QFont

try:
    import pdfplumber
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

# OCR imports with fallback
try:
    from doctr.models import ocr_predictor
    from doctr.io import DocumentFile
    DOCTR_AVAILABLE = True
except ImportError:
    DOCTR_AVAILABLE = False

# OCR preset configurations from the example script
OCR_PRESETS = {
    "f": ("db_mobilenet_v3_large", "crnn_mobilenet_v3_small"),
    "b": ("db_resnet34", "sar_resnet31"),
    "a": ("db_resnet50", "master"),
}

PRESET_DESCRIPTIONS = {
    "f": "Quickest, uses least memory; ideal for slow/old machines. May miss complex or small/faint text.",
    "b": "Good speed and accuracy; best for daily use, textbooks, columns, and newsletters.",
    "a": "Best for complex, messy, or academic documents. Slowest, needs more memory/CPU/GPU, but highest OCR accuracy.",
}

PRESET_LABELS = {
    "f": "Fast (Low Resource)",
    "b": "Balanced (Recommended)", 
    "a": "Accurate (High Detail)",
}


class PresetCard(QWidget):
    """Card widget for OCR preset selection"""
    clicked = Signal(str)  # preset key
    
    def __init__(self, preset_key, label, description, is_selected=False):
        super().__init__()
        self.preset_key = preset_key
        self.is_selected = is_selected
        
        self.setFixedHeight(100)
        self.setMinimumWidth(300)
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        
        # Title
        title_label = QLabel(label)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        desc_font = desc_label.font()
        desc_font.setPointSize(10)
        desc_label.setFont(desc_font)
        layout.addWidget(desc_label)

        # Set cursor to indicate the widget is clickable
        self.setCursor(Qt.PointingHandCursor)
        
        # Apply initial styling
        self.update_style()

    def update_style(self):
        """Update the card styling based on selection state"""
        # Ensure cursor is always set to pointing hand
        self.setCursor(Qt.PointingHandCursor)
        
        if self.is_selected:
            # Selected state: thick blue border, keep dark mode colors
            self.setStyleSheet("""
                QWidget {
                    border: 4px solid #0078d4;
                    border-radius: 8px;
                    background-color: #2d2d2d;
                    color: white;
                }
            """)
        else:
            # Unselected state: thin border, dark mode colors
            self.setStyleSheet("""
                QWidget {
                    border: 1px solid #555;
                    border-radius: 6px;
                    background-color: #1e1e1e;
                    color: white;
                }
                QWidget:hover {
                    border: 2px solid #0078d4;
                    background-color: #2d2d2d;
                }
            """)

    def set_selected(self, selected):
        """Set the selection state"""
        self.is_selected = selected
        self.update_style()
        
    def mousePressEvent(self, event):
        """Handle mouse press to emit clicked signal"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.preset_key)
        super().mousePressEvent(event)


class OCRDialog(QDialog):
    """Dialog for OCR processing with preset selection"""
    
    def __init__(self, pdf_path, config, assistivox_dir, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.config = config
        self.assistivox_dir = assistivox_dir
    
        self.setWindowTitle("PDF Processing")
        self.setMinimumSize(500, 400)
        self.setModal(True)
    
        # Initialize required attributes
        self.ocr_result = ""
        self.is_cancelling = False
    
        # Always setup progress UI only - settings come from config
        self.setup_progress_ui_only()
    
        # Add keyboard shortcuts
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.escape_shortcut.activated.connect(self.close)
    
        # Start OCR processing based on config
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, self.start_ocr_from_config)
    
    def setup_progress_ui_only(self):
        """Set up progress UI only (no engine selection)"""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
    
        # Title
        title = QLabel("OCR Processing")
        title.setAlignment(Qt.AlignCenter)
        title_font = title.font()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
    
        # Progress section
        self.progress_widget = QWidget()
        progress_layout = QVBoxLayout(self.progress_widget)
    
        self.progress_header = QLabel("Processing Pages")
        self.progress_header.setAlignment(Qt.AlignCenter)
        progress_font = self.progress_header.font()
        progress_font.setPointSize(12)
        progress_font.setBold(True)
        self.progress_header.setFont(progress_font)
        progress_layout.addWidget(self.progress_header)
    
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        progress_layout.addWidget(self.progress_bar)
    
        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.progress_label)
    
        self.progress_widget.setVisible(True)
        layout.addWidget(self.progress_widget)
    
        layout.addStretch()
    
        # Buttons
        button_layout = QHBoxLayout()
    
        self.back_button = QPushButton("Cancel")
        self.back_button.setMinimumHeight(40)
        self.back_button.clicked.connect(self.reject)
        button_layout.addWidget(self.back_button)
    
        layout.addLayout(button_layout)

    def start_ocr_from_config(self):
        """Start OCR processing based on config settings"""
        # Get settings from config
        pdf_settings = self.config.get("pdf_settings", {})
        engine = pdf_settings.get("ocr_engine", "tesseract")
    
        if engine == "tesseract":
            self.start_tesseract_ocr()
        else:  # doctr
            self.start_doctr_ocr()

    def start_tesseract_ocr(self):
        """Start Tesseract OCR processing"""
        if not TESSERACT_AVAILABLE:
            QMessageBox.critical(
                self, 
                "Tesseract Not Available", 
                "Tesseract OCR is not installed. Please install tesseract and pytesseract."
            )
            return
    
        # Show progress
        self.progress_widget.setVisible(True)
    
        # Start processing using QProcess (not direct call)
        self.start_tesseract_process()

    def start_doctr_ocr(self):
        """Start docTR OCR processing"""
        if not DOCTR_AVAILABLE:
            QMessageBox.critical(
                self,
                "docTR Not Available",
                "The docTR library is not installed. Please run the installation script to install required dependencies."
            )
            return

        # Initialize cancelling flag
        self.is_cancelling = False

        # Show progress
        self.progress_widget.setVisible(True)

        # Add cancel button (only for docTR, matching current pattern)
        if not hasattr(self, 'cancel_button_added'):
            cancel_button = QPushButton("Cancel")
            cancel_button.clicked.connect(self.cancel_ocr)
            self.back_button.setParent(None)  # Remove from layout temporarily

            button_layout = self.layout().itemAt(self.layout().count() - 1).layout()
            button_layout.addWidget(cancel_button)
            button_layout.addWidget(self.back_button)

            self.cancel_button_ocr = cancel_button
            self.cancel_button_added = True

        # Create temporary file for output
        self.temp_output_file = tempfile.mktemp(suffix='.md')

        # Get preset from config (not self.selected_preset)
        pdf_settings = self.config.get("pdf_settings", {})
        preset = pdf_settings.get("doctr_preset", "b")

        # Get models for selected preset
        det_model, rec_model = OCR_PRESETS[preset]

        # Get page range from dialog if available
        start_page = getattr(self, 'start_page', 1)
        end_page = getattr(self, 'end_page', None)
        
        # Create OCR processing script content (working version)
        script_content = f'''
import sys
import tempfile
try:
    from doctr.models import ocr_predictor
    from doctr.io import DocumentFile

    # Load document
    try:
        doc = DocumentFile.from_pdf("{self.pdf_path}")
    except Exception:
        doc = DocumentFile.from_images("{self.pdf_path}")

    total_pages = len(doc)
    start_page = {start_page}
    end_page = {end_page if end_page else 'total_pages'}
    
    # Use page range or full document
    if end_page == 'total_pages':
        end_page = total_pages
        
    # Ensure valid range  
    start_page = max(1, min(start_page, total_pages))
    end_page = max(start_page, min(end_page, total_pages))
    
    page_count = end_page - start_page + 1

    # Report total pages in range
    print(f"TOTAL_PAGES:{{page_count}}")
    sys.stdout.flush()

    # Initialize OCR with specified models
    model = ocr_predictor(det_arch="{det_model}", reco_arch="{rec_model}", pretrained=True)

    # Process pages in range and generate ASVX content
    asvx_parts = []

    for page_idx in range(start_page - 1, end_page):  # Convert to 0-indexed
        # Report progress
        print(f"PAGE_PROGRESS:{{page_idx - (start_page - 1) + 1}}")
        sys.stdout.flush()

        # Add ASVX page tag with actual PDF page number
        actual_page_num = page_idx + 1
        asvx_parts.append("{{"+f"asvx|page|num:{{actual_page_num}}"+"}}\\n\\n")

        # Process single page
        single_page_doc = [doc[page_idx]]
        result = model(single_page_doc)

        # Extract text content
        page_text = ""
        for block in result.pages[0].blocks:
            for line in block.lines:
                line_text = ""
                for word in line.words:
                    line_text += word.value + " "
                page_text += line_text.strip() + "\\n"

        # Add the OCR text content
        asvx_parts.append(page_text.strip())
        
        # Add spacing between pages (except for the last page)
        if page_idx < end_page - 1:
            asvx_parts.append("\\n\\n")

    # Combine all parts into final ASVX content
    final_asvx = "".join(asvx_parts)

    # Write to temporary output file
    with open("{self.temp_output_file}", 'w', encoding='utf-8') as f:
        f.write(final_asvx)

    print("PROCESSING_COMPLETE")
    sys.stdout.flush()

except Exception as e:
    print(f"ERROR:{{str(e)}}")
    sys.stdout.flush()
    sys.exit(1)
'''

        # Write script to temp file
        self.temp_script_file = tempfile.mktemp(suffix='.py')
        with open(self.temp_script_file, 'w') as f:
            f.write(script_content)

        # Start the process - use ocr_process to match current architecture
        self.ocr_process = QProcess(self)
        self.ocr_process.readyReadStandardOutput.connect(self.on_process_output)
        self.ocr_process.finished.connect(self.on_process_finished)
        self.ocr_process.errorOccurred.connect(self.on_process_error)

        # Initialize progress tracking
        self.total_pages = 0

        self.ocr_process.start(sys.executable, [self.temp_script_file])

        self.progress_label.setText("Starting docTR OCR processing...")
        self.progress_bar.setValue(0)

    def on_process_output(self):
        """Handle process output for progress updates"""
        # Check which process is active
        active_process = None
        if hasattr(self, 'ocr_process') and self.ocr_process and self.ocr_process.state() == QProcess.Running:
            active_process = self.ocr_process
        elif hasattr(self, 'doctr_process') and self.doctr_process and self.doctr_process.state() == QProcess.Running:
            active_process = self.doctr_process
        
        if not active_process:
            return

        data = active_process.readAllStandardOutput()
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

            elif line.startswith('PAGE_PROGRESS:') or line.startswith('PROGRESS:'):
                try:
                    page_num = int(line.split(':')[1])
                    self.progress_bar.setValue(page_num)
                    self.progress_label.setText(f"{page_num} of {self.total_pages} pages")
                    self.progress_header.setText(f"Processing page {page_num} of {self.total_pages}...")
                except ValueError:
                    pass
    
            elif line.startswith('PROCESSING_COMPLETE') or line.startswith('COMPLETED'):
                self.progress_bar.setValue(self.total_pages)
                self.progress_label.setText("Processing complete!")
                self.progress_header.setText("OCR complete!")

    def on_process_finished(self, exit_code, exit_status):
        """Handle process completion"""
        # If we're cancelling, don't show error messages
        if self.is_cancelling:
            return

        if exit_code == 0 and exit_status == QProcess.NormalExit:
            # Process completed successfully, read the result
            try:
                with open(self.temp_output_file, 'r', encoding='utf-8') as f:
                    self.ocr_result = f.read()
    
                self.progress_header.setText("OCR complete!")
                self.progress_label.setText("Processing complete!")
                
                # Clean up temporary files
                self.cleanup_temp_files()
                
                # Close dialog with success
                self.accept()
                
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "OCR Error",
                    f"Failed to read OCR result: {str(e)}"
                )
                self.cleanup_temp_files()
                self.reject()
        else:
            # Process failed
            error_message = "OCR process failed"
            if hasattr(self, 'ocr_process') and self.ocr_process:
                stderr_data = self.ocr_process.readAllStandardError()
                if stderr_data:
                    error_message = bytes(stderr_data).decode('utf-8')
            
            QMessageBox.critical(
                self,
                "OCR Error",
                f"OCR processing failed: {error_message}"
            )
            self.cleanup_temp_files()
            self.reject()

    def cleanup_temp_files(self):
        """Clean up temporary files"""
        import os
        try:
            if hasattr(self, 'temp_output_file') and os.path.exists(self.temp_output_file):
                os.remove(self.temp_output_file)
        except:
            pass
        try:
            if hasattr(self, 'temp_script_file') and os.path.exists(self.temp_script_file):
                os.remove(self.temp_script_file)
        except:
            pass

    def start_tesseract_process(self):
        """Start Tesseract OCR processing using external process"""
        # Create temporary file for output
        self.temp_output_file = tempfile.mktemp(suffix='.txt')

        # Get page range from dialog if available
        start_page = getattr(self, 'start_page', 1)
        end_page = getattr(self, 'end_page', None)
        
        # Create OCR script content
        script_content = f'''
import sys
import tempfile
import os
try:
    import pdfplumber
    import pytesseract
    from PIL import Image
    
    pdf_path = r"{self.pdf_path}"
    output_file = r"{self.temp_output_file}"
    start_page = {start_page}
    end_page = {end_page if end_page else 'None'}
    
    with pdfplumber.open(pdf_path) as pdf:
        num_pages = len(pdf.pages)
        
        # Use page range or full document
        if end_page is None:
            end_page = num_pages
        
        # Ensure valid range
        start_page = max(1, min(start_page, num_pages))
        end_page = max(start_page, min(end_page, num_pages))
        
        page_count = end_page - start_page + 1
        print(f"TOTAL_PAGES:{{page_count}}")
        sys.stdout.flush()
        
        # Build ASVX content
        asvx_parts = []
        
        for i in range(start_page - 1, end_page):  # Convert to 0-indexed
            print(f"PAGE_PROGRESS:{{i - (start_page - 1) + 1}}")
            sys.stdout.flush()
            
            # Add ASVX page tag with actual PDF page number (i + 1)
            actual_page_num = i + 1
            asvx_parts.append("{{"+f"asvx|page|num:{{actual_page_num}}"+"}}\\n\\n")
            
            page = pdf.pages[i]
            page_image = page.to_image(resolution=300).original
            text = pytesseract.image_to_string(page_image)
            
            # Add the OCR text content
            asvx_parts.append(text.strip())
            
            # Add spacing between pages (except for the last page)
            if i < end_page - 1:
                asvx_parts.append("\\n\\n")
        
        # Combine all parts into final ASVX content
        final_asvx = "".join(asvx_parts)
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(final_asvx)
        
        print("PROCESSING_COMPLETE")
        sys.stdout.flush()
        
except Exception as e:
    print(f"ERROR: {{str(e)}}")
    sys.exit(1)
'''

        # Write script to temporary file
        self.temp_script_file = tempfile.mktemp(suffix='.py')
        with open(self.temp_script_file, 'w', encoding='utf-8') as f:
            f.write(script_content)

        # Create and start process
        self.ocr_process = QProcess(self)
        self.ocr_process.finished.connect(self.on_process_finished)
        self.ocr_process.errorOccurred.connect(self.on_process_error)
        self.ocr_process.readyReadStandardOutput.connect(self.on_process_output)
    
        # Initialize progress tracking
        self.total_pages = 0
    
        # Start the process
        self.ocr_process.start(sys.executable, [self.temp_script_file])

    def on_process_error(self, error):
        """Handle process error"""
        # If we're cancelling, don't show error messages
        if self.is_cancelling:
            return
    
        self.on_ocr_error(f"Process error: {error}")
    
    def cancel_ocr(self):
        """Cancel the OCR process"""
        # Set cancelling flag to prevent error dialogs
        self.is_cancelling = True

        # Handle Tesseract process
        if hasattr(self, 'ocr_process') and self.ocr_process and self.ocr_process.state() == QProcess.Running:
            self.progress_header.setText("Cancelling...")
            # Kill the process
            self.ocr_process.kill()
            self.ocr_process.waitForFinished(2000)  # Wait up to 2 seconds

        # Handle docTR process
        if hasattr(self, 'doctr_process') and self.doctr_process and self.doctr_process.state() == QProcess.Running:
            self.progress_header.setText("Cancelling...")
            # Disable cancel button if it exists (only for docTR)
            if hasattr(self, 'cancel_button_ocr'):
                self.cancel_button_ocr.setEnabled(False)
            # Kill the process
            self.doctr_process.kill()
            self.doctr_process.waitForFinished(2000)  # Wait up to 2 seconds

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
    
    def get_ocr_result(self):
        """Get the OCR result text"""
        return getattr(self, 'ocr_result', None)

    def on_ocr_error(self, error_message):
        """Handle OCR error"""
        # If we're cancelling, don't show error messages
        if self.is_cancelling:
            return

        self.progress_header.setText("OCR failed")

        # Clean up
        self.cleanup_temp_files()

        # Show error and close
        QMessageBox.critical(self, "OCR Error", f"Failed to perform OCR:\n{error_message}")
        self.reject()

    def closeEvent(self, event):
        """Handle dialog close event"""
        if hasattr(self, 'ocr_process') and self.ocr_process and self.ocr_process.state() == QProcess.Running:
            # Cancel OCR if running
            self.cancel_ocr()
        event.accept()
    
    def reject(self):
        """Handle dialog rejection (Escape, X button)"""
        if hasattr(self, 'ocr_process') and self.ocr_process and self.ocr_process.state() == QProcess.Running:
            self.cancel_ocr()
        else:
            self.cleanup_temp_files()
            super().reject()

