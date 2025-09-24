# gui/vision/pdf_processing_dialog.py
import json
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QWidget, QCheckBox, QFrame, QLineEdit
)
from PySide6.QtCore import Qt, Signal, QRegularExpression
from PySide6.QtGui import QFont, QRegularExpressionValidator

class PDFProcessingDialog(QDialog):
    """Dialog for selecting PDF processing method and options"""
    
    def __init__(self, pdf_path, config, assistivox_dir, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.config = config
        self.assistivox_dir = assistivox_dir
        
        # Load settings from config
        self.processing_method = self.get_processing_method()
        self.ocr_engine = self.get_ocr_engine()
        self.doctr_preset = self.get_doctr_preset()
        
        self.setup_ui()
        self.load_settings()
        
    def setup_ui(self):
        """Set up the user interface"""
        self.setWindowTitle("PDF Processing Options")
        self.setModal(True)
        self.resize(400, 300)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # Title
        title_label = QLabel("Choose how to process this PDF:")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # Page range selection
        page_range_widget = QWidget()
        page_range_layout = QVBoxLayout(page_range_widget)
        page_range_layout.setContentsMargins(0, 0, 0, 10)
        
        page_range_label = QLabel("Page Range:")
        page_range_label.setFont(title_font)
        page_range_layout.addWidget(page_range_label)
        
        range_input_layout = QHBoxLayout()
        range_input_layout.addWidget(QLabel("From page:"))
        
        self.start_page_input = QLineEdit()
        self.start_page_input.setMaximumWidth(60)
        self.start_page_input.setText("1")
        # Only allow digits
        from PySide6.QtGui import QRegularExpressionValidator
        from PySide6.QtCore import QRegularExpression
        digit_validator = QRegularExpressionValidator(QRegularExpression(r'^[1-9]\d*$'))
        self.start_page_input.setValidator(digit_validator)
        range_input_layout.addWidget(self.start_page_input)
        
        range_input_layout.addWidget(QLabel("to page:"))
        
        self.end_page_input = QLineEdit()
        self.end_page_input.setMaximumWidth(60)
        self.end_page_input.setText("1")
        self.end_page_input.setValidator(digit_validator)
        range_input_layout.addWidget(self.end_page_input)
        
        range_input_layout.addStretch()
        page_range_layout.addLayout(range_input_layout)
        
        layout.addWidget(page_range_widget)
        
        # Initialize page count and set default range
        self.total_pages = 1
        self.get_pdf_page_count()
        
        # Main processing method options
        self.method_checkboxes = {}
        
        # Extract text option
        extract_checkbox = QCheckBox("Extract the text")
        extract_checkbox.clicked.connect(lambda: self.on_method_selected("extraction"))
        self.method_checkboxes["extraction"] = extract_checkbox
        layout.addWidget(extract_checkbox)
        
        # OCR option
        ocr_checkbox = QCheckBox("Scan the text with OCR")
        ocr_checkbox.clicked.connect(lambda: self.on_method_selected("ocr"))
        self.method_checkboxes["ocr"] = ocr_checkbox
        layout.addWidget(ocr_checkbox)
        
        # OCR engine options (initially hidden)
        self.ocr_options_widget = QWidget()
        ocr_options_layout = QVBoxLayout(self.ocr_options_widget)
        ocr_options_layout.setContentsMargins(30, 10, 0, 0)  # Indent OCR options
        
        self.engine_checkboxes = {}
        
        # Tesseract option
        tesseract_checkbox = QCheckBox("Tesseract")
        tesseract_checkbox.clicked.connect(lambda: self.on_engine_selected("tesseract"))
        self.engine_checkboxes["tesseract"] = tesseract_checkbox
        ocr_options_layout.addWidget(tesseract_checkbox)
        
        # docTR option
        doctr_checkbox = QCheckBox("docTR")
        doctr_checkbox.clicked.connect(lambda: self.on_engine_selected("doctr"))
        self.engine_checkboxes["doctr"] = doctr_checkbox
        ocr_options_layout.addWidget(doctr_checkbox)
        
        # docTR preset options (initially hidden)
        self.preset_options_widget = QWidget()
        preset_options_layout = QVBoxLayout(self.preset_options_widget)
        preset_options_layout.setContentsMargins(60, 10, 0, 0)  # Further indent preset options
        
        self.preset_checkboxes = {}
        
        # Preset descriptions
        preset_descriptions = {
            "f": "Quickest, uses least memory; ideal for slow/old machines. May miss complex or small/faint text.",
            "b": "Good speed and accuracy; best for daily use, textbooks, columns, and newsletters.",
            "a": "Best for complex, messy, or academic documents. Slowest, needs more memory/CPU/GPU, but highest OCR accuracy."
        }
        
        for preset_key in ["f", "b", "a"]:
            preset_checkbox = QCheckBox(f"Preset {preset_key.upper()}: {preset_descriptions[preset_key]}")
            preset_checkbox.clicked.connect(lambda checked, key=preset_key: self.on_preset_selected(key))
            self.preset_checkboxes[preset_key] = preset_checkbox
            preset_options_layout.addWidget(preset_checkbox)
        
        self.preset_options_widget.setVisible(False)
        ocr_options_layout.addWidget(self.preset_options_widget)
        
        self.ocr_options_widget.setVisible(False)
        layout.addWidget(self.ocr_options_widget)
        
        # Spacer
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.process_button = QPushButton("Process PDF")
        self.process_button.clicked.connect(self.accept)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.process_button)
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
    def get_processing_method(self):
        """Get processing method from config"""
        pdf_settings = self.config.get("pdf_settings", {})
        return pdf_settings.get("processing_method", "extraction")
    
    def get_ocr_engine(self):
        """Get OCR engine from config"""
        pdf_settings = self.config.get("pdf_settings", {})
        return pdf_settings.get("ocr_engine", "tesseract")
    
    def get_doctr_preset(self):
        """Get docTR preset from config"""
        pdf_settings = self.config.get("pdf_settings", {})
        return pdf_settings.get("doctr_preset", "b")
    
    def save_settings(self):
        """Save settings to config"""
        if "pdf_settings" not in self.config:
            self.config["pdf_settings"] = {}
        
        self.config["pdf_settings"]["processing_method"] = self.processing_method
        self.config["pdf_settings"]["ocr_engine"] = self.ocr_engine
        self.config["pdf_settings"]["doctr_preset"] = self.doctr_preset
        
        # Save config file
        config_path = self.assistivox_dir / "config.json"
        with open(config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def load_settings(self):
        """Load settings and update UI"""
        # Set processing method
        for method, checkbox in self.method_checkboxes.items():
            checkbox.setChecked(method == self.processing_method)
        
        # Show/hide OCR options based on method
        self.ocr_options_widget.setVisible(self.processing_method == "ocr")
        
        if self.processing_method == "ocr":
            # Set OCR engine
            for engine, checkbox in self.engine_checkboxes.items():
                checkbox.setChecked(engine == self.ocr_engine)
            
            # Show/hide preset options based on engine
            self.preset_options_widget.setVisible(self.ocr_engine == "doctr")
            
            if self.ocr_engine == "doctr":
                # Set preset
                for preset, checkbox in self.preset_checkboxes.items():
                    checkbox.setChecked(preset == self.doctr_preset)
    
    def on_method_selected(self, method):
        """Handle processing method selection"""
        self.processing_method = method
        
        # Uncheck all other methods
        for m, checkbox in self.method_checkboxes.items():
            checkbox.setChecked(m == method)
        
        # Show/hide OCR options
        self.ocr_options_widget.setVisible(method == "ocr")
        
        # When OCR options are shown, reload the saved settings
        if method == "ocr":
            # Reload OCR engine from config and update checkboxes
            current_engine = self.get_ocr_engine()
            for engine, checkbox in self.engine_checkboxes.items():
                checkbox.setChecked(engine == current_engine)
            
            # Show/hide preset options based on current engine
            self.preset_options_widget.setVisible(current_engine == "doctr")
            
            # If docTR is selected, also load the preset settings
            if current_engine == "doctr":
                current_preset = self.get_doctr_preset()
                for preset, checkbox in self.preset_checkboxes.items():
                    checkbox.setChecked(preset == current_preset)
    
    def on_engine_selected(self, engine):
        """Handle OCR engine selection"""
        self.ocr_engine = engine
        
        # Uncheck all other engines
        for e, checkbox in self.engine_checkboxes.items():
            checkbox.setChecked(e == engine)
        
        # Show/hide preset options
        self.preset_options_widget.setVisible(engine == "doctr")
        
        # If switching to docTR, load the saved preset settings
        if engine == "doctr":
            current_preset = self.get_doctr_preset()
            for preset, checkbox in self.preset_checkboxes.items():
                checkbox.setChecked(preset == current_preset)

    def on_preset_selected(self, preset):
        """Handle preset selection"""
        self.doctr_preset = preset
        
        # Uncheck all other presets
        for p, checkbox in self.preset_checkboxes.items():
            checkbox.setChecked(p == preset)
    
    def accept(self):
        """Accept dialog and save settings including page range"""
        # Validate page range before accepting
        start_page, end_page = self.get_page_range()
        
        # Save settings
        self.save_settings()
        
        # Store page range for retrieval
        self.page_range = (start_page, end_page)
        
        super().accept()
    
    def get_processing_settings(self):
        """Get the current processing settings"""
        return {
            "method": self.processing_method,
            "engine": self.ocr_engine,
            "preset": self.doctr_preset
        }

    def get_pdf_page_count(self):
        """Get PDF page count using pdfplumber and set default range"""
        try:
            import pdfplumber
            with pdfplumber.open(self.pdf_path) as pdf:
                self.total_pages = len(pdf.pages)
                self.start_page_input.setText("1")
                self.end_page_input.setText(str(self.total_pages))
        except Exception:
            # Fallback - keep default of 1 page
            self.total_pages = 1
            self.start_page_input.setText("1")
            self.end_page_input.setText("1")
    
    def get_page_range(self):
        """Get and validate the selected page range"""
        try:
            start_page = int(self.start_page_input.text()) if self.start_page_input.text() else 1
            end_page = int(self.end_page_input.text()) if self.end_page_input.text() else self.total_pages
            
            # Validate range
            if start_page < 1 or end_page < 1 or start_page > self.total_pages or end_page > self.total_pages or start_page > end_page:
                # Reset to default range
                self.start_page_input.setText("1")
                self.end_page_input.setText(str(self.total_pages))
                return 1, self.total_pages
            
            return start_page, end_page
        except ValueError:
            # Reset to default range on invalid input
            self.start_page_input.setText("1")
            self.end_page_input.setText(str(self.total_pages))
            return 1, self.total_pages

    def get_selected_page_range(self):
        """Get the selected page range"""
        if hasattr(self, 'page_range'):
            return self.page_range
        return 1, self.total_pages
