#!/usr/bin/env python3
"""
Assistivox Setup Script
Creates the virtual environment and installs required components.
"""

import os
import sys
import json
import subprocess
import venv
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

# Configuration
ASSISTIVOX_DIR = Path.home() / ".assistivox"
VENV_DIR = ASSISTIVOX_DIR / "venv"
CONFIG_PATH = ASSISTIVOX_DIR / "config.json"
PIPER_DIR = ASSISTIVOX_DIR / "piper"
TTS_MODELS_DIR = ASSISTIVOX_DIR / "tts-models" / "piper"
DEFAULT_CONFIG = {
    "appearance": {
        "dark_mode": True,
        "editor_font_size": 14,
        "menu_font_size": 12,
        "button_font_size": 12,
        "dialog_font_size": 11
    },
    "editor": {
        "show_toolbar": True,
        "show_line_numbers": False,
        "default_zoom": 100
    },
    "piper_settings": {
        "path": str(ASSISTIVOX_DIR / "piper"),  # This works correctly
        "voice": "amy"
    },
    "tts_settings": {
        "engine": "piper",
        "speed": 1.0,
        "pause_ms": 500
    },
    "dictation_settings": {
        "engine": "vosk",
    },
    "vosk_settings": {
        "model": "small",
        "show_partial_text": True
    }
}

def print_step(message):
    """Print a step message"""
    print(f"\n=== {message} ===")

def setup_assistivox():
    """
    Setup Assistivox according to the specified steps:
    1. Create ~/.assistivox and create the virtual environment
    2. Install PySide6, Piper, Amy voice, sounddevice, and Vosk small model
    3. Create config file
    """
    try:
        # Step 1: Create ~/.assistivox and create virtual environment
        print_step("Step 1: Creating Assistivox directory and virtual environment")
        ASSISTIVOX_DIR.mkdir(exist_ok=True)
        
        # Check if we're already in a virtual environment
        in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
        
        if not in_venv:
            print("Creating virtual environment...")
            venv.create(VENV_DIR, with_pip=True)
            
            # Get the pip executable path
            if sys.platform.startswith('win'):
                pip_exe = VENV_DIR / "Scripts" / "pip.exe"
                python_exe = VENV_DIR / "Scripts" / "python.exe"
            else:
                pip_exe = VENV_DIR / "bin" / "pip"
                python_exe = VENV_DIR / "bin" / "python"
        else:
            print("Already in a virtual environment, using it...")
            pip_exe = "pip"
            python_exe = sys.executable
        
        # Step 2: Install PySide6, Piper, Amy voice, and sounddevice
        print_step("Step 2: Installing required packages and components")
        
        # Install PySide6
        print("Installing PySide6...")
        subprocess.check_call([str(pip_exe), "install", "PySide6"])
        
        # Install sound-related packages
        print("Installing audio dependencies...")
        subprocess.check_call([str(pip_exe), "install", "sounddevice", "soundfile", "numpy"])
        
        # Set up Piper
        print("Setting up Piper...")
        setup_piper()
        
        # Download Amy voice
        print("Downloading Amy voice model...")
        download_amy_voice()

        # Download Vosk small model
        print("Downloading Vosk small STT model...")
        download_vosk_small_model()
        
        # Step 3: Create config file
        print_step("Step 3: Creating configuration file")
        if not CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
            print("Configuration file created")
        else:
            # Update existing config with new keys
            with open(CONFIG_PATH, 'r') as f:
                existing_config = json.load(f)
            
            # Update with defaults but preserve user settings
            merge_configs(existing_config, DEFAULT_CONFIG)
            
            with open(CONFIG_PATH, 'w') as f:
                json.dump(existing_config, f, indent=2)
            print("Configuration file updated")

        # Create src directory and copy folders
        print("Setting up source directories...")
        src_dir = ASSISTIVOX_DIR / "src"
        src_dir.mkdir(exist_ok=True)
    
        # Copy gui and transcribe folders to .assistivox/src/
        import shutil
    
        current_dir = Path(__file__).parent
        gui_source = current_dir / "gui"
        transcribe_source = current_dir / "transcribe"
    
        if gui_source.exists():
            gui_dest = src_dir / "gui"
            if gui_dest.exists():
                shutil.rmtree(gui_dest)
            shutil.copytree(gui_source, gui_dest, ignore=shutil.ignore_patterns('__pycache__'))
            print(f"✅ Copied gui/ to {gui_dest}")
        else:
            print("⚠️ gui/ folder not found")
    
        if transcribe_source.exists():
            transcribe_dest = src_dir / "transcribe"
            if transcribe_dest.exists():
                shutil.rmtree(transcribe_dest)
            shutil.copytree(transcribe_source, transcribe_dest, ignore=shutil.ignore_patterns('__pycache__'))
            print(f"✅ Copied transcribe/ to {transcribe_dest}")
        else:
            print("⚠️ transcribe/ folder not found")

        # Copy icons directory
        icons_source = current_dir / "icons"
        if icons_source.exists():
            icons_dest = src_dir / "icons"
            if icons_dest.exists():
                shutil.rmtree(icons_dest)
            shutil.copytree(icons_source, icons_dest)
            print(f"✅ Copied icons/ to {icons_dest}")
        else:
            print("⚠️ icons/ folder not found")

        shutil.copy2(current_dir / "assistivox.py", src_dir / "assistivox.py")
        shutil.copy2(current_dir / "tts.json", src_dir / "tts.json") 
        shutil.copy2(current_dir / "stt.json", src_dir / "stt.json")

        # Now we can launch the GUI
        print_step("Initial setup complete! Launching GUI...")
        launch_gui(python_exe)
        
    except Exception as e:
        print(f"Error during setup: {str(e)}")
        sys.exit(1)

def merge_configs(target, source):
    """Recursively merge source config into target config"""
    for key, value in source.items():
        if key not in target:
            target[key] = value
        elif isinstance(value, dict) and isinstance(target[key], dict):
            merge_configs(target[key], value)

def setup_piper():
    """Download and set up Piper TTS engine - binary only"""
    import shutil
    
    PIPER_DIR.mkdir(exist_ok=True)
    
    # Detect Wine as Windows
    if sys.platform.startswith('win'):
        # Windows
        url = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
        zip_path = PIPER_DIR / "piper.zip"
        
        print("Downloading Piper Windows binary...")
        urlretrieve(url, zip_path)
        
        print("Extracting Piper...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(PIPER_DIR)
        
        # Rename extracted piper directory to build
        extracted_piper = PIPER_DIR / "piper"
        build_dir = PIPER_DIR / "build"
        if extracted_piper.exists():
            extracted_piper.rename(build_dir)
        
        os.remove(zip_path)
        print("Piper Windows binary installed")
        
    elif sys.platform.startswith('linux'):
        # Linux
        url = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"
        tar_path = PIPER_DIR / "piper.tar.gz"
        
        print("Downloading Piper Linux binary...")
        urlretrieve(url, tar_path)
        
        print("Extracting Piper...")
        subprocess.check_call(["tar", "-xzf", str(tar_path), "-C", str(PIPER_DIR)])
        
        # Rename extracted piper directory to build
        extracted_piper = PIPER_DIR / "piper"
        build_dir = PIPER_DIR / "build"
        if extracted_piper.exists():
            extracted_piper.rename(build_dir)
            # Make binary executable
            piper_bin = build_dir / "piper"
            if piper_bin.exists():
                os.chmod(piper_bin, 0o755)
        
        os.remove(tar_path)
        print("Piper Linux binary installed")
        
    elif sys.platform.startswith('darwin'):
        # macOS
        url = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_macos_x64.tar.gz"
        tar_path = PIPER_DIR / "piper.tar.gz"
        
        print("Downloading Piper macOS binary...")
        urlretrieve(url, tar_path)
        
        print("Extracting Piper...")
        subprocess.check_call(["tar", "-xzf", str(tar_path), "-C", str(PIPER_DIR)])
        
        # Rename extracted piper directory to build
        extracted_piper = PIPER_DIR / "piper"
        build_dir = PIPER_DIR / "build"
        if extracted_piper.exists():
            extracted_piper.rename(build_dir)
            # Make binary executable
            piper_bin = build_dir / "piper"
            if piper_bin.exists():
                os.chmod(piper_bin, 0o755)
        
        os.remove(tar_path)
        print("Piper macOS binary installed")
    
    else:
        raise Exception(f"Unsupported platform: {sys.platform}")

def download_amy_voice():
    """Download the Amy voice model for Piper"""
    # Create model directory
    TTS_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Amy voice directory
    amy_dir = TTS_MODELS_DIR / "amy"
    amy_dir.mkdir(exist_ok=True)
    
    # URLs for Amy voice files
    amy_files = [
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/MODEL_CARD"
    ]
    
    # Download each file
    for url in amy_files:
        filename = url.split("/")[-1]
        dest_path = amy_dir / filename
        
        if not dest_path.exists():
            print(f"Downloading {filename}...")
            urlretrieve(url, dest_path)
            print(f"{filename} downloaded")

def download_vosk_small_model():
    """Download the Vosk small English STT model"""
    # Create STT models directory
    stt_models_dir = ASSISTIVOX_DIR / "stt-models" / "vosk"
    stt_models_dir.mkdir(parents=True, exist_ok=True)

    url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    model_id = "vosk-model-small-en-us-0.15"
    zip_path = stt_models_dir / f"{model_id}.zip"

    try:
        print("Downloading Vosk small model...")
        urlretrieve(url, zip_path)

        print("Extracting Vosk model...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(stt_models_dir)

        # Remove zip file
        zip_path.unlink()
        print(f"✅ Vosk small model installed to {stt_models_dir / model_id}")

    except Exception as e:
        print(f"❌ Vosk download failed: {str(e)}")
        sys.exit(1)

def launch_gui(python_exe):
    """Launch the GUI setup with the installed Python"""
    try:
        # We'll create a temporary script to launch just the GUI portion
        # This ensures we're using the Python from the virtual environment
        gui_script = '''
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt, QTimer, Signal, QObject
import subprocess
import tempfile
import os
import threading
from pathlib import Path

# Get paths
ASSISTIVOX_DIR = Path.home() / ".assistivox"
PIPER_DIR = ASSISTIVOX_DIR / "piper"
TTS_MODELS_DIR = ASSISTIVOX_DIR / "tts-models" / "piper"

# Audio signal handler class to avoid blocking the main thread
class AudioSignalHandler(QObject):
    finished = Signal()

    def __init__(self):
        super().__init__()
        self._playing = False
        self._stop_requested = False

    def stop_playback(self):
        """Request to stop any ongoing playback"""
        self._stop_requested = True
        # Immediately stop sounddevice playback
        try:
            import sounddevice as sd
            sd.stop()
        except Exception as e:
            print(f"Error stopping audio: {str(e)}")
        self._playing = False

    def play_audio_non_blocking(self, audio_path):
        """Play audio file without blocking the UI thread"""
        if self._playing:
            return

        self._playing = True
        self._stop_requested = False

        # Start a separate thread for audio playback
        def audio_thread():
            try:
                import soundfile as sf
                import sounddevice as sd

                data, samplerate = sf.read(audio_path, dtype='float32')
                sd.play(data, samplerate)

                # Check for stop request while waiting
                import time
                while sd.get_stream().active and not self._stop_requested:
                    time.sleep(0.1)

                # Make sure playback is stopped
                sd.stop()

                # Clean up
                try:
                    os.unlink(audio_path)
                except:
                    pass

                # Signal completion but use QTimer to ensure signals happen in main thread
                if not self._stop_requested:
                    QTimer.singleShot(0, lambda: self.finished.emit())
                self._playing = False

            except Exception as e:
                print(f"Error playing audio: {str(e)}")
                self._playing = False

        # Start thread
        thread = threading.Thread(target=audio_thread)
        thread.daemon = True
        thread.start()

class TTSEngine:
    """Simple TTS engine for the installer using Piper"""
    def __init__(self):
        self.piper_bin = PIPER_DIR / "build" / "piper"
        if sys.platform.startswith('win'):
            self.piper_bin = PIPER_DIR / "build" / "piper.exe"
       
        self.model_path = TTS_MODELS_DIR / "amy" / "en_US-amy-medium.onnx"
        self.config_path = TTS_MODELS_DIR / "amy" / "en_US-amy-medium.onnx.json"
        
        # Check if files exist
        self.is_available = (
            self.piper_bin.exists() and 
            self.model_path.exists() and 
            self.config_path.exists()
        )
        
        # Create audio handler
        self.audio_handler = AudioSignalHandler()
    
    def speak(self, text, silence_ms=500):
        """Speak text using Piper TTS"""
        if not self.is_available:
            print(f"TTS not available: piper binary exists: {self.piper_bin.exists()}, model exists: {self.model_path.exists()}")
            return False
        
        try:
            # Create temp file for output
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                output_path = tmp.name
            
            # Generate speech with Piper
            cmd = [
                str(self.piper_bin),
                "--model", str(self.model_path),
                "--config", str(self.config_path),
                "--output_file", output_path,
                "--silence_ms", str(silence_ms)
            ]
            
            # Run Piper with text as input
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate(input=text)
            
            if process.returncode != 0:
                print(f"TTS process failed: {stderr}")
                return False
            
            # Play the audio without blocking
            self.audio_handler.play_audio_non_blocking(output_path)
            return True
        
        except Exception as e:
            print(f"TTS error: {str(e)}")
            return False

class SetupWindow(QMainWindow):
    """Main setup window for Assistivox"""
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Assistivox Setup")
        self.resize(600, 400)

        # Initialize TTS engine
        self.tts_engine = TTSEngine()
        self.tts_enabled = True

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Set up layout
        layout = QVBoxLayout(central_widget)

        # Add welcome title
        title_label = QLabel("Assistivox Setup")
        font = title_label.font()
        font.setPointSize(18)
        font.setBold(True)
        title_label.setFont(font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Add welcome text
        self.welcome_text = QLabel(
            """Welcome to the Assistivox setup wizard.

I have installed the basic components, but I need to complete the setup process by installing additional dependencies.

This setup is using text-to-speech to guide you through the installation process. You can turn this off with the button below.

Press Next to continue with the installation or Cancel to exit."""
        )
        self.welcome_text.setWordWrap(True)
        self.welcome_text.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.welcome_text)

        # Add button layout
        button_layout = QHBoxLayout()

        # TTS toggle button
        self.tts_button = QPushButton("Turn Off Text-to-Speech")
        self.tts_button.clicked.connect(self.toggle_tts)
        button_layout.addWidget(self.tts_button)

        # Spacer
        button_layout.addStretch()

        # Cancel button
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.close)
        button_layout.addWidget(cancel_button)

        # Next button
        next_button = QPushButton("Next")
        next_button.clicked.connect(self.on_next)
        button_layout.addWidget(next_button)

        # Add button layout to main layout
        layout.addLayout(button_layout)

        # Speak welcome message with a short delay
        QTimer.singleShot(500, self.speak_welcome)

    def speak_welcome(self):
        """Speak the welcome message"""
        if self.tts_enabled and self.tts_engine.is_available:
            self.tts_engine.speak(self.welcome_text.text())

    def toggle_tts(self):
        """Toggle text-to-speech on/off"""
        self.tts_enabled = not self.tts_enabled

        if self.tts_enabled:
            self.tts_button.setText("Turn Off Text-to-Speech")
        else:
            self.tts_button.setText("Turn On Text-to-Speech")
            # Stop any currently playing audio
            if hasattr(self.tts_engine, 'audio_handler'):
                import sounddevice as sd
                sd.stop()

    def on_next(self):
        """Handle Next button click - Install remaining packages"""
        from PySide6.QtWidgets import QProgressBar, QVBoxLayout, QDialog, QLabel
        from PySide6.QtCore import QThread, Signal, Qt
        import subprocess
        import sys
        
        # List of packages to install based on the codebase analysis
        packages_to_install = [
            "requests",
            "pathlib",
            "spacy", 
            "vosk",
            "pyaudio", 
            "audiostretchy",
            "faster-whisper", 
            "torch",
            "transformers",
            "huggingface_hub",
            "RealtimeSTT",
            "markdown",
            "reportlab",
            "python-doctr[torch,viz]",
            "pytesseract",
            "pdfplumber",
            "nupunkt",
            'pyshortcuts'
#            "nvidia-ml-py3"
        ]
    
        class PackageInstallThread(QThread):
            """Thread for installing packages without blocking the GUI"""
            package_started = Signal(str)
            package_completed = Signal(str)
            all_completed = Signal()
            error_occurred = Signal(str)
            
            def __init__(self, packages, pip_exe):
                super().__init__()
                self.packages = packages
                self.pip_exe = pip_exe

            def run(self):
                """Install each package and spacy model"""
                # Install regular pip packages first
                for package in self.packages:
                    try:
                        self.package_started.emit(package)
                        result = subprocess.run([str(self.pip_exe), "install", package], 
                                              capture_output=True, text=True, check=True)
                        self.package_completed.emit(package)
                    except subprocess.CalledProcessError as e:
                        self.error_occurred.emit(f"Failed to install {package}: {e.stderr}")
                        return
                    except Exception as e:
                        self.error_occurred.emit(f"Error installing {package}: {str(e)}")
                        return
                
                # Install spacy model as final step
                try:
                    self.package_started.emit("en_core_web_sm spacy model")
                
                    # Use python -m spacy download for spacy model
                    python_exe = str(Path(self.pip_exe).parent / "python")
                    if sys.platform.startswith('win'):
                        python_exe = str(Path(self.pip_exe).parent / "python.exe")
                
                    result = subprocess.run([python_exe, "-m", "spacy", "download", "en_core_web_sm"], 
                                          capture_output=True, text=True, check=True)
                    self.package_completed.emit("en_core_web_sm spacy model")
                except subprocess.CalledProcessError as e:
                    self.error_occurred.emit(f"Failed to install spacy model: {e.stderr}")
                    return
                except Exception as e:
                    self.error_occurred.emit(f"Error installing spacy model: {str(e)}")
                    return
        
                self.all_completed.emit()
    
        # Create installation dialog
        install_dialog = QDialog(self)
        install_dialog.setWindowTitle("Installing Packages")
        install_dialog.setMinimumWidth(400)
        install_dialog.setMinimumHeight(200)
        
        layout = QVBoxLayout(install_dialog)
        
        # Status label
        status_label = QLabel("Preparing to install packages...")
        layout.addWidget(status_label)
        
        # Current package label  
        current_package_label = QLabel("")
        layout.addWidget(current_package_label)
        
        # Progress bar
        progress_bar = QProgressBar()
        progress_bar.setMinimum(0)
        progress_bar.setMaximum(len(packages_to_install) + 1)  # +1 for spacy model
        progress_bar.setValue(0)
        layout.addWidget(progress_bar)
        
        # Get pip executable path
        ASSISTIVOX_DIR = Path.home() / ".assistivox"
        VENV_DIR = ASSISTIVOX_DIR / "venv"

        # Check if we're already in a virtual environment
        in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)

        if in_venv:
            # Use current venv's pip
            pip_exe = str(Path(sys.executable).parent / "pip")
        else:
            # Use the assistivox venv pip
            if sys.platform.startswith('win'):
                pip_exe = str(VENV_DIR / "Scripts" / "pip.exe")
            else:
                pip_exe = str(VENV_DIR / "bin" / "pip")

        # Create and start the installation thread
        install_thread = PackageInstallThread(packages_to_install, pip_exe)
        
        # Connect signals
        def on_package_started(package):
            current_package_label.setText(f"Installing: {package}")
            if self.tts_enabled and self.tts_engine and self.tts_engine.is_available:
                self.tts_engine.speak(f"Installing {package}")
        
        def on_package_completed(package):
            current_value = progress_bar.value()
            progress_bar.setValue(current_value + 1)

        def on_all_completed():
            status_label.setText("All packages installed successfully!")
            current_package_label.setText("Installation complete")
            if self.tts_enabled and self.tts_engine and self.tts_engine.is_available:
                self.tts_engine.speak("All packages installed successfully. Setup is complete.")
            
            # Create desktop shortcut as final step
            try:
                # Get paths
                assistivox_dir = Path.home() / ".assistivox"
                assistivox_script = assistivox_dir / "src" / "assistivox.py"
                
                # Select icon from copied icons directory
                icon_path = None
                icons_dir = assistivox_dir / "src" / "icons"
                
                if icons_dir.exists():
                    if sys.platform.startswith('win'):
                        icon_file = icons_dir / "assistivox-waveform.ico"
                    elif sys.platform == 'darwin':
                        icon_file = icons_dir / "assistivox-waveform.icns"
                    else:
                        icon_file = icons_dir / "assistivox-waveform_512.png"
                    
                    if icon_file.exists():
                        icon_path = str(icon_file)

                # Determine Python executable
                in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
                if in_venv:
                    python_exe = sys.executable
                else:
                    venv_dir = assistivox_dir / "venv"
                    if sys.platform.startswith('win'):
                        python_exe = str(venv_dir / "Scripts" / "python.exe")
                    else:
                        python_exe = str(venv_dir / "bin" / "python")

                if sys.platform.startswith('linux'):
                    # Create .desktop file manually for Linux
                    desktop_path = Path.home() / "Desktop" / "AssistiVox AI.desktop"
                    
                    desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=AssistiVox AI
Comment=Voice-Enabled Content Productivity Suite
Exec="{python_exe}" "{assistivox_script}"
Icon={icon_path if icon_path else ""}
Terminal=false
StartupNotify=true
Categories=Accessibility;Office;TextEditor;
"""
                    
                    # Write the .desktop file
                    with open(desktop_path, 'w') as f:
                        f.write(desktop_content)
                    
                    # Make it executable and trusted
                    import stat
                    os.chmod(desktop_path, 0o755)
                    
                    # Set the trusted bit using gio (GNOME's file manager)
                    try:
                        subprocess.run(['gio', 'set', str(desktop_path), 'metadata::trusted', 'true'], 
                                     check=True, capture_output=True)
                        print("Desktop shortcut created and marked as trusted")
                    except subprocess.CalledProcessError:
                        print("Desktop shortcut created (could not mark as trusted - user will need to right-click and Allow Launching)")
                else:
                    # Use pyshortcuts for Windows and Mac
                    from pyshortcuts import make_shortcut
                    
                    make_shortcut(
                        str(assistivox_script),
                        name="AssistiVox AI",
                        description="AssistiVox AI - Voice-Enabled Content Productivity Suite",
                        icon=icon_path,
                        terminal=False
                    )
                    print("Desktop shortcut created")

            except Exception as e:
                print(f"Failed to create desktop shortcut: {str(e)}")
            
            # Close the dialog after a brief delay
            QTimer.singleShot(2000, install_dialog.accept)
            # Close the main setup window after install dialog closes
            QTimer.singleShot(2500, self.close)

        def on_error_occurred(error_message):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(install_dialog, "Installation Error", error_message)
            install_dialog.reject()
        
        install_thread.package_started.connect(on_package_started)
        install_thread.package_completed.connect(on_package_completed)
        install_thread.all_completed.connect(on_all_completed)
        install_thread.error_occurred.connect(on_error_occurred)
        
        # Show dialog and start installation
        install_dialog.show()
        install_thread.start()
        
        # Make the dialog modal
        install_dialog.exec()
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Stop any playing audio when closing
        if hasattr(self.tts_engine, 'audio_handler'):
            import sounddevice as sd
            sd.stop()
        event.accept()

    def keyPressEvent(self, event):
        """Handle key press events"""
        # Enter/Return works like clicking the Next button
        if event.key() in (Qt.Key_Enter, Qt.Key_Return):
            self.on_next()
        # Escape key closes the window
        elif event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

def main():
    app = QApplication(sys.argv)
    window = SetupWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
'''
        
        # Write GUI script to a temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            gui_script_path = f.name
            f.write(gui_script)
        
        # Make it executable
        os.chmod(gui_script_path, 0o755)
        
        # Launch the GUI script
        subprocess.Popen([str(python_exe), gui_script_path])
        
    except Exception as e:
        print(f"Error launching GUI: {str(e)}")

def main():
    """Main entry point for the setup script"""
    setup_assistivox()

if __name__ == "__main__":
    main()
