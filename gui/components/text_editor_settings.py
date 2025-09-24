# gui/components/text_editor_settings.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QGroupBox, QCheckBox, QSpinBox,
    QStackedWidget, QSlider, QDoubleSpinBox, QListWidget,
    QListWidgetItem, QRadioButton, QButtonGroup, QWidget,
    QComboBox, QProgressDialog, QMessageBox, QScrollArea
)
from PySide6.QtCore import Qt, Signal, QProcess, QObject
from PySide6.QtGui import QKeySequence, QShortcut
import os
import sys
import json
import requests
import zipfile
import tempfile

from gui.tts.tts_manager import TTSManager

# Import model information
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Build MODEL_MAP from tts.json and define list_installed_tts_models locally
def load_model_map():
    """Load MODEL_MAP from tts.json"""
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tts_json_path = os.path.join(current_dir, "tts.json")

    model_map = {}
    try:
        with open(tts_json_path, 'r') as f:
            tts_data = json.load(f)

        # Extract piper voices
        piper_voices = tts_data.get("piper_tts_voices", {}).get("voices", {})
        if piper_voices:
            model_map["piper"] = piper_voices

        return model_map
    except Exception as e:
        print(f"Error loading tts.json: {e}")
        return {}

def list_installed_tts_models(base_path):
    """List installed TTS models"""
    tts_models_path = os.path.join(base_path, "tts-models")
    model_groups = {}
    if not os.path.exists(tts_models_path):
        return model_groups

    for engine in os.listdir(tts_models_path):
        engine_path = os.path.join(tts_models_path, engine)
        if not os.path.isdir(engine_path):
            continue
        models = set()
        for model_dir in os.listdir(engine_path):
            # Check if this is a directory
            model_dir_path = os.path.join(engine_path, model_dir)
            if not os.path.isdir(model_dir_path):
                continue
            # we expect the voice name (e.g., "amy", "bryce")
            nickname = model_dir
            models.add(nickname)
        model_groups[engine] = sorted(models)
    return model_groups

#try:
#    from install_stt import list_installed_models
#except ImportError:
#    list_installed_models = lambda x: {}

# Import sentence detector to get available methods
try:
    from gui.nlp.sentence_detector import SentenceDetector
    SENTENCE_DETECTOR_AVAILABLE = True
except ImportError:
    SENTENCE_DETECTOR_AVAILABLE = False


class EditorSettingsDialog(QDialog):
    """Main settings dialog with menu-based navigation"""

    settingsChanged = Signal(dict)  # Signal emitted when settings are changed

    # Voice test text
    VOICE_TEST_TEXT = ("Welcome to Assistivox AI, your voice-enabled productivity suite. "
                      "This AI-powered reading and writing assistant provides powerful local AI assistance with advanced accessibility features.")

    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        # Get references from parent
        self.main_window = parent.main_window if hasattr(parent, 'main_window') else parent
        self.config = self.main_window.config if hasattr(self.main_window, 'config') else {}
        self.assistivox_dir = self.main_window.assistivox_dir if hasattr(self.main_window, 'assistivox_dir') else None

        # Voice testing audio playback tracking
        self._test_audio_thread = None
        self._test_audio_stop_requested = False

        # Store current settings
        self.settings = current_settings.copy() if current_settings else {
            "show_toolbar": True,
            "show_line_numbers": False,
            "default_zoom": 100
        }

        # Navigation stack for ESC key functionality
        self.navigation_stack = []

        # Set up layout
        self.main_layout = QVBoxLayout(self)

        # Create stacked widget for different pages
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)

        # Create pages
        self.create_main_menu_page()                    # Index 0
        self.create_tts_settings_page()                 # Index 1
        self.create_piper_settings_page()               # Index 2
        self.create_faster_whisper_settings_page()      # Index 3 (RENAMED from create_dictation_settings_page)
        self.create_other_settings_page()               # Index 4
        self.create_kokoro_settings_page()              # Index 5
        self.create_dictation_engine_selection_page()   # Index 6 (NEW)
        self.create_vosk_settings_page()              # Index 7 (NEW)

        # Buttons at bottom
        button_layout = QHBoxLayout()

        self.close_button = QPushButton("â†� Back")
        self.close_button.clicked.connect(self.go_back)
        self.close_button.setFixedHeight(40)
        self.close_button.setDefault(True)

        button_layout.addWidget(self.close_button)

        self.main_layout.addLayout(button_layout)

        # Add keyboard shortcuts
        self.setup_shortcuts()

        # Show main menu
        self.show_page(0)

    def reload_config_from_disk(self):
        """Reload config from disk to ensure we have the latest saved values"""
        if self.assistivox_dir:
            config_path = self.assistivox_dir / "config.json"
            try:
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        self.config = json.load(f)
            except Exception as e:
                print(f"Error reloading config: {str(e)}")

    def save_config_immediately(self):
        """Save config to disk immediately"""
        if self.assistivox_dir:
            config_path = self.assistivox_dir / "config.json"
            try:
                with open(config_path, 'w') as f:
                    json.dump(self.config, f, indent=2)
            except Exception as e:
                print(f"Error saving config: {str(e)}")

    def setup_auto_save_connections(self):
        """Set up auto-save connections for all controls"""
        # Speed controls (will be connected when TTS page is shown)
        pass

    def setup_vosk_toggle_connections(self):
        """Connect Vosk toggles to auto-save"""
        if hasattr(self, 'show_partial_text_toggle'):
            self.show_partial_text_toggle.toggled.connect(self.on_vosk_settings_changed)

    def setup_editor_toggle_connections(self):
        """Connect editor toggles to auto-save"""
        if hasattr(self, 'toolbar_toggle'):
            self.toolbar_toggle.toggled.connect(self.on_editor_settings_changed)
        if hasattr(self, 'line_numbers_toggle'):
            self.line_numbers_toggle.toggled.connect(self.on_editor_settings_changed)

    def setup_nlp_radio_connections(self):
        """Connect NLP radio buttons to auto-save"""
        if hasattr(self, 'nupunkt_radio'):
            self.nupunkt_radio.toggled.connect(self.on_nlp_settings_changed)
        if hasattr(self, 'spacy_radio'):
            self.spacy_radio.toggled.connect(self.on_nlp_settings_changed)

    def setup_tts_speed_connections(self):
        """Connect TTS speed controls to auto-save"""
        if hasattr(self, 'speed_slider') and hasattr(self, 'speed_spinner'):
            # Disconnect existing connections first
            try:
                self.speed_slider.valueChanged.disconnect()
                self.speed_spinner.valueChanged.disconnect()
            except:
                pass
            
            # Reconnect with auto-save
            self.speed_slider.valueChanged.connect(self.update_speed_spinner_with_save)
            self.speed_spinner.valueChanged.connect(self.update_speed_slider_with_save)

    def on_vosk_settings_changed(self):
        """Handle Vosk settings changes"""
        if "vosk_settings" not in self.config:
            self.config["vosk_settings"] = {}
        
        if hasattr(self, 'show_partial_text_toggle'):
            self.config["vosk_settings"]["show_partial_text"] = self.show_partial_text_toggle.isChecked()
        
        # Save immediately
        self.save_config_immediately()

    def on_editor_settings_changed(self):
        """Handle editor settings changes - these are saved to self.settings, not config"""
        if hasattr(self, 'toolbar_toggle'):
            self.settings["show_toolbar"] = self.toolbar_toggle.isChecked()
        if hasattr(self, 'line_numbers_toggle'):
            self.settings["show_line_numbers"] = self.line_numbers_toggle.isChecked()
        if hasattr(self, 'default_zoom_spinner'):
            self.settings["default_zoom"] = self.default_zoom_spinner.value()
        
        # Emit signal immediately for editor settings
        self.settingsChanged.emit(self.settings)

    def on_nlp_settings_changed(self):
        """Handle NLP settings changes"""
        if "nlp_settings" not in self.config:
            self.config["nlp_settings"] = {}
        
        if hasattr(self, 'spacy_radio') and self.spacy_radio.isChecked():
            self.config["nlp_settings"]["sentence_boundaries"] = "spacy"
        else:
            self.config["nlp_settings"]["sentence_boundaries"] = "nupunkt"
        
        # Save immediately
        self.save_config_immediately()

    def save_tts_speed(self):
        """Save TTS speed setting immediately"""
        if "tts_settings" not in self.config:
            self.config["tts_settings"] = {}
        self.config["tts_settings"]["speed"] = self.speed_spinner.value()
        self.save_config_immediately()

    def update_speed_spinner_with_save(self, value):
        """Update speed spinner when slider changes and save"""
        spinner_value = value / 100.0
        self.speed_spinner.blockSignals(True)
        self.speed_spinner.setValue(spinner_value)
        self.speed_spinner.blockSignals(False)
        
        # Save TTS speed immediately
        self.save_tts_speed()

    def update_speed_slider_with_save(self, value):
        """Update speed slider when spinner changes and save"""
        slider_value = int(value * 100)
        self.speed_slider.blockSignals(True)
        self.speed_slider.setValue(slider_value)
        self.speed_slider.blockSignals(False)
        
        # Save TTS speed immediately
        self.save_tts_speed()

    def setup_shortcuts(self):
        """Set up keyboard shortcuts"""
        # ESC to go back
        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.esc_shortcut.activated.connect(self.go_back)

        # Ctrl+Return to save
        self.save_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.save_shortcut.activated.connect(self.accept)

    def create_main_menu_page(self):
        """Create the main menu page"""
        page = QWidget()
        layout = QVBoxLayout(page)

        # Title
        title = QLabel("Settings")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        layout.addSpacing(40)

        # Menu buttons
        tts_button = QPushButton("Text-to-Speech Settings")
        tts_button.setMinimumHeight(50)
        tts_button.clicked.connect(lambda: self.show_page(1))
        layout.addWidget(tts_button)

        dictation_button = QPushButton("Dictation Settings")
        dictation_button.setMinimumHeight(50)
        dictation_button.clicked.connect(lambda: self.show_page(6))  # CHANGED: from 3 to 6
        layout.addWidget(dictation_button)

        other_button = QPushButton("Other Settings")
        other_button.setMinimumHeight(50)
        other_button.clicked.connect(lambda: self.show_page(4))
        layout.addWidget(other_button)

        layout.addStretch()

        self.stacked_widget.addWidget(page)

    def create_tts_settings_page(self):
        """Create TTS engine selection page"""
        page = QWidget()
    
        # Create scroll area for the entire page
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    
        # Create the scrollable content widget
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
    
        # Title
        title = QLabel("Text-to-Speech Settings")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
    
        layout.addSpacing(20)
    
        # Common TTS settings (speed)
        speed_group = QGroupBox("Speech Speed (All Engines)")
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
        speed_slider_layout.addWidget(self.speed_spinner)
    
        speed_layout.addLayout(speed_slider_layout)
        speed_group.setLayout(speed_layout)
        layout.addWidget(speed_group)
    
        # Connect slider and spinner (auto-save connections will be set up when page is shown)
        self.speed_slider.valueChanged.connect(self.update_speed_spinner)
        self.speed_spinner.valueChanged.connect(self.update_speed_slider)
    
        # Current engine display
        self.current_tts_engine_label = QLabel("Currently selected: None")
        font = self.current_tts_engine_label.font()
        font.setBold(True)
        self.current_tts_engine_label.setFont(font)
        layout.addWidget(self.current_tts_engine_label)
    
        layout.addSpacing(10)
    
        # Engine selection with checkboxes
        engine_selection_group = QGroupBox("Select TTS Engine")
        engine_selection_layout = QVBoxLayout()
    
        # Create TTS engine widgets dictionary 
        self.tts_engine_widgets = {}
    
        # Piper engine option
        piper_layout = QHBoxLayout()
        piper_checkbox = QCheckBox()
        piper_checkbox.setText("Piper")
        piper_checkbox.toggled.connect(lambda checked: self.on_tts_engine_selected(checked, "piper"))
        piper_layout.addWidget(piper_checkbox)
        piper_layout.addStretch()
    
        self.tts_engine_widgets["piper"] = {"checkbox": piper_checkbox}
        engine_selection_layout.addLayout(piper_layout)
    
        # Kokoro engine option  
        kokoro_layout = QHBoxLayout()
        kokoro_checkbox = QCheckBox()
        kokoro_checkbox.setText("Kokoro")
        kokoro_checkbox.toggled.connect(lambda checked: self.on_tts_engine_selected(checked, "kokoro"))
        kokoro_layout.addWidget(kokoro_checkbox)
        kokoro_layout.addStretch()
    
        self.tts_engine_widgets["kokoro"] = {"checkbox": kokoro_checkbox}
        engine_selection_layout.addLayout(kokoro_layout)
    
        engine_selection_group.setLayout(engine_selection_layout)
        layout.addWidget(engine_selection_group)
    
        layout.addSpacing(10)
    
        # Settings buttons section
        settings_group = QGroupBox("Engine Settings")  
        settings_layout = QVBoxLayout()
    
        piper_button = QPushButton("Piper TTS Settings")
        piper_button.setMinimumHeight(40)
        piper_button.clicked.connect(lambda: self.show_page(2))
        settings_layout.addWidget(piper_button)
    
        kokoro_button = QPushButton("Kokoro TTS Settings")
        kokoro_button.setMinimumHeight(40)
        kokoro_button.clicked.connect(lambda: self.show_page(5))
        settings_layout.addWidget(kokoro_button)
    
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
    
        layout.addStretch()
    
        # Back button
        back_button = QPushButton("← Back")
        back_button.clicked.connect(self.go_back)
        layout.addWidget(back_button)
    
        # Set the scroll content and add to scroll area
        scroll_area.setWidget(scroll_content)
    
        # Create the main page layout with just the scroll area
        page_layout = QVBoxLayout(page)
        page_layout.addWidget(scroll_area)
    
        self.stacked_widget.addWidget(page)

    def create_piper_settings_page(self):
        """Create Piper TTS settings page with voice selection like Kokoro"""
        page = QWidget()
    
        # Create scroll area for the entire page (like Kokoro)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    
        # Create the scrollable content widget
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)

        # Title
        title = QLabel("Piper TTS Settings")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        layout.addSpacing(20)
    
        # Current voice
        self.piper_current_voice_label = QLabel("Current voice: None")
        font = self.piper_current_voice_label.font()
        font.setBold(True)
        self.piper_current_voice_label.setFont(font)
        layout.addWidget(self.piper_current_voice_label)

        # Voice groups section
        voices_group = QGroupBox("Installed Voices")
        voices_layout = QVBoxLayout()

        # Initialize piper voice widgets storage
        self.piper_voice_widgets = {}
    
        # Voice list container (like Kokoro groups but flat)
        voice_list_widget = QWidget()
        voice_list_layout = QVBoxLayout(voice_list_widget)
        voice_list_layout.setContentsMargins(10, 10, 10, 10)
        voices_layout.addWidget(voice_list_widget)
    
        # Store references for loading voices later
        self.piper_voice_list_widget = voice_list_widget
        self.piper_voice_list_layout = voice_list_layout
    
        voices_group.setLayout(voices_layout)
        layout.addWidget(voices_group)
    
        # Check for available voices not installed and add download button if needed
        self.add_piper_download_button_if_needed(voices_layout, voices_group)
    
        layout.addStretch()
    
        # Back button
        back_button = QPushButton("← Back")
        back_button.clicked.connect(self.go_back)
        layout.addWidget(back_button)
    
        # Set the scroll content and add to scroll area (like Kokoro)
        scroll_area.setWidget(scroll_content)
    
        # Create the main page layout with just the scroll area
        page_layout = QVBoxLayout(page)
        page_layout.addWidget(scroll_area)
    
        self.stacked_widget.addWidget(page)

    def create_kokoro_settings_page(self):
        """Create Kokoro TTS settings page with expandable voice groups using PDF dialog pattern"""
        page = QWidget()
    
        # Create scroll area for the entire page (like Faster Whisper)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    
        # Create the scrollable content widget
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
    
        # Title
        title = QLabel("Kokoro TTS Settings")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
    
        layout.addSpacing(20)
    
        # Current voice
        self.kokoro_current_voice_label = QLabel("Current voice: None")
        font = self.kokoro_current_voice_label.font()
        font.setBold(True)
        self.kokoro_current_voice_label.setFont(font)
        layout.addWidget(self.kokoro_current_voice_label)
    
        # Voice groups section
        voices_group = QGroupBox("Available Voices")
        voices_layout = QVBoxLayout()
    
        # Initialize voice group widgets storage
        self.kokoro_voice_groups = {}
        self.kokoro_voice_widgets = {}
    
        # Create voice group checkboxes and voice lists (like PDF dialog pattern)
        voice_group_names = ["US Female", "US Male", "UK Female", "UK Male"]
    
        for group_name in voice_group_names:
            # Create group header checkbox (like PDF dialog)
            group_checkbox = QCheckBox(group_name)
            group_checkbox.clicked.connect(lambda checked, name=group_name: self.toggle_voice_group(name, checked))
            voices_layout.addWidget(group_checkbox)
    
            # Create collapsible voice list widget (indented like PDF dialog)
            voice_list_widget = QWidget()
            voice_list_layout = QVBoxLayout(voice_list_widget)
            voice_list_layout.setContentsMargins(30, 10, 0, 0)  # Indent like PDF dialog (30px)
            voice_list_widget.setVisible(False)  # Start collapsed
            voices_layout.addWidget(voice_list_widget)
    
            # Store references
            self.kokoro_voice_groups[group_name] = {
                'checkbox': group_checkbox,
                'widget': voice_list_widget,
                'layout': voice_list_layout
            }
    
        voices_group.setLayout(voices_layout)
        layout.addWidget(voices_group)
    
        # Docker settings
        docker_group = QGroupBox("Docker Settings")
        docker_layout = QHBoxLayout()
    
        docker_layout.addWidget(QLabel("Port:"))
    
        self.docker_port_spinner = QSpinBox()
        self.docker_port_spinner.setRange(1024, 65535)
        self.docker_port_spinner.setValue(8880)
        self.docker_port_spinner.valueChanged.connect(self.on_kokoro_settings_changed)
        docker_layout.addWidget(self.docker_port_spinner)
    
        docker_group.setLayout(docker_layout)
        layout.addWidget(docker_group)
    
        # GPU acceleration options
        gpu_group = QGroupBox("Performance")
        gpu_layout = QVBoxLayout()
    
        # Check if GPU is available
        if self.gpu_available:
            self.kokoro_use_gpu_toggle = QCheckBox("Use GPU acceleration (CUDA)")
            self.kokoro_use_gpu_toggle.setToolTip("Use GPU for faster processing. Requires CUDA-compatible GPU.")
            gpu_layout.addWidget(self.kokoro_use_gpu_toggle)
    
            # Connect to settings handler
            self.kokoro_use_gpu_toggle.toggled.connect(self.on_kokoro_settings_changed)
        else:
            # Show informational label when no GPU detected
            no_gpu_label = QLabel("GPU acceleration not available (no CUDA GPU detected)")
            no_gpu_label.setStyleSheet("color: #666; font-style: italic;")
            gpu_layout.addWidget(no_gpu_label)
    
        gpu_group.setLayout(gpu_layout)
        layout.addWidget(gpu_group)
    
        layout.addStretch()
    
        # Back button
        back_button = QPushButton("â†� Back")
        back_button.clicked.connect(self.go_back)
        layout.addWidget(back_button)
    
        # Set the scroll content and add to scroll area (like Faster Whisper)
        scroll_area.setWidget(scroll_content)
    
        # Create the main page layout with just the scroll area
        page_layout = QVBoxLayout(page)
        page_layout.addWidget(scroll_area)
    
        self.stacked_widget.addWidget(page)

    def create_faster_whisper_settings_page(self):
        """Create faster whisper settings page"""
        page = QWidget()
    
        # Create scroll area for the entire page
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    
        # Create the scrollable content widget
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
    
        # Title
        title = QLabel("Faster Whisper Settings")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        
        layout.addSpacing(20)
    
        # Load STT models from stt.json
        self.faster_whisper_models = self.load_stt_models()
    
        # Current model section
        current_model_group = QGroupBox("Current Model")
        current_model_layout = QVBoxLayout()
        
        self.fw_current_model_label = QLabel("Current model: None")
        font = self.fw_current_model_label.font()
        font.setBold(True)
        self.fw_current_model_label.setFont(font)
        current_model_layout.addWidget(self.fw_current_model_label)
        
        current_model_group.setLayout(current_model_layout)
        layout.addWidget(current_model_group)
    
        # Model selection section
        models_group = QGroupBox("Available Models")
        models_layout = QVBoxLayout()
    
        # Create model widgets dictionary
        self.fw_model_widgets = {}
    
        # Get faster-whisper models from stt.json
        if "faster-whisper" in self.faster_whisper_models:
            fw_models = self.faster_whisper_models["faster-whisper"]
            
            for model_size, model_info in fw_models.items():
                # Create horizontal layout for each model
                model_layout = QHBoxLayout()
                
                # Create checkbox for model selection
                checkbox = QCheckBox()
                checkbox.setText(f"{model_size.title()} Model ({model_info['model_id']})")
                checkbox.clicked.connect(lambda checked, size=model_size: self.on_fw_model_selected(checked, size))
                
                # Create download button
                download_button = QPushButton(f"Download")
                download_button.clicked.connect(lambda checked, size=model_size: self.download_fw_model(size))
                download_button.setMaximumWidth(200)
                
                # Add to layout
                model_layout.addWidget(checkbox)
                model_layout.addStretch()
                model_layout.addWidget(download_button)
            
                # Store widgets
                self.fw_model_widgets[model_size] = {
                    'checkbox': checkbox,
                    'download_button': download_button
                }
            
                models_layout.addLayout(model_layout)
    
        models_group.setLayout(models_layout)
        layout.addWidget(models_group)
    
        # GPU settings (keep existing functionality)
        gpu_group = QGroupBox("Performance Settings")
        gpu_layout = QVBoxLayout()
    
        # Detect GPU availability
        self.gpu_available = self._detect_gpu()
    
        if self.gpu_available:
            self.fw_use_gpu_toggle = QCheckBox("Use GPU acceleration (CUDA)")
            self.fw_use_gpu_toggle.setToolTip("Enable GPU acceleration for faster processing. Requires CUDA-compatible GPU.")
            gpu_layout.addWidget(self.fw_use_gpu_toggle)
            
#            # Connect to settings handler
#            self.fw_use_gpu_toggle.toggled.connect(self.on_fw_settings_changed)
        else:
            # Show informational label when no GPU detected
            no_gpu_label = QLabel("GPU acceleration not available (no CUDA GPU detected)")
            no_gpu_label.setStyleSheet("color: #666; font-style: italic;")
            gpu_layout.addWidget(no_gpu_label)
    
        gpu_group.setLayout(gpu_layout)
        layout.addWidget(gpu_group)
    
        # Formatting settings (keep existing functionality)
        formatting_group = QGroupBox("Text Formatting")
        formatting_layout = QVBoxLayout()
    
        self.fw_auto_sentence_format_toggle = QCheckBox("Automatically format sentences (add periods and capitalize)")
        self.fw_auto_sentence_format_toggle.setToolTip("Check to automatically add periods and capitalize sentences. Uncheck for raw transcription.")
        formatting_layout.addWidget(self.fw_auto_sentence_format_toggle)
    
        formatting_group.setLayout(formatting_layout)
        layout.addWidget(formatting_group)
    
        layout.addStretch()
    
        # Back button
        back_button = QPushButton("â†� Back")
        back_button.clicked.connect(self.go_back)
        layout.addWidget(back_button)
    
        # Set the scroll content and add to scroll area
        scroll_area.setWidget(scroll_content)
    
        # Create the main page layout with just the scroll area
        page_layout = QVBoxLayout(page)
        page_layout.addWidget(scroll_area)
    
        self.stacked_widget.addWidget(page)
    
    def create_dictation_engine_selection_page(self):
        """Create dictation engine selection page"""
        page = QWidget()
        layout = QVBoxLayout(page)
    
        # Title
        title = QLabel("Dictation Settings")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
    
        layout.addSpacing(20)
    
        # Current engine display
        self.current_engine_label = QLabel("Currently selected: None")
        font = self.current_engine_label.font()
        font.setBold(True)
        self.current_engine_label.setFont(font)
        layout.addWidget(self.current_engine_label)
    
        layout.addSpacing(10)
    
        # Engine selection with checkboxes
        engine_group = QGroupBox("Select Speech Recognition Engine")
        engine_layout = QVBoxLayout()
    
        # Create engine widgets dictionary 
        self.engine_widgets = {}
    
        # Vosk engine option
        vosk_layout = QHBoxLayout()
        vosk_checkbox = QCheckBox()
        vosk_checkbox.setText("Vosk")
        vosk_checkbox.toggled.connect(lambda checked: self.on_engine_selected(checked, "vosk"))
        vosk_layout.addWidget(vosk_checkbox)
        vosk_layout.addStretch()
    
        self.engine_widgets["vosk"] = {"checkbox": vosk_checkbox}
        engine_layout.addLayout(vosk_layout)
    
        # Faster Whisper engine option  
        fw_layout = QHBoxLayout()
        fw_checkbox = QCheckBox()
        fw_checkbox.setText("Faster Whisper")
        fw_checkbox.toggled.connect(lambda checked: self.on_engine_selected(checked, "faster-whisper"))
        fw_layout.addWidget(fw_checkbox)
        fw_layout.addStretch()
    
        self.engine_widgets["faster-whisper"] = {"checkbox": fw_checkbox}
        engine_layout.addLayout(fw_layout)
    
        engine_group.setLayout(engine_layout)
        layout.addWidget(engine_group)
    
        layout.addSpacing(10)
    
        # Settings buttons section
        settings_group = QGroupBox("Engine Settings")  
        settings_layout = QVBoxLayout()
    
        faster_whisper_button = QPushButton("Faster Whisper Settings")
        faster_whisper_button.setMinimumHeight(40)
        faster_whisper_button.clicked.connect(lambda: self.show_page(3))
        settings_layout.addWidget(faster_whisper_button)
    
        vosk_button = QPushButton("Vosk Settings")
        vosk_button.setMinimumHeight(40)
        vosk_button.clicked.connect(lambda: self.show_page(7))
        settings_layout.addWidget(vosk_button)
    
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
    
        layout.addStretch()
    
        # Back button
        back_button = QPushButton("â†� Back")
        back_button.clicked.connect(self.go_back)
        layout.addWidget(back_button)
    
        self.stacked_widget.addWidget(page)

    def on_engine_selected(self, checked, engine):
        """Handle engine checkbox selection"""
        if checked:
            # Uncheck all other engine checkboxes
            for eng, widgets in self.engine_widgets.items():
                if eng != engine:
                    widgets['checkbox'].setChecked(False)
            
            # Update config
            if "dictation_settings" not in self.config:
                self.config["dictation_settings"] = {}
            self.config["dictation_settings"]["engine"] = engine
            
            # Save immediately
            self.save_config_immediately()
            
            # Update current engine label
            engine_display = engine.replace("-", " ").title()
            self.current_engine_label.setText(f"Currently selected: {engine_display}")

    def on_tts_engine_selected(self, checked, engine):
        """Handle TTS engine checkbox selection"""
        if checked:
            # Uncheck all other engine checkboxes
            for eng, widgets in self.tts_engine_widgets.items():
                if eng != engine:
                    widgets['checkbox'].setChecked(False)
            
            # Update config
            if "tts_settings" not in self.config:
                self.config["tts_settings"] = {}
            self.config["tts_settings"]["engine"] = engine
            
            # Save immediately
            self.save_config_immediately()
            
            # Update label
            engine_display = engine.title()
            self.current_tts_engine_label.setText(f"Currently selected: {engine_display}")
    
    def create_other_settings_page(self):
        """Create other settings page (editor + NLP settings)"""
        page = QWidget()
        layout = QVBoxLayout(page)

        # Title
        title = QLabel("Other Settings")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        layout.addSpacing(20)

        # Editor settings
        editor_group = QGroupBox("Text Editor Display")
        editor_layout = QVBoxLayout()

        self.toolbar_toggle = QCheckBox("Show toolbar with formatting controls")
        self.toolbar_toggle.setChecked(self.settings.get("show_toolbar", True))
        editor_layout.addWidget(self.toolbar_toggle)

        self.line_numbers_toggle = QCheckBox("Show line numbers in the margin")
        self.line_numbers_toggle.setChecked(self.settings.get("show_line_numbers", False))
        editor_layout.addWidget(self.line_numbers_toggle)

        # Default zoom
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("Default zoom level:"))
        
        self.default_zoom_spinner = QSpinBox()
        self.default_zoom_spinner.setRange(50, 300)
        self.default_zoom_spinner.setSingleStep(10)
        self.default_zoom_spinner.setSuffix("%")
        self.default_zoom_spinner.setValue(self.settings.get("default_zoom", 100))
        zoom_layout.addWidget(self.default_zoom_spinner)
        self.default_zoom_spinner.valueChanged.connect(self.on_editor_settings_changed)
        
        editor_layout.addLayout(zoom_layout)

        editor_group.setLayout(editor_layout)
        layout.addWidget(editor_group)

        # NLP settings
        nlp_group = QGroupBox("Natural Language Processing")
        nlp_layout = QVBoxLayout()

        nlp_layout.addWidget(QLabel("Sentence boundary detection method:"))

        self.sentence_method_group = QButtonGroup()
        
        self.nupunkt_radio = QRadioButton("nupunkt (Default)")
        self.spacy_radio = QRadioButton("spaCy")
        
        self.sentence_method_group.addButton(self.nupunkt_radio, 0)
        self.sentence_method_group.addButton(self.spacy_radio, 1)
        
        nlp_layout.addWidget(self.nupunkt_radio)
        nlp_layout.addWidget(self.spacy_radio)

        nlp_group.setLayout(nlp_layout)
        layout.addWidget(nlp_group)

        layout.addStretch()

        # Back button
        back_button = QPushButton("â†� Back")
        back_button.clicked.connect(self.go_back)
        layout.addWidget(back_button)

        # Set up auto-save connections
        self.setup_editor_toggle_connections()
        self.setup_nlp_radio_connections()

        self.stacked_widget.addWidget(page)

    def create_vosk_settings_page(self):
        """Create Vosk settings page"""
        page = QWidget()
    
        # Create scroll area for the entire page
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    
        # Create the scrollable content widget
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
    
        # Title
        title = QLabel("Vosk Settings")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        
        layout.addSpacing(20)
    
        # Load STT models from stt.json
        self.vosk_models = self.load_stt_models()
    
        # Vosk models section
        models_group = QGroupBox("Available Vosk Models")
        models_layout = QVBoxLayout()
    
        # Store model widgets for dynamic updates
        self.vosk_model_widgets = {}
    
        # Create widgets for each available Vosk model
        if "vosk" in self.vosk_models:
            for model_size, model_info in self.vosk_models["vosk"].items():
                model_widget = QWidget()
                model_layout = QHBoxLayout(model_widget)
                model_layout.setContentsMargins(0, 5, 0, 5)
                
                # Selection checkbox (on the left, like the partial text toggle)
                selection_checkbox = QCheckBox(f"{model_size.title()} Model")
                selection_checkbox.clicked.connect(lambda checked, size=model_size: self.on_vosk_model_selected(checked, size))
                model_layout.addWidget(selection_checkbox)
                
                model_layout.addStretch()
                
                # Download button (on the right)
                download_button = QPushButton("Download")
                download_button.setMinimumHeight(30)
                download_button.clicked.connect(lambda checked, size=model_size: self.download_vosk_model(size))
                model_layout.addWidget(download_button)
                
                models_layout.addWidget(model_widget)
                
                # Store references for updates
                self.vosk_model_widgets[model_size] = {
                    'widget': model_widget,
                    'checkbox': selection_checkbox,
                    'download_button': download_button
                }
    
        models_group.setLayout(models_layout)
        layout.addWidget(models_group)
    
        # Formatting options (keep partial text toggle only)
        formatting_group = QGroupBox("Dictation Display")
        formatting_layout = QVBoxLayout()
    
        self.show_partial_text_toggle = QCheckBox("Show partial text while speaking")
        self.show_partial_text_toggle.setToolTip("Display gray partial text during dictation. Uncheck to hide partial text.")
        formatting_layout.addWidget(self.show_partial_text_toggle)
    
        formatting_group.setLayout(formatting_layout)
        layout.addWidget(formatting_group)
    
        layout.addStretch()
    
        # Back button
        back_button = QPushButton("â†� Back")
        back_button.clicked.connect(self.go_back)
        layout.addWidget(back_button)
    
        # Set the scroll content and add to scroll area
        scroll_area.setWidget(scroll_content)
    
        # Create the main page layout with just the scroll area
        page_layout = QVBoxLayout(page)
        page_layout.addWidget(scroll_area)
    
        self.stacked_widget.addWidget(page)
    
        # Load current settings after widgets are created
        self.load_vosk_settings()

    def load_stt_models(self):
        """Load STT models from stt.json"""
        try:
            stt_json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "stt.json")
            with open(stt_json_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading stt.json: {e}")
            return {"vosk": {}}

    def _detect_gpu(self):
        """Detect if a CUDA GPU is available and properly configured"""
        try:
            import torch
            return torch.cuda.is_available() and torch.cuda.device_count() > 0
        except ImportError:
            return False

    def on_kokoro_settings_changed(self):
        """Handle Kokoro TTS settings changes - NEW CONFIG STRUCTURE"""
        if "kokoro_settings" not in self.config:
            self.config["kokoro_settings"] = {}
    
        # Save GPU setting if available
        if self.gpu_available and hasattr(self, 'kokoro_use_gpu_toggle'):
            use_gpu = self.kokoro_use_gpu_toggle.isChecked()
            # Validate GPU is still available if trying to enable
            if use_gpu and not self._detect_gpu():
                use_gpu = False
                self.kokoro_use_gpu_toggle.setChecked(False)
    
            self.config["kokoro_settings"]["use_gpu"] = use_gpu
    
        # Save Docker port
        if hasattr(self, 'docker_port_spinner'):
            self.config["kokoro_settings"]["docker_port"] = self.docker_port_spinner.value()
    
        # Save immediately
        self.save_config_immediately()
    
    def toggle_voice_group(self, group_name, checked):
        """Toggle voice group expansion and collapse others (like PDF dialog pattern)"""
        # If this group is being checked (expanded)
        if checked:
            # Collapse any currently expanded groups
            for other_group_name, group_data in self.kokoro_voice_groups.items():
                if other_group_name != group_name:
                    group_data['checkbox'].setChecked(False)
                    group_data['widget'].setVisible(False)
    
            # Expand this group
            self.kokoro_voice_groups[group_name]['widget'].setVisible(True)
    
            # Load voices for this group if not already loaded
            if group_name not in self.kokoro_voice_widgets:
                self.load_voices_for_group(group_name)
        else:
            # Collapse this group
            self.kokoro_voice_groups[group_name]['widget'].setVisible(False)

    def load_voices_for_group(self, group_name):
        """Load and display voices for a specific group"""
        try:
            # Get the project root directory
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            tts_json_path = os.path.join(project_root, "tts.json")
    
            with open(tts_json_path, 'r') as f:
                tts_data = json.load(f)
    
            kokoro_voices = tts_data.get("kokoro_tts_voices", {}).get("voices", {})
   
            # Get currently selected voice - show saved Kokoro voice regardless of current engine
            selected_voice = None
            if ("kokoro_settings" in self.config and
                "voice" in self.config["kokoro_settings"]):
                selected_voice = self.config["kokoro_settings"]["voice"]
    
            # Filter voices for this group
            group_voices = []
            for voice_id, voice_info in kokoro_voices.items():
                display_name = voice_info.get("display_name", voice_id)
                gender = voice_info.get("gender", "unknown")
                lang_code = voice_info.get("language_code", "en_US")
    
                # Determine if this voice belongs to the current group
                voice_group = None
                if lang_code == "en_US":
                    if gender == "female":
                        voice_group = "US Female"
                    elif gender == "male":
                        voice_group = "US Male"
                elif lang_code == "en_GB":
                    if gender == "female":
                        voice_group = "UK Female"
                    elif gender == "male":
                        voice_group = "UK Male"
    
                if voice_group == group_name:
                    group_voices.append((voice_id, display_name))
    
            # Sort voices by display name
            group_voices.sort(key=lambda x: x[1])
    
            # Create voice widgets for this group
            group_layout = self.kokoro_voice_groups[group_name]['layout']
            self.kokoro_voice_widgets[group_name] = {}
    
            for voice_id, display_name in group_voices:
                # Create horizontal layout for voice
                voice_layout = QHBoxLayout()
    
                # Create checkbox for voice selection (like Faster Whisper)
                voice_checkbox = QCheckBox()
                voice_checkbox.setText(display_name)
                voice_checkbox.toggled.connect(lambda checked, vid=voice_id: self.on_kokoro_voice_selected(checked, vid))
    
                # Check if this is the selected voice
                if selected_voice == voice_id:
                    voice_checkbox.setChecked(True)
    
                voice_layout.addWidget(voice_checkbox)
                voice_layout.addStretch()
    
                # Store widget reference
                self.kokoro_voice_widgets[group_name][voice_id] = {
                    'checkbox': voice_checkbox,
                    'layout': voice_layout
                }
    
                # Add to group layout
                group_layout.addLayout(voice_layout)
    
        except Exception as e:
            print(f"Error loading voices for group {group_name}: {e}")

    def on_kokoro_voice_selected(self, checked, voice_id):
        """Handle Kokoro voice selection with checkbox - NEW CONFIG STRUCTURE"""
        if checked:
            # Uncheck all other voice checkboxes (like Faster Whisper)
            for group_name, voice_widgets in self.kokoro_voice_widgets.items():
                for vid, widgets in voice_widgets.items():
                    if vid != voice_id:
                        widgets['checkbox'].setChecked(False)

            # Update config - NEW STRUCTURE
            # Set the TTS engine to kokoro
            if "tts_settings" not in self.config:
                self.config["tts_settings"] = {}
            self.config["tts_settings"]["engine"] = "kokoro"

            # Set the selected kokoro voice
            if "kokoro_settings" not in self.config:
                self.config["kokoro_settings"] = {}
            self.config["kokoro_settings"]["voice"] = voice_id

            # Save immediately
            self.save_config_immediately()

            # Update label
            self.kokoro_current_voice_label.setText(f"Current voice: {voice_id}")
            
            # Play voice test
            self._play_voice_test(voice_id)

    def _play_voice_test(self, voice_id):
        """Play test audio for the selected voice using existing TTS infrastructure"""
        # Stop any currently playing test
        self._stop_voice_test()
        
        # Create a simple single-sentence "document" for testing
        from PySide6.QtGui import QTextDocument
        test_document = QTextDocument()
        test_document.setPlainText(self.VOICE_TEST_TEXT)
        
        # Create a minimal sentence data structure like the TTS system expects
        test_sentence_data = [{
            'sentences': [self.VOICE_TEST_TEXT],
            'offsets': [(0, len(self.VOICE_TEST_TEXT))]
        }]
        
        # Create a temporary TTS manager for voice testing
        self._test_tts_manager = TTSManager(None, self.config, self.assistivox_dir)
        self._test_tts_manager.sentence_data = test_sentence_data
        self._test_tts_manager.set_sentence_index(0, 0)
        
        # Temporarily override the voice in config for this test
        original_voice = self.config.get("kokoro_settings", {}).get("voice")
        if "kokoro_settings" not in self.config:
            self.config["kokoro_settings"] = {}
        self.config["kokoro_settings"]["voice"] = voice_id
        
        # Start playing the test
        success = self._test_tts_manager._start_speaking_from_index()
        
        # Restore original voice setting
        if original_voice:
            self.config["kokoro_settings"]["voice"] = original_voice
        elif "voice" in self.config["kokoro_settings"]:
            del self.config["kokoro_settings"]["voice"]
        
        if not success:
            print(f"Failed to start voice test for {voice_id}")
    
    def _stop_voice_test(self):
        """Stop any currently playing voice test"""
        if hasattr(self, '_test_tts_manager') and self._test_tts_manager:
            self._test_tts_manager.stop_speech()
            self._test_tts_manager = None
    
    def closeEvent(self, event):
        """Clean up when dialog is closed"""
        # Stop any playing voice test
        self._stop_voice_test()
        super().closeEvent(event)

    def auto_expand_group_for_voice(self, voice_id):
        """Auto-expand the group containing the selected voice"""
        try:
            # Get the project root directory
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            tts_json_path = os.path.join(project_root, "tts.json")
    
            with open(tts_json_path, 'r') as f:
                tts_data = json.load(f)
    
            kokoro_voices = tts_data.get("kokoro_tts_voices", {}).get("voices", {})
    
            # Find the group for this voice
            if voice_id in kokoro_voices:
                voice_info = kokoro_voices[voice_id]
                gender = voice_info.get("gender", "unknown")
                lang_code = voice_info.get("language_code", "en_US")
    
                # Determine group
                target_group = None
                if lang_code == "en_US":
                    if gender == "female":
                        target_group = "US Female"
                    elif gender == "male":
                        target_group = "US Male"
                elif lang_code == "en_GB":
                    if gender == "female":
                        target_group = "UK Female"
                    elif gender == "male":
                        target_group = "UK Male"
    
                # Auto-expand the target group
                if target_group and target_group in self.kokoro_voice_groups:
                    group_checkbox = self.kokoro_voice_groups[target_group]['checkbox']
                    group_checkbox.setChecked(True)
                    self.toggle_voice_group(target_group, True)
    
        except Exception as e:
            print(f"Error auto-expanding group for voice {voice_id}: {e}")

    def show_page(self, index):
        """Show a specific page and track navigation"""
        current_index = self.stacked_widget.currentIndex()
        if current_index != index:
            self.navigation_stack.append(current_index)
        self.stacked_widget.setCurrentIndex(index)

        # Reload config from disk to ensure we have latest saved values
        self.reload_config_from_disk()

        # Load data when showing specific pages
        if index == 2:  # Piper settings
            self.load_voice_list()
        elif index == 3:  # Faster Whisper settings
            self.load_fw_settings()
        elif index == 1:  # TTS settings
            self.load_tts_speed()
            self.setup_tts_speed_connections()
            self.load_tts_engine_selection()
        elif index == 4:  # Other settings
            self.load_nlp_settings()
        elif index == 5:  # Kokoro settings
            self.load_kokoro_voices()
            self.load_kokoro_settings()
        elif index == 6:  # Dictation engine selection
            self.load_dictation_engine_selection()
        elif index == 7:  # Vosk settings page
            self.load_vosk_settings()

    def load_kokoro_settings(self):
        """Load Kokoro TTS settings - NEW CONFIG STRUCTURE"""
        # Load GPU setting if GPU is available
        if self.gpu_available and hasattr(self, 'kokoro_use_gpu_toggle'):
            use_gpu = self.config.get("kokoro_settings", {}).get("use_gpu", True)  # Default to True if GPU available
            # Validate GPU is still available
            if use_gpu and not self._detect_gpu():
                use_gpu = False
                # Auto-correct the config
                if "kokoro_settings" not in self.config:
                    self.config["kokoro_settings"] = {}
                self.config["kokoro_settings"]["use_gpu"] = False
                self.save_config_immediately()
    
            self.kokoro_use_gpu_toggle.setChecked(use_gpu)
    
        # Load Docker port
        if hasattr(self, 'docker_port_spinner'):
            docker_port = self.config.get("kokoro_settings", {}).get("docker_port", 8880)
            self.docker_port_spinner.setValue(docker_port)
    
    def go_back(self):
        """Go back to previous page or close dialog"""
        if self.navigation_stack:
            prev_index = self.navigation_stack.pop()
            self.stacked_widget.setCurrentIndex(prev_index)
            
            # If returning to TTS settings page, reload the engine selection to update checkboxes
            if prev_index == 1:  # TTS settings page index
                self.load_tts_engine_selection()
        else:
            # If at main menu, close dialog
            self.reject()

    def load_voice_list(self):
        """Load Piper voice list with checkboxes like Kokoro in a scrollable list"""
        # Clear existing voice widgets
        if hasattr(self, 'piper_voice_widgets'):
            for voice_id, widgets in self.piper_voice_widgets.items():
                widgets['checkbox'].deleteLater()
            self.piper_voice_widgets.clear()
    
        # Clear the layout
        if hasattr(self, 'piper_voice_list_layout'):
            for i in reversed(range(self.piper_voice_list_layout.count())):
                child = self.piper_voice_list_layout.itemAt(i).widget()
                if child:
                    child.deleteLater()
    
        # Get currently selected voice
        selected_voice = None
        if ("piper_settings" in self.config and
            "voice" in self.config["piper_settings"]):
            selected_voice = self.config["piper_settings"]["voice"]
    
        # Get installed voices using the existing method
        installed_voices = list_installed_tts_models(str(self.assistivox_dir))
        piper_voices = installed_voices.get("piper", [])
    
        if not piper_voices:
            no_voices_label = QLabel("No Piper voices installed")
            no_voices_label.setAlignment(Qt.AlignCenter)
            self.piper_voice_list_layout.addWidget(no_voices_label)
            return
    
        # Sort voices alphabetically
        piper_voices.sort()
    
        # Create voice checkboxes (like Kokoro but in a flat list)
        for voice_id in piper_voices:
            # Create horizontal layout for voice (like Kokoro voice layout)
            voice_layout = QHBoxLayout()
    
            # Create checkbox for voice selection
            voice_checkbox = QCheckBox()
            voice_checkbox.setText(voice_id)
            voice_checkbox.toggled.connect(lambda checked, vid=voice_id: self.on_piper_voice_selected(checked, vid))
    
            # Apply menu font size like Kokoro
            if 'appearance' in self.config and 'menu_font_size' in self.config['appearance']:
                font = voice_checkbox.font()
                font.setPointSize(self.config['appearance']['menu_font_size'])
                voice_checkbox.setFont(font)
    
            # Check if this is the selected voice
            if selected_voice == voice_id:
                voice_checkbox.setChecked(True)
    
            voice_layout.addWidget(voice_checkbox)
            voice_layout.addStretch()
    
            # Store widget reference
            self.piper_voice_widgets[voice_id] = {
                'checkbox': voice_checkbox,
                'layout': voice_layout
            }
    
            # Add to layout
            self.piper_voice_list_layout.addLayout(voice_layout)
    
        # Update current voice label
        if selected_voice:
            self.piper_current_voice_label.setText(f"Current voice: {selected_voice}")
        else:
            self.piper_current_voice_label.setText("Current voice: None")

    def load_kokoro_voices(self):
        """Load Kokoro voices and auto-expand the correct group - NEW CONFIG STRUCTURE"""
        # Get currently selected voice - show saved Kokoro voice regardless of current engine
        selected_voice = None
        if ("kokoro_settings" in self.config and
            "voice" in self.config["kokoro_settings"]):
            selected_voice = self.config["kokoro_settings"]["voice"]

        # Update current voice label
        if selected_voice:
            self.kokoro_current_voice_label.setText(f"Current voice: {selected_voice}")
    
            # Determine which group contains this voice and auto-expand it
            self.auto_expand_group_for_voice(selected_voice)
        else:
            self.kokoro_current_voice_label.setText("Current voice: None")

    def on_fw_settings_changed(self):
        """Handle faster-whisper settings changes"""
        if "faster_whisper_settings" not in self.config:
            self.config["faster_whisper_settings"] = {}

        if hasattr(self, 'fw_auto_sentence_format_toggle'):
            self.config["faster_whisper_settings"]["auto_sentence_format"] = self.fw_auto_sentence_format_toggle.isChecked()

        # Save GPU setting if available
        if self.gpu_available and hasattr(self, 'fw_use_gpu_toggle'):
            use_gpu = self.fw_use_gpu_toggle.isChecked()
            # Validate GPU is still available if trying to enable
            if use_gpu and not self._detect_gpu():
                use_gpu = False
                self.fw_use_gpu_toggle.setChecked(False)
            
            self.config["faster_whisper_settings"]["use_gpu"] = use_gpu
    
        # Save immediately
        self.save_config_immediately()

    def load_tts_speed(self):
        """Load TTS speed setting"""
        if "tts_settings" in self.config:
            speed = self.config["tts_settings"].get("speed", 1.0)  # Default to 1.0 instead of 0.5
            self.speed_spinner.setValue(float(speed))
            self.update_speed_slider(float(speed))
        else:
            # Default to 1.0 if no setting exists
            self.speed_spinner.setValue(1.0)
            self.update_speed_slider(1.0)

    def load_nlp_settings(self):
        """Load NLP settings"""
        if "nlp_settings" in self.config and "sentence_boundaries" in self.config["nlp_settings"]:
            method = self.config["nlp_settings"]["sentence_boundaries"]
            if method == "spacy":
                self.spacy_radio.setChecked(True)
            else:
                self.nupunkt_radio.setChecked(True)
        else:
            self.nupunkt_radio.setChecked(True)

    def load_dictation_engine_selection(self):
        """Load current dictation engine selection"""
        # Read the engine field from dictation_settings section in config file
        current_engine = None
        current_engine_display = "None"
        
        if "dictation_settings" in self.config and "engine" in self.config["dictation_settings"]:
            current_engine = self.config["dictation_settings"]["engine"]
        
        # Use load_stt_models to see if there are any models installed for that engine
        if current_engine:
            try:
                from gui.models.stt_models import load_installed_stt_models
                installed_models = load_installed_stt_models(str(self.assistivox_dir))
                
                # Check if there are installed models for the current engine
                engine_has_models = current_engine in installed_models and len(installed_models[current_engine]) > 0
                
                if engine_has_models:
                    # If so, then put a checkbox next to the chosen engine
                    current_engine_display = current_engine.replace("-", " ").title()
                    
                    # Update checkboxes - only check the engine that has models installed
                    if hasattr(self, 'engine_widgets'):
                        for engine, widgets in self.engine_widgets.items():
                            widgets['checkbox'].setChecked(engine == current_engine)
                else:
                    # If not, then do not put any checkbox
                    current_engine_display = "None (no models installed)"
                    current_engine = None
                    
                    # Uncheck all checkboxes since no models are installed
                    if hasattr(self, 'engine_widgets'):
                        for engine, widgets in self.engine_widgets.items():
                            widgets['checkbox'].setChecked(False)
            
            except ImportError:
                # Fallback if stt_models module is not available
                current_engine_display = current_engine.replace("-", " ").title()
                if hasattr(self, 'engine_widgets'):
                    for engine, widgets in self.engine_widgets.items():
                        widgets['checkbox'].setChecked(engine == current_engine)
        else:
            # No engine configured, uncheck all
            if hasattr(self, 'engine_widgets'):
                for engine, widgets in self.engine_widgets.items():
                    widgets['checkbox'].setChecked(False)
    
        self.current_engine_label.setText(f"Currently selected: {current_engine_display}")

    def load_tts_engine_selection(self):
        """Load current TTS engine selection"""
        # Read the engine field from tts_settings section in config file
        current_engine = None
        current_engine_display = "None"
        
        if "tts_settings" in self.config and "engine" in self.config["tts_settings"]:
            current_engine = self.config["tts_settings"]["engine"]
            current_engine_display = current_engine.title()
        
        # Update label
        self.current_tts_engine_label.setText(f"Currently selected: {current_engine_display}")
        
        # Set checkboxes based on current engine
        for engine, widgets in self.tts_engine_widgets.items():
            widgets['checkbox'].setChecked(engine == current_engine)
    
    def load_vosk_settings(self):
        """Load Vosk settings and update model list UI"""
        try:
            from gui.models.stt_models import load_installed_stt_models
            
            # Get installed models
            installed_models = load_installed_stt_models(str(self.assistivox_dir))
            vosk_installed = installed_models.get("vosk", [])
            
            # Get selected model from vosk_settings section
            selected_model = None
            if "vosk_settings" in self.config and "model" in self.config["vosk_settings"]:
                selected_model = self.config["vosk_settings"]["model"]
            
            # Update each model widget
            for model_size, widgets in self.vosk_model_widgets.items():
                is_installed = model_size in vosk_installed
                is_selected = selected_model == model_size
                
                # Enable/disable and check/uncheck the checkbox
                widgets['checkbox'].setEnabled(is_installed)
                widgets['checkbox'].setChecked(is_selected and is_installed)
                
                # Show/hide download button based on installation status
                widgets['download_button'].setVisible(not is_installed)
            
        except ImportError:
            # Handle case where stt_models is not available
            for model_size, widgets in self.vosk_model_widgets.items():
                widgets['checkbox'].setText("Cannot check status")
                widgets['checkbox'].setEnabled(False)
                widgets['download_button'].setVisible(False)
        
        # Load partial text setting
        if "vosk_settings" in self.config and "show_partial_text" in self.config["vosk_settings"]:
            self.show_partial_text_toggle.setChecked(self.config["vosk_settings"]["show_partial_text"])
        else:
            self.show_partial_text_toggle.setChecked(True)
        
        # Set up auto-save connections for toggles
        self.setup_vosk_toggle_connections()

    def on_piper_voice_selected(self, checked, voice_id):
        """Handle Piper voice selection with checkbox like Kokoro"""
        if checked:
            # Uncheck all other voice checkboxes (like Kokoro)
            for vid, widgets in self.piper_voice_widgets.items():
                if vid != voice_id:
                    widgets['checkbox'].setChecked(False)
    
            # Update config - set TTS engine to piper
            if "tts_settings" not in self.config:
                self.config["tts_settings"] = {}
            self.config["tts_settings"]["engine"] = "piper"
    
            # Set the selected piper voice
            if "piper_settings" not in self.config:
                self.config["piper_settings"] = {}
            self.config["piper_settings"]["voice"] = voice_id
    
            # Save immediately
            self.save_config_immediately()
    
            # Update label
            self.piper_current_voice_label.setText(f"Current voice: {voice_id}")
            
            # Play voice test using the same test message as Kokoro
            self._play_piper_voice_test(voice_id)
    
    def _play_piper_voice_test(self, voice_id):
        """Play test audio for the selected Piper voice using existing TTS infrastructure"""
        # Stop any currently playing test
        self._stop_voice_test()
        
        # Create a simple single-sentence "document" for testing
        from PySide6.QtGui import QTextDocument
        test_document = QTextDocument()
        test_document.setPlainText(self.VOICE_TEST_TEXT)
        
        # Create a minimal sentence data structure like the TTS system expects
        test_sentence_data = [{
            'sentences': [self.VOICE_TEST_TEXT],
            'offsets': [(0, len(self.VOICE_TEST_TEXT))]
        }]
        
        # Create a temporary TTS manager for voice testing
        self._test_tts_manager = TTSManager(None, self.config, self.assistivox_dir)
        self._test_tts_manager.sentence_data = test_sentence_data
        self._test_tts_manager.set_sentence_index(0, 0)
        
        # Temporarily override the voice in config for this test
        original_voice = self.config.get("piper_settings", {}).get("voice")
        if "piper_settings" not in self.config:
            self.config["piper_settings"] = {}
        self.config["piper_settings"]["voice"] = voice_id
        
        # Start playing the test
        success = self._test_tts_manager._start_speaking_from_index()
        
        # Restore original voice setting
        if original_voice:
            self.config["piper_settings"]["voice"] = original_voice
        elif "voice" in self.config["piper_settings"]:
            del self.config["piper_settings"]["voice"]
        
        if not success:
            print(f"Failed to start voice test for {voice_id}")

    def on_vosk_model_selected(self, checked, model_size):
        """Handle Vosk model checkbox selection"""
        if checked:
            # Uncheck all other model checkboxes
            for size, widgets in self.vosk_model_widgets.items():
                if size != model_size:
                    widgets['checkbox'].setChecked(False)
    
            # Select this model
            self.select_vosk_model(model_size)

    def update_speed_spinner(self, value):
        """Update speed spinner when slider changes"""
        spinner_value = value / 100.0
        self.speed_spinner.blockSignals(True)
        self.speed_spinner.setValue(spinner_value)
        self.speed_spinner.blockSignals(False)

    def update_speed_slider(self, value):
        """Update speed slider when spinner changes"""
        slider_value = int(value * 100)
        self.speed_slider.blockSignals(True)
        self.speed_slider.setValue(slider_value)
        self.speed_slider.blockSignals(False)

    def select_voice(self, item):
        """Handle voice selection"""
        voice_id = item.data(Qt.UserRole)
        
        # Extract voice name from voice_id (remove "piper-" prefix)
        if voice_id.startswith("piper-"):
            voice_name = voice_id[6:]  # Remove "piper-" prefix
        
            # Update config with new structure
            if "tts_settings" not in self.config:
                self.config["tts_settings"] = {}
            self.config["tts_settings"]["engine"] = "piper"
            
            if "piper_settings" not in self.config:
                self.config["piper_settings"] = {}
            self.config["piper_settings"]["voice"] = voice_name
        
            # Save immediately
            self.save_config_immediately()
        
            # Update label
            self.current_voice_label.setText(f"Current voice: {voice_name.title()}")

    def select_dictation_engine_and_navigate(self, engine, page_index):
        """Select dictation engine and navigate to settings page if applicable"""
        # Update config with selected engine
        if "dictation_settings" not in self.config:
            self.config["dictation_settings"] = {}

        self.config["dictation_settings"]["engine"] = engine

        # Save immediately
        self.save_config_immediately()

        # Navigate to settings page if provided
        if page_index is not None:
            self.show_page(page_index)

    def accept(self):
        """Close dialog and emit settings changed signal"""
        # Only save editor settings (non-config settings) one final time
        self.settings["show_toolbar"] = self.toolbar_toggle.isChecked() if hasattr(self, 'toolbar_toggle') else self.settings.get("show_toolbar", True)
        self.settings["show_line_numbers"] = self.line_numbers_toggle.isChecked() if hasattr(self, 'line_numbers_toggle') else self.settings.get("show_line_numbers", False)
        self.settings["default_zoom"] = self.default_zoom_spinner.value() if hasattr(self, 'default_zoom_spinner') else self.settings.get("default_zoom", 100)

        # Emit signal with editor settings
        self.settingsChanged.emit(self.settings)

        # Close dialog
        super().accept()

    def download_vosk_model(self, model_size):
        """Download a Vosk model using QProcess for cancelability"""
        try:
            model_info = self.vosk_models.get("vosk", {}).get(model_size, {})
            if not model_info:
                QMessageBox.warning(self, "Error", f"Model {model_size} not found in configuration")
                return
    
            # Create cancelable progress dialog
            self.download_dialog = QProgressDialog(f"Downloading Vosk {model_size} model...", "Cancel", 0, 0, self)
            self.download_dialog.setWindowTitle("Downloading Model")
            self.download_dialog.setWindowModality(Qt.WindowModal)
            self.download_dialog.setAutoClose(True)
            self.download_dialog.setAutoReset(True)
            
            # Connect cancel to process termination
            self.download_dialog.canceled.connect(self.cancel_vosk_download)
            
            # Create download process
            self.download_process = VoskModelDownloadProcess(
                model_size,
                model_info.get("url"),
                str(self.assistivox_dir)
            )
            self.download_process.finished.connect(lambda success, message: self.on_vosk_model_download_finished(success, message, model_size))
            self.download_process.progress_update.connect(self.download_dialog.setLabelText)
            
            # Show dialog and start download
            self.download_dialog.show()
            self.download_process.start()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to start download: {str(e)}")
    
    def cancel_vosk_download(self):
        """Cancel the download process"""
        if hasattr(self, 'download_process'):
            self.download_process.terminate()
            if hasattr(self, 'download_dialog'):
                self.download_dialog.close()

    def on_vosk_model_download_finished(self, success, message, model_size):
        """Handle Vosk model download completion"""
        # Close download dialog
        if hasattr(self, 'download_dialog'):
            self.download_dialog.close()
    
        if success:
            # Update config - save to vosk_settings section
            if "vosk_settings" not in self.config:
                self.config["vosk_settings"] = {}
        
            self.config["vosk_settings"]["model"] = model_size
            
            # Update dictation engine to Vosk
            if "dictation_settings" not in self.config:
                self.config["dictation_settings"] = {}
        
            self.config["dictation_settings"]["engine"] = "vosk"
        
            # Save config immediately
            self.save_config_immediately()
        
            # Reload and reconstruct the Vosk settings page
            self.load_vosk_settings()
        else:
            # Show error popup only on failure
            QMessageBox.warning(self, "Download Failed", f"Failed to download model: {message}")
        
            # Still reload settings to refresh UI state
            self.load_vosk_settings()

    def select_vosk_model(self, model_size):
        """Select a Vosk model"""
        # Update config - save to vosk_settings section
        if "vosk_settings" not in self.config:
            self.config["vosk_settings"] = {}
    
        self.config["vosk_settings"]["model"] = model_size
    
        # Update dictation engine
        if "dictation_settings" not in self.config:
            self.config["dictation_settings"] = {}
    
        self.config["dictation_settings"]["engine"] = "vosk"
        
        # Save config immediately
        self.save_config_immediately()
    
        # Reload settings to update UI
        self.load_vosk_settings()

    def download_vosk_small(self):
        """Download Vosk small model"""
        # Create and show progress dialog
        progress_dialog = QProgressDialog("Downloading Vosk small model...", "Cancel", 0, 0, self)
        progress_dialog.setWindowTitle("Downloading Model")
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.show()
    
        # Create download thread
        self.download_thread = VoskDownloadThread(str(self.assistivox_dir))
        self.download_thread.progress_update.connect(progress_dialog.setLabelText)
        self.download_thread.finished.connect(self.on_vosk_download_finished)
        self.download_thread.finished.connect(progress_dialog.close)
    
        # Start download
        self.download_thread.start()

    def on_vosk_download_finished(self, success, message):
        """Handle Vosk download completion"""
        if success:
            # Automatically select the downloaded model
            self.select_vosk_small()
            QMessageBox.information(self, "Success", 
                               "Vosk small model downloaded and selected successfully!")
        else:
            QMessageBox.warning(self, "Download Failed", f"Failed to download model: {message}")

        # Update UI
        self.load_vosk_status()

    def load_fw_settings(self):
        """Load Faster Whisper settings and update model list UI"""
        try:
            from gui.models.stt_models import load_installed_stt_models
            
            # Get installed models
            installed_models = load_installed_stt_models(str(self.assistivox_dir))
            fw_installed = installed_models.get("faster-whisper", [])
            
            # Get selected model from CORRECTED config sections
            selected_model = None
            if ("dictation_settings" in self.config and 
                self.config["dictation_settings"].get("engine") == "faster-whisper" and
                "faster_whisper_settings" in self.config and
                "model" in self.config["faster_whisper_settings"]):
                selected_model = self.config["faster_whisper_settings"]["model"]
    
            # Update current model label
            if selected_model:
                self.fw_current_model_label.setText(f"Current model: Faster Whisper {selected_model.title()}")
            else:
                self.fw_current_model_label.setText("Current model: None")
            
            # Update each model widget
            for model_size, widgets in self.fw_model_widgets.items():
                is_installed = model_size in fw_installed
                is_selected = selected_model == model_size if selected_model else False
                
                # Enable/disable and check/uncheck the checkbox
                widgets['checkbox'].setEnabled(is_installed)
                widgets['checkbox'].setChecked(is_selected and is_installed)
                
                # Show/hide download button based on installation status
                widgets['download_button'].setVisible(not is_installed)
               
                widgets['checkbox'].setText(f"{model_size.title()} Model")

        except ImportError:
            # Handle case where stt_models is not available
            for model_size, widgets in self.fw_model_widgets.items():
                widgets['checkbox'].setText("Cannot check status")
                widgets['checkbox'].setEnabled(False)
                widgets['download_button'].setVisible(False)
        
        # Load GPU setting if GPU is available
        if self.gpu_available and hasattr(self, 'fw_use_gpu_toggle'):
            use_gpu = self.config.get("faster_whisper_settings", {}).get("use_gpu", True)
            if use_gpu and not self._detect_gpu():
                use_gpu = False
                if "faster_whisper_settings" not in self.config:
                    self.config["faster_whisper_settings"] = {}
                self.config["faster_whisper_settings"]["use_gpu"] = False
                self.save_config_immediately()
            
            self.fw_use_gpu_toggle.setChecked(use_gpu)
        
        # Load auto sentence format setting (MOVED OUTSIDE THE GPU CONDITIONAL)
        if "faster_whisper_settings" in self.config and "auto_sentence_format" in self.config["faster_whisper_settings"]:
            self.fw_auto_sentence_format_toggle.setChecked(self.config["faster_whisper_settings"]["auto_sentence_format"])
        else:
            self.fw_auto_sentence_format_toggle.setChecked(True)

        # Set up auto-save connections - use the same pattern as Vosk
        self.setup_fw_toggle_connections()

    def setup_fw_toggle_connections(self):
        """Connect Faster Whisper toggles to auto-save"""
        if hasattr(self, 'fw_auto_sentence_format_toggle'):
            self.fw_auto_sentence_format_toggle.toggled.connect(self.on_fw_settings_changed)

    def on_fw_model_selected(self, checked, model_size):
        """Handle Faster Whisper model checkbox selection"""
        if checked:
            # Uncheck all other checkboxes
            for size, widgets in self.fw_model_widgets.items():
                if size != model_size:
                    widgets['checkbox'].setChecked(False)
            
            # Update config - CORRECTED: Save to proper sections
            # Set dictation engine
            if "dictation_settings" not in self.config:
                self.config["dictation_settings"] = {}
            self.config["dictation_settings"]["engine"] = "faster-whisper"
            
            # Set faster-whisper model
            if "faster_whisper_settings" not in self.config:
                self.config["faster_whisper_settings"] = {}
            self.config["faster_whisper_settings"]["model"] = model_size
            
            # Save immediately
            self.save_config_immediately()
            
            # Update label
            self.fw_current_model_label.setText(f"Current model: Faster Whisper {model_size.title()}")
    
    def download_fw_model(self, model_size):
        """Download a Faster Whisper model with console output display"""
        try:
            # Get model info from stt.json
            model_info = self.faster_whisper_models.get("faster-whisper", {}).get(model_size, {})
            if not model_info:
                QMessageBox.warning(self, "Error", f"Model {model_size} not found in stt.json")
                return
    
            # Create console download dialog
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
            from PySide6.QtCore import Qt
            
            self.console_dialog = QDialog(self)
            self.console_dialog.setWindowTitle(f"Downloading Faster Whisper {model_size.title()} Model")
            self.console_dialog.setMinimumSize(600, 400)
            self.console_dialog.setModal(True)
            
            layout = QVBoxLayout(self.console_dialog)
            
            # Console output area
            self.console_output = QTextEdit()
            self.console_output.setReadOnly(True)
            self.console_output.setStyleSheet("""
                QTextEdit {
                    background-color: #1e1e1e;
                    color: #ffffff;
                    font-family: 'Consolas', 'Monaco', 'Lucida Console', monospace;
                    font-size: 10pt;
                    border: 1px solid #555;
                }
            """)
            layout.addWidget(self.console_output)
            
            # Button layout
            button_layout = QHBoxLayout()
            
            # Cancel button
            self.cancel_button = QPushButton("Cancel Download")
            self.cancel_button.clicked.connect(self.cancel_fw_download)
            button_layout.addWidget(self.cancel_button)
            
            # Close button (initially hidden)
            self.close_button = QPushButton("Close")
            self.close_button.clicked.connect(self.console_dialog.accept)
            self.close_button.setVisible(False)
            button_layout.addWidget(self.close_button)
            
            button_layout.addStretch()
            layout.addLayout(button_layout)
            
            # Create download process
            self.download_process = FasterWhisperDownloadProcess(
                model_size,
                model_info,
                str(self.assistivox_dir)
            )
            self.download_process.finished.connect(lambda success, message: self.on_fw_console_download_finished(success, message, model_size))
            self.download_process.progress_update.connect(self.append_console_output)
            
            # Show dialog and start download
            self.console_dialog.show()
            self.append_console_output(f"=== Downloading Faster Whisper {model_size.title()} Model ===")
            self.download_process.start()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to start download: {str(e)}")

    def append_console_output(self, text):
        """Append text to console output and auto-scroll"""
        if hasattr(self, 'console_output'):
            self.console_output.append(text)
            # Auto-scroll to bottom
            scrollbar = self.console_output.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    def on_fw_console_download_finished(self, success, message, model_size):
        """Handle Faster Whisper console download completion"""
        if success:
            self.append_console_output(f"\n=== SUCCESS ===")
            self.append_console_output(message)
            
            # Update config - CORRECTED: Save to proper sections
            # Set dictation engine
            if "dictation_settings" not in self.config:
                self.config["dictation_settings"] = {}
            self.config["dictation_settings"]["engine"] = "faster-whisper"
            
            # Set faster-whisper model
            if "faster_whisper_settings" not in self.config:
                self.config["faster_whisper_settings"] = {}
            self.config["faster_whisper_settings"]["model"] = model_size
            
            # Save config immediately
            self.save_config_immediately()
            
            self.append_console_output(f"\nRefreshing settings page...")
            
            # Auto-close and reload with delay
            from PySide6.QtCore import QTimer
            def delayed_reload_and_close():
                self.load_fw_settings()
                self.append_console_output("Settings refreshed!")
                self.append_console_output("Closing in 2 seconds...")
                QTimer.singleShot(2000, self.console_dialog.accept)
            
            QTimer.singleShot(1000, delayed_reload_and_close)
            
        else:
            self.append_console_output(f"\n=== FAILED ===")
            self.append_console_output(f"Error: {message}")
            self.append_console_output(f"\nClosing in 3 seconds...")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(3000, self.console_dialog.accept)
        
        # Hide cancel button and show close button
        if hasattr(self, 'cancel_button'):
            self.cancel_button.setVisible(False)
        if hasattr(self, 'close_button'):
            self.close_button.setVisible(True)

    def cancel_fw_download(self):
        """Cancel the faster-whisper download process"""
        if hasattr(self, 'download_process'):
            self.append_console_output("\n*** CANCELLING DOWNLOAD ***")
            self.download_process.terminate()
            if hasattr(self, 'console_dialog'):
                self.console_dialog.accept()

    def on_fw_model_download_finished(self, success, message, model_size):
        """Handle Faster Whisper model download completion"""
        # Close download dialog
        if hasattr(self, 'download_dialog'):
            self.download_dialog.close()

        if success:
            # Update config - CORRECTED: Save to proper sections
            # Set dictation engine
            if "dictation_settings" not in self.config:
                self.config["dictation_settings"] = {}
            self.config["dictation_settings"]["engine"] = "faster-whisper"
        
            # Set faster-whisper model
            if "faster_whisper_settings" not in self.config:
                self.config["faster_whisper_settings"] = {}
            self.config["faster_whisper_settings"]["model"] = model_size

    def on_fw_settings_changed(self):
        """Handle Faster Whisper settings changes"""
        if "faster_whisper_settings" not in self.config:
            self.config["faster_whisper_settings"] = {}
        
        # Save GPU setting if available
        if self.gpu_available and hasattr(self, 'fw_use_gpu_toggle'):
            use_gpu = self.fw_use_gpu_toggle.isChecked()
            # Validate GPU is still available if trying to enable
            if use_gpu and not self._detect_gpu():
                use_gpu = False
                self.fw_use_gpu_toggle.setChecked(False)
            
            self.config["faster_whisper_settings"]["use_gpu"] = use_gpu
        
        # Save auto sentence format setting
        if hasattr(self, 'fw_auto_sentence_format_toggle'):
            self.config["faster_whisper_settings"]["auto_sentence_format"] = self.fw_auto_sentence_format_toggle.isChecked()
        
        # Save immediately
        self.save_config_immediately()

    def add_piper_download_button_if_needed(self, voices_layout, voices_group):
        """Add download button below voice list if there are uninstalled voices available"""
        # Get available voices from tts.json
        MODEL_MAP = load_model_map()
        available_voices = set(MODEL_MAP.get("piper", {}).keys())

        # Get installed voices
        installed_voices = list_installed_tts_models(str(self.assistivox_dir))
        installed_piper = set(installed_voices.get("piper", []))

        # Check if there are uninstalled voices
        uninstalled_voices = available_voices - installed_piper

        if uninstalled_voices:
            download_button = QPushButton("Download Piper Voice Pack")
            download_button.clicked.connect(self.show_bulk_piper_download_dialog)
            voices_layout.addWidget(download_button)

    def show_bulk_piper_download_dialog(self):
        """Show dialog to download all available uninstalled Piper voices"""
        try:
            from gui.settings.piper_bulk_download_dialog import PiperBulkDownloadDialog
    
            # Get list of uninstalled voices
            MODEL_MAP = load_model_map()
            available_voices = set(MODEL_MAP.get("piper", {}).keys())
            installed_voices = list_installed_tts_models(str(self.assistivox_dir))
            installed_piper = set(installed_voices.get("piper", []))
            uninstalled_voices = list(available_voices - installed_piper)
    
            if not uninstalled_voices:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, "All Voices Installed",
                                      "All available Piper voices are already installed.")
                return
    
            dialog = PiperBulkDownloadDialog(self.assistivox_dir, uninstalled_voices, self)
    
            if dialog.exec() == QDialog.Accepted:
                # Recreate the page to update download button visibility
                current_index = self.stacked_widget.currentIndex()
                if current_index == 2:  # Piper settings page index
                    # Remove the old page
                    widget_to_remove = self.stacked_widget.widget(2)
                    self.stacked_widget.removeWidget(widget_to_remove)
                    widget_to_remove.deleteLater()
    
                    # Create new page using the existing method
                    self.create_piper_settings_page()
    
                    # The new page gets added at the end, so we need to move it to index 2
                    new_page = self.stacked_widget.widget(self.stacked_widget.count() - 1)
                    self.stacked_widget.removeWidget(new_page)
                    self.stacked_widget.insertWidget(2, new_page)
                    self.stacked_widget.setCurrentIndex(2)
                    
                    # NOW refresh the voice list on the NEW page
                    self.load_voice_list()
    
        except ImportError:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Not Implemented",
                                  "Bulk voice download dialog not yet implemented.")

class VoskModelDownloadProcess(QObject):
    """Process for downloading Vosk models with cancelability"""
    finished = Signal(bool, str)
    progress_update = Signal(str)

    def __init__(self, model_size, download_url, assistivox_dir):
        super().__init__()
        self.model_size = model_size
        self.download_url = download_url
        self.assistivox_dir = assistivox_dir
        self.process = None
        self.cancelled = False

    def start(self):
        """Start the download process"""
        # Use Python subprocess to run download in separate process
        import threading
        self.download_thread = threading.Thread(target=self._download_model)
        self.download_thread.daemon = True
        self.download_thread.start()

    def terminate(self):
        """Terminate the download process"""
        self.cancelled = True

    def _download_model(self):
        """Download and install the model"""
        try:
            if self.cancelled:
                return
    
            import tempfile
            import zipfile
            import requests
            import shutil
    
            # Load model ID from stt.json
            try:
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                stt_json_path = os.path.join(project_root, "stt.json")
    
                with open(stt_json_path, 'r') as f:
                    stt_data = json.load(f)
    
                model_id = stt_data["vosk"][self.model_size]["model_id"]
            except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
                self.finished.emit(False, f"Model ID not found for size {self.model_size}: {str(e)}")
                return

            self.progress_update.emit(f"Starting download of {self.model_size} model...")
    
            # Create target directory using model ID: <base_path>/stt-models/vosk/<model_id>/
            final_target_dir = os.path.join(self.assistivox_dir, "stt-models", "vosk", model_id)
            temp_extract_dir = os.path.join(self.assistivox_dir, "stt-models", "vosk", f"temp_{model_id}")
            
            # Clean up any existing temp directory
            if os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
            
            os.makedirs(temp_extract_dir, exist_ok=True)
    
            if self.cancelled:
                return
    
            # Create temporary file for download
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
                temp_zip_path = temp_file.name
    
            self.progress_update.emit("Downloading model file...")
    
            # Download the model
            response = requests.get(self.download_url, stream=True)
            response.raise_for_status()
    
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
    
            with open(temp_zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self.cancelled:
                        os.unlink(temp_zip_path)
                        return
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            self.progress_update.emit(f"Downloading... {percent}%")
    
            if self.cancelled:
                os.unlink(temp_zip_path)
                return
    
            self.progress_update.emit("Extracting model...")
    
            # Extract the model to temp directory
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)
    
            # Remove temporary zip file
            os.unlink(temp_zip_path)
    
            if self.cancelled:
                return
    
            self.progress_update.emit("Installing model...")
    
            # Find the actual model directory inside the extracted content
            # Look for the directory that contains the model files
            extracted_contents = os.listdir(temp_extract_dir)
            
            model_source_dir = None
            for item in extracted_contents:
                item_path = os.path.join(temp_extract_dir, item)
                if os.path.isdir(item_path):
                    # Check if this directory contains model files (look for 'am' directory)
                    if os.path.exists(os.path.join(item_path, "am")):
                        model_source_dir = item_path
                        break
    
            if not model_source_dir:
                # If no nested directory with model files, use the temp directory itself
                if os.path.exists(os.path.join(temp_extract_dir, "am")):
                    model_source_dir = temp_extract_dir
    
            if not model_source_dir:
                shutil.rmtree(temp_extract_dir)
                self.finished.emit(False, "Could not find model files in downloaded archive")
                return
    
            # Remove existing target directory if it exists
            if os.path.exists(final_target_dir):
                shutil.rmtree(final_target_dir)
    
            # Move the model files to the final location
            shutil.move(model_source_dir, final_target_dir)
    
            # Clean up temp directory
            if os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
    
            if self.cancelled:
                return
    
            self.finished.emit(True, "Model downloaded successfully")
    
        except Exception as e:
            # Clean up on error
            if 'temp_zip_path' in locals() and os.path.exists(temp_zip_path):
                os.unlink(temp_zip_path)
            if 'temp_extract_dir' in locals() and os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
            self.finished.emit(False, str(e))


class FasterWhisperDownloadProcess(QObject):
    """Process for downloading Faster Whisper models with cancelability"""
    finished = Signal(bool, str)
    progress_update = Signal(str)

    def __init__(self, model_size, model_info, assistivox_dir):
        super().__init__()
        self.model_size = model_size
        self.model_info = model_info
        self.assistivox_dir = assistivox_dir
        self.process = None
        self.cancelled = False

    def start(self):
        """Start the download process"""
        import threading
        self.download_thread = threading.Thread(target=self._download_model)
        self.download_thread.daemon = True
        self.download_thread.start()

    def terminate(self):
        """Terminate the download process"""
        self.cancelled = True

    def _download_model(self):
        """Download and install the Faster Whisper model using Hugging Face Hub with real-time output capture"""
        try:
            if self.cancelled:
                return
    
            import sys
            import io
            import contextlib
    
            # Check if huggingface_hub is available
            try:
                from huggingface_hub import snapshot_download
                import os
            except ImportError:
                self.finished.emit(False, "huggingface_hub is not installed. Please install it first.")
                return
    
            model_id = self.model_info["model_id"]
    
            self.progress_update.emit(f"Model: {model_id}")
            self.progress_update.emit(f"Size: {self.model_size}")
    
            # Target directory
            target_dir = os.path.join(
                self.assistivox_dir,
                "stt-models",
                "faster-whisper",
                model_id
            )
    
            self.progress_update.emit(f"Target directory: {target_dir}")
    
            if self.cancelled:
                return
    
            # Create target directory
            os.makedirs(target_dir, exist_ok=True)
            self.progress_update.emit("Created target directory")
    
            # Create a custom stdout/stderr capturer
            class OutputCapture:
                def __init__(self, progress_callback, cancelled_check):
                    self.progress_callback = progress_callback
                    self.cancelled_check = cancelled_check
                    self.buffer = ""
    
                def write(self, text):
                    if self.cancelled_check():
                        return len(text)
    
                    self.buffer += text
                    # Emit line by line
                    lines = self.buffer.split('\n')
                    self.buffer = lines[-1]  # Keep incomplete line in buffer
    
                    for line in lines[:-1]:  # Process complete lines
                        if line.strip():  # Only emit non-empty lines
                            self.progress_callback(line.strip())
    
                    return len(text)
    
                def flush(self):
                    if self.buffer.strip():
                        self.progress_callback(self.buffer.strip())
                        self.buffer = ""
    
            # Re-enable tqdm but capture its output
            if 'HF_HUB_DISABLE_PROGRESS_BARS' in os.environ:
                del os.environ['HF_HUB_DISABLE_PROGRESS_BARS']
    
            self.progress_update.emit("Connecting to Hugging Face Hub...")
    
            try:
                # Create output capturer
                output_capture = OutputCapture(self.progress_update.emit, lambda: self.cancelled)
    
                self.progress_update.emit("Starting download from Hugging Face...")
                self.progress_update.emit("Progress will be shown below:")
                self.progress_update.emit("-" * 50)
    
                # Redirect stdout and stderr to capture huggingface_hub output
                with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(output_capture):
                    downloaded_path = snapshot_download(
                        repo_id=model_id,
                        local_dir=target_dir,
                        local_dir_use_symlinks=False,
                        ignore_patterns=["*.md", "*.bib"],
                        resume_download=True
                    )
    
                if self.cancelled:
                    return
    
                self.progress_update.emit("-" * 50)
                self.progress_update.emit(f"Download completed successfully!")
                self.progress_update.emit(f"Model installed to: {downloaded_path}")
    
                # Verify installation
                if os.path.exists(downloaded_path) and os.listdir(downloaded_path):
                    self.progress_update.emit("Installation verified - model files present")
                    self.finished.emit(True, f"Successfully installed {self.model_size} model")
                else:
                    self.finished.emit(False, "Download completed but model files not found")
    
            except Exception as e:
                if not self.cancelled:
                    self.progress_update.emit(f"Exception occurred: {str(e)}")
                    self.finished.emit(False, f"Error downloading model: {str(e)}")
    
        except Exception as e:
            if not self.cancelled:
                self.progress_update.emit(f"Exception occurred: {str(e)}")
                self.finished.emit(False, f"Error downloading model: {str(e)}")

