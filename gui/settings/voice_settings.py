# gui/settings/voice_settings.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton, 
    QLabel, QSlider, QListWidget, QListWidgetItem, QWidget,
    QComboBox, QDoubleSpinBox, QGroupBox, QRadioButton, QButtonGroup,
    QSpinBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShortcut, QKeySequence, QFont

import os
import sys
import json

# Get paths for importing model functions
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from install_tts import list_installed_tts_models
    from install_stt import list_installed_models
except ImportError:
    # Fallback if imports fail
    list_installed_tts_models = lambda x: {}
    list_installed_models = lambda x: {}

# Import sentence detector to get available methods
try:
    from gui.nlp.sentence_detector import SentenceDetector
    SENTENCE_DETECTOR_AVAILABLE = True
except ImportError:
    SENTENCE_DETECTOR_AVAILABLE = False

class VoiceSettingsDialog(QDialog):
    """Dialog for configuring voice-related settings (TTS and dictation)"""
    
    # Signal emitted when settings are changed and saved
    voice_settings_changed = Signal()
    
    def __init__(self, config, assistivox_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Voice Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        
        # Store references
        self.config = config
        self.assistivox_dir = assistivox_dir
        
        # Set up layout
        main_layout = QVBoxLayout(self)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Apply button font size to tab widget text
        if 'appearance' in self.config and 'button_font_size' in self.config['appearance']:
            button_font_size = self.config['appearance']['button_font_size']
            font = self.tab_widget.font()
            font.setPointSize(button_font_size)
            self.tab_widget.setFont(font)
        
        # Add TTS settings tab (default active tab)
        self.tts_tab = QWidget()
        self.setup_tts_tab()
        self.tab_widget.addTab(self.tts_tab, "Text to Speech Settings")
        
        # Add dictation settings tab
        self.dictation_tab = QWidget()
        self.setup_dictation_tab()
        self.tab_widget.addTab(self.dictation_tab, "Dictation Settings")
        
        # Add NLP settings tab
        self.nlp_tab = QWidget()
        self.setup_nlp_tab()
        self.tab_widget.addTab(self.nlp_tab, "NLP Settings")
        
        # Buttons
        button_layout = QHBoxLayout()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        cancel_button.setFixedHeight(40)
        
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.accept)
        save_button.setFixedHeight(40)
        save_button.setDefault(True)
        
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(save_button)
        
        main_layout.addLayout(button_layout)
        
        # Add keyboard shortcut for save (Ctrl+Return)
        self.ctrl_return_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.ctrl_return_shortcut.activated.connect(self.accept)
        
        # Apply font settings before loading content
        self.apply_font_settings()
        
        # Load settings
        self.load_settings()
    
    def apply_font_settings(self):
        """Apply font settings from config to all dialog elements"""
        if not self.config or 'appearance' not in self.config:
            return
            
        appearance = self.config['appearance']
        dialog_font_size = appearance.get('dialog_font_size', 11)
        menu_font_size = appearance.get('menu_font_size', 12)
        button_font_size = appearance.get('button_font_size', 12)
        
        # Apply dialog font size to labels and other dialog elements
        for widget in self.findChildren(QLabel):
            font = widget.font()
            font.setPointSize(dialog_font_size)
            widget.setFont(font)
        
        # Apply dialog font size to group boxes
        for widget in self.findChildren(QGroupBox):
            font = widget.font()
            font.setPointSize(dialog_font_size)
            widget.setFont(font)
        
        # Apply menu font size to list widgets and combo boxes
        for widget in self.findChildren(QListWidget):
            font = widget.font()
            font.setPointSize(menu_font_size)
            widget.setFont(font)
        
        for widget in self.findChildren(QComboBox):
            font = widget.font()
            font.setPointSize(menu_font_size)
            widget.setFont(font)
        
        # Apply button font size to buttons
        for widget in self.findChildren(QPushButton):
            font = widget.font()
            font.setPointSize(button_font_size)
            widget.setFont(font)
        
        # Apply dialog font size to other controls
        for widget in self.findChildren(QDoubleSpinBox):
            font = widget.font()
            font.setPointSize(dialog_font_size)
            widget.setFont(font)
            
        # Apply dialog font size to radio buttons
        for widget in self.findChildren(QRadioButton):
            font = widget.font()
            font.setPointSize(dialog_font_size)
            widget.setFont(font)
    
    def setup_tts_tab(self):
        """Set up the Text to Speech settings tab"""
        layout = QVBoxLayout(self.tts_tab)
        
        # TTS Engine selection
        engine_group = QGroupBox("TTS Engine")
        engine_layout = QVBoxLayout()
        
        engine_label = QLabel("Select TTS engine:")
        engine_layout.addWidget(engine_label)
        
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("Piper TTS", "piper")
        self.engine_combo.addItem("Kokoro TTS", "kokoro")
        self.engine_combo.currentIndexChanged.connect(self.update_voice_list)
        engine_layout.addWidget(self.engine_combo)
        
        engine_group.setLayout(engine_layout)
        layout.addWidget(engine_group)
        
        # Voice selection
        voice_group = QGroupBox("Voice Selection")
        voice_layout = QVBoxLayout()
        
        voice_label = QLabel("Select a voice:")
        voice_layout.addWidget(voice_label)
        
        self.voice_list = QListWidget()
        self.voice_list.itemDoubleClicked.connect(self.select_voice)
        self.voice_list.setSelectionMode(QListWidget.SingleSelection)
        voice_layout.addWidget(self.voice_list)
        
        # Add label to show current selection
        self.current_voice_label = QLabel("Currently selected: None")
        if 'appearance' in self.config and 'dialog_font_size' in self.config['appearance']:
            font = self.current_voice_label.font()
            font.setBold(True)
            self.current_voice_label.setFont(font)
        voice_layout.addWidget(self.current_voice_label)
        
        voice_group.setLayout(voice_layout)
        layout.addWidget(voice_group)
        
        # Speed settings
        speed_group = QGroupBox("Speech Speed")
        speed_layout = QVBoxLayout()
        
        speed_description = QLabel("Adjust the speed of speech:")
        speed_layout.addWidget(speed_description)
        
        speed_slider_layout = QHBoxLayout()
        
        speed_min_label = QLabel("Slow")
        speed_slider_layout.addWidget(speed_min_label)
        
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(50, 200)  # 0.5 to 2.0 (x100)
        self.speed_slider.setTickInterval(10)
        self.speed_slider.setTickPosition(QSlider.TicksBelow)
        speed_slider_layout.addWidget(self.speed_slider)
        
        speed_max_label = QLabel("Fast")
        speed_slider_layout.addWidget(speed_max_label)
        
        self.speed_spinner = QDoubleSpinBox()
        self.speed_spinner.setRange(0.5, 2.0)
        self.speed_spinner.setSingleStep(0.05)
        self.speed_spinner.setDecimals(2)
        
        # Apply dialog font size to spinner
        if 'appearance' in self.config and 'dialog_font_size' in self.config['appearance']:
            dialog_font_size = self.config['appearance']['dialog_font_size']
            font = self.speed_spinner.font()
            font.setPointSize(dialog_font_size)
            self.speed_spinner.setFont(font)
            
        speed_slider_layout.addWidget(self.speed_spinner)
        
        speed_layout.addLayout(speed_slider_layout)
        
        # Connect slider and spinner
        self.speed_slider.valueChanged.connect(self.update_speed_spinner)
        self.speed_spinner.valueChanged.connect(self.update_speed_slider)
        
        speed_group.setLayout(speed_layout)
        layout.addWidget(speed_group)
        
        # Docker port settings (for Kokoro)
        docker_group = QGroupBox("Kokoro Docker Settings")
        docker_layout = QHBoxLayout()
        
        docker_layout.addWidget(QLabel("Docker port:"))
        
        self.docker_port_spinner = QSpinBox()
        self.docker_port_spinner.setRange(1024, 65535)
        self.docker_port_spinner.setValue(8880)
        docker_layout.addWidget(self.docker_port_spinner)
        
        docker_group.setLayout(docker_layout)
        layout.addWidget(docker_group)
        
        # Add spacer
        layout.addStretch()
    
    def setup_dictation_tab(self):
        """Set up the Dictation settings tab"""
        layout = QVBoxLayout(self.dictation_tab)
        
        # Engine selection
        engine_group = QGroupBox("Speech Recognition Engine")
        engine_layout = QVBoxLayout()
        
        engine_label = QLabel("Select an engine:")
        engine_layout.addWidget(engine_label)
        
        self.dictation_engine_combo = QComboBox()
        self.dictation_engine_combo.currentIndexChanged.connect(self.update_model_list)
        engine_layout.addWidget(self.dictation_engine_combo)
        
        engine_group.setLayout(engine_layout)
        layout.addWidget(engine_group)
        
        # Model selection
        model_group = QGroupBox("Speech Recognition Model")
        model_layout = QVBoxLayout()
        
        model_label = QLabel("Select a model:")
        model_layout.addWidget(model_label)
        
        self.model_list = QListWidget()
        self.model_list.itemDoubleClicked.connect(self.select_model)
        self.model_list.setSelectionMode(QListWidget.SingleSelection)
        model_layout.addWidget(self.model_list)
        
        # Add label to show current selection
        self.current_model_label = QLabel("Currently selected: None")
        if 'appearance' in self.config and 'dialog_font_size' in self.config['appearance']:
            font = self.current_model_label.font()
            font.setBold(True)
            self.current_model_label.setFont(font)
        model_layout.addWidget(self.current_model_label)
        
        model_group.setLayout(model_layout)
        layout.addWidget(model_group)
        
        # Add spacer
        layout.addStretch()
    
    def setup_nlp_tab(self):
        """Set up the NLP settings tab"""
        layout = QVBoxLayout(self.nlp_tab)
        
        # Sentence boundary detection
        sentence_group = QGroupBox("Sentence Boundary Detection")
        sentence_layout = QVBoxLayout()
        
        sentence_description = QLabel(
            "Choose the method for detecting sentence boundaries during text-to-speech:"
        )
        sentence_layout.addWidget(sentence_description)
        
        # Radio buttons for sentence detection methods
        self.sentence_method_group = QButtonGroup()
        
        self.nupunkt_radio = QRadioButton("nupunkt (Default)")
        self.spacy_radio = QRadioButton("spaCy")
        
        # Set default selection
        self.nupunkt_radio.setChecked(True)
        
        # Add to button group
        self.sentence_method_group.addButton(self.nupunkt_radio, 0)  # Use 0 for nupunkt
        self.sentence_method_group.addButton(self.spacy_radio, 1)    # Use 1 for spacy
        
        # Add to layout
        sentence_layout.addWidget(self.nupunkt_radio)
        sentence_layout.addWidget(self.spacy_radio)
        
        # Check availability and disable if needed
        if SENTENCE_DETECTOR_AVAILABLE:
            # Get available methods from sentence detector
            config_path = os.path.join(self.assistivox_dir, "config.json")
            detector = SentenceDetector(config_path)
            available_methods = detector.get_available_methods()
            
            # Update radio button text with availability
            for method_name, method_desc in available_methods.items():
                if method_name == "nupunkt":
                    self.nupunkt_radio.setText(method_desc)
                    if "Not Available" in method_desc:
                        self.nupunkt_radio.setEnabled(False)
                elif method_name == "spacy":
                    self.spacy_radio.setText(method_desc)
                    if "Not Available" in method_desc:
                        self.spacy_radio.setEnabled(False)
        else:
            # Sentence detector not available, disable options
            self.nupunkt_radio.setEnabled(False)
            self.spacy_radio.setEnabled(False)
            self.nupunkt_radio.setText("nupunkt (Module Not Available)")
            self.spacy_radio.setText("spaCy (Module Not Available)")
        
        sentence_group.setLayout(sentence_layout)
        layout.addWidget(sentence_group)
        
        # Add spacer
        layout.addStretch()
    
    def load_settings(self):
        """Load current settings from config"""
        # Load TTS engine
        if "tts_settings" in self.config:
            engine = self.config["tts_settings"].get("engine", "piper")
            index = self.engine_combo.findData(engine)
            if index >= 0:
                self.engine_combo.setCurrentIndex(index)
        
        # Load TTS speed
        if "tts_settings" in self.config:
            speed = self.config["tts_settings"].get("speed", 1.0)
            try:
                speed = float(speed)
                if speed < 0.5:
                    speed = 0.5
                elif speed > 2.0:
                    speed = 2.0
            except (ValueError, TypeError):
                speed = 1.0
                
            self.speed_spinner.setValue(speed)
            self.update_speed_slider(speed)
        else:
            # Default to 1.0
            self.speed_spinner.setValue(1.0)
            self.update_speed_slider(1.0)
        
        # Load Docker port
        if "tts_settings" in self.config:
            port = self.config["tts_settings"].get("docker_port", 8880)
            self.docker_port_spinner.setValue(port)
        
        # Load sentence boundary method
        if "nlp_settings" in self.config and "sentence_boundaries" in self.config["nlp_settings"]:
            method = self.config["nlp_settings"]["sentence_boundaries"]
            # Handle both old numeric and new string formats
            if isinstance(method, int):
                # Convert old format: 1 -> nupunkt, 2 -> spacy
                if method == 1:
                    self.nupunkt_radio.setChecked(True)
                elif method == 2:
                    self.spacy_radio.setChecked(True)
                else:
                    self.nupunkt_radio.setChecked(True)
            elif isinstance(method, str):
                # New string format
                if method == "nupunkt":
                    self.nupunkt_radio.setChecked(True)
                elif method == "spacy":
                    self.spacy_radio.setChecked(True)
                else:
                    self.nupunkt_radio.setChecked(True)
        else:
            # Default to nupunkt
            self.nupunkt_radio.setChecked(True)
        
        # Populate voice list based on selected engine
        self.update_voice_list()
        
        # Populate engine list and model list
        self.populate_dictation_engine_list()
        
        # Apply font settings again after populating lists
        self.apply_font_settings()
    
    def update_voice_list(self):
        """Update voice list based on selected engine"""
        self.voice_list.clear()
        
        engine = self.engine_combo.currentData()
        
        # Get currently selected voice
        selected_voice = None
        selected_display_name = "None"
        if "tts_models" in self.config and "selected" in self.config["tts_models"]:
            selected_voice = self.config["tts_models"]["selected"]
        
        if engine == "piper":
            # Populate with installed Piper voices
            installed_voices = list_installed_tts_models(str(self.assistivox_dir))
            
            # Add voices to list
            for engine_name, voices in installed_voices.items():
                if engine_name == "piper":
                    for voice in sorted(voices):
                        # Create display name
                        display_name = f"{voice} (piper)"
                        
                        # Create item
                        item = QListWidgetItem(display_name)
                        item.setData(Qt.UserRole, f"piper-{voice}")
                        
                        # Apply menu font size to the item
                        if 'appearance' in self.config and 'menu_font_size' in self.config['appearance']:
                            font = item.font() if hasattr(item, 'font') else self.voice_list.font()
                            font.setPointSize(self.config['appearance']['menu_font_size'])
                            item.setFont(font)
                        
                        # Check if this is the selected voice
                        if selected_voice == f"piper-{voice}":
                            item.setSelected(True)
                            self.voice_list.setCurrentItem(item)
                            selected_display_name = display_name
                        
                        # Add to list
                        self.voice_list.addItem(item)
        
        elif engine == "kokoro":
            # Load Kokoro voices from tts.json
            try:
                tts_json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tts.json")
                with open(tts_json_path, 'r') as f:
                    tts_data = json.load(f)
                
                kokoro_voices = tts_data.get("kokoro_tts_voices", {}).get("voices", {})
                
                # Sort voices by gender and accent
                # Create categories
                voices_by_category = {
                    "US Female": [],
                    "US Male": [],
                    "UK Female": [],
                    "UK Male": []
                }
                
                for voice_id, voice_info in kokoro_voices.items():
                    display_name = voice_info.get("display_name", voice_id)
                    gender = voice_info.get("gender", "unknown")
                    lang_code = voice_info.get("language_code", "en_US")
                    
                    # Determine category
                    if lang_code == "en_US":
                        if gender == "female":
                            voices_by_category["US Female"].append((voice_id, display_name))
                        elif gender == "male":
                            voices_by_category["US Male"].append((voice_id, display_name))
                    elif lang_code == "en_GB":
                        if gender == "female":
                            voices_by_category["UK Female"].append((voice_id, display_name))
                        elif gender == "male":
                            voices_by_category["UK Male"].append((voice_id, display_name))
                
                # Add voices by category
                for category, voice_list in voices_by_category.items():
                    if voice_list:
                        # Add separator
                        separator_item = QListWidgetItem(f"--- {category} ---")
                        separator_item.setFlags(Qt.NoItemFlags)
                        self.voice_list.addItem(separator_item)
                        
                        # Add voices
                        for voice_id, display_name in sorted(voice_list, key=lambda x: x[1]):
                            item = QListWidgetItem(display_name)
                            item.setData(Qt.UserRole, f"kokoro-{voice_id}")
                            
                            # Apply menu font size to the item
                            if 'appearance' in self.config and 'menu_font_size' in self.config['appearance']:
                                font = item.font() if hasattr(item, 'font') else self.voice_list.font()
                                font.setPointSize(self.config['appearance']['menu_font_size'])
                                item.setFont(font)
                            
                            # Check if this is the selected voice
                            if selected_voice == f"kokoro-{voice_id}":
                                item.setSelected(True)
                                self.voice_list.setCurrentItem(item)
                                selected_display_name = display_name
                            
                            self.voice_list.addItem(item)
                
            except Exception as e:
                print(f"Error loading Kokoro voices: {e}")
        
        # Update the current selection label
        self.current_voice_label.setText(f"Currently selected: {selected_display_name}")
    
    def populate_dictation_engine_list(self):
        """Populate the list of available speech recognition engines"""
        self.dictation_engine_combo.clear()
        
        # Get installed STT models
        installed_models = list_installed_models(str(self.assistivox_dir))
        
        # Get currently selected model
        selected_model = None
        selected_model_display = "None"
        if "stt_models" in self.config and "selected" in self.config["stt_models"]:
            selected_model = self.config["stt_models"]["selected"]
            
        # Add engines to combo box
        selected_engine = None
        if selected_model:
            parts = selected_model.split("_")
            if len(parts) >= 2:
                selected_engine = parts[0]
        
        # Add engines to combo
        for engine in sorted(installed_models.keys()):
            self.dictation_engine_combo.addItem(engine.replace("-", " ").title(), engine)
            
            # Select current engine
            if engine == selected_engine:
                idx = self.dictation_engine_combo.findData(engine)
                if idx >= 0:
                    self.dictation_engine_combo.setCurrentIndex(idx)
        
        # Update model list for current engine
        self.update_model_list()
    
    def update_model_list(self):
        """Update the list of models based on selected engine"""
        self.model_list.clear()
        
        # Get current engine
        current_idx = self.dictation_engine_combo.currentIndex()
        if current_idx < 0:
            return
            
        engine = self.dictation_engine_combo.itemData(current_idx)
        
        # Get models for this engine
        installed_models = list_installed_models(str(self.assistivox_dir))
        
        if engine not in installed_models:
            return
            
        # Get currently selected model
        selected_model = None
        selected_model_display = "None"
        if "stt_models" in self.config and "selected" in self.config["stt_models"]:
            selected_model = self.config["stt_models"]["selected"]
        
        # Add models to list
        for model_size in sorted(installed_models[engine]):
            display_name = f"{model_size}"
            item = QListWidgetItem(display_name)
            item.setData(Qt.UserRole, f"{engine}_{model_size}")
            
            # Apply menu font size to the item
            if 'appearance' in self.config and 'menu_font_size' in self.config['appearance']:
                font = item.font() if hasattr(item, 'font') else self.model_list.font()
                font.setPointSize(self.config['appearance']['menu_font_size'])
                item.setFont(font)
            
            # Check if this is the selected model
            if selected_model == f"{engine}_{model_size}":
                item.setSelected(True)
                self.model_list.setCurrentItem(item)
                selected_model_display = f"{engine} {model_size}"
                
            self.model_list.addItem(item)
        
        # Update the current selection label
        self.current_model_label.setText(f"Currently selected: {selected_model_display}")
    
    def update_speed_spinner(self, value):
        """Update speed spinner when slider changes"""
        # Convert slider value (50-200) to spinner value (0.5-2.0)
        spinner_value = value / 100.0
        
        # Block signals to prevent feedback loop
        self.speed_spinner.blockSignals(True)
        self.speed_spinner.setValue(spinner_value)
        self.speed_spinner.blockSignals(False)
    
    def update_speed_slider(self, value):
        """Update speed slider when spinner changes"""
        # Convert spinner value (0.5-2.0) to slider value (50-200)
        slider_value = int(value * 100)
        
        # Block signals to prevent feedback loop
        self.speed_slider.blockSignals(True)
        self.speed_slider.setValue(slider_value)
        self.speed_slider.blockSignals(False)
    
    def select_voice(self, item):
        """Handle voice selection"""
        # Just highlight the item - actual selection happens on save
        self.voice_list.setCurrentItem(item)
        # Update the current selection label immediately for better UX
        self.current_voice_label.setText(f"Currently selected: {item.text()}")
    
    def select_model(self, item):
        """Handle model selection"""
        # Just highlight the item - actual selection happens on save
        self.model_list.setCurrentItem(item)
        # Update the current selection label immediately for better UX
        current_engine = self.dictation_engine_combo.currentText()
        self.current_model_label.setText(f"Currently selected: {current_engine} {item.text()}")
    
    def accept(self):
        """Save settings and close dialog"""
        try:
            # Ensure tts_settings section exists
            if "tts_settings" not in self.config:
                self.config["tts_settings"] = {}
            
            # Save TTS engine
            self.config["tts_settings"]["engine"] = self.engine_combo.currentData()
            
            # Save TTS speed
            self.config["tts_settings"]["speed"] = self.speed_spinner.value()
            
            # Save Docker port
            self.config["tts_settings"]["docker_port"] = self.docker_port_spinner.value()
            
            # Ensure nlp_settings section exists
            if "nlp_settings" not in self.config:
                self.config["nlp_settings"] = {}
            
            # Save sentence boundary method as string
            if self.nupunkt_radio.isChecked():
                self.config["nlp_settings"]["sentence_boundaries"] = "nupunkt"
            elif self.spacy_radio.isChecked():
                self.config["nlp_settings"]["sentence_boundaries"] = "spacy"
            else:
                self.config["nlp_settings"]["sentence_boundaries"] = "nupunkt"  # Default
            
            # Save selected voice
            selected_voice_items = self.voice_list.selectedItems()
            if selected_voice_items:
                voice_id = selected_voice_items[0].data(Qt.UserRole)
                if voice_id:
                    # Ensure tts_models section exists
                    if "tts_models" not in self.config:
                        self.config["tts_models"] = {}
                    
                    self.config["tts_models"]["selected"] = voice_id
            
            # Save selected model
            selected_model_items = self.model_list.selectedItems()
            if selected_model_items:
                model_id = selected_model_items[0].data(Qt.UserRole)
                if model_id:
                    # Ensure stt_models section exists
                    if "stt_models" not in self.config:
                        self.config["stt_models"] = {}
                    
                    self.config["stt_models"]["selected"] = model_id
            
            # Save config to file
            config_path = os.path.join(self.assistivox_dir, "config.json")
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            # Emit signal
            self.voice_settings_changed.emit()
            
            # Close dialog
            super().accept()
            
        except Exception as e:
            print(f"Error saving voice settings: {str(e)}")
            # Still close the dialog even if there's an error
            super().accept()
        
    def keyPressEvent(self, event):
        """Handle key press events for the dialog"""
        # Implement Ctrl+Return shortcut for Save button
        if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
            self.accept()
        else:
            super().keyPressEvent(event)
