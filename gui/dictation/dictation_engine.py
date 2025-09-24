# File: gui/dictation/dictation_engine.py
# This file should be placed in the gui directory of your project

import os
import sys
import json
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThread

# Import necessary components for different STT engines
try:
    import pyaudio
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

try:
    from RealtimeSTT import AudioToTextRecorder
    REALTIMESTT_AVAILABLE = True
except ImportError:
    REALTIMESTT_AVAILABLE = False

class VoskWorker(QThread):
    """Worker thread for Vosk-based dictation"""
    textReceived = Signal(str)  # Keep for compatibility
    partialTextReceived = Signal(str)  # NEW: Gray text while speaking
    finalTextReceived = Signal(str)    # NEW: Black text when finished
    errorOccurred = Signal(str)
    statusChanged = Signal(str)

    def __init__(self, model_path):
        super().__init__()
        self.model_path = model_path
        self.running = False
        self._stop_event = threading.Event()  # Use event for cleaner termination
  
    def run(self):
        """Main processing loop for Vosk dictation"""
        if not VOSK_AVAILABLE:
            self.errorOccurred.emit("Vosk is not available. Please install the required dependencies.")
            return
    
        try:
            # Initialize Vosk
            model = Model(self.model_path)
            recognizer = KaldiRecognizer(model, 16000)
    
            # Audio setup
            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=4096
            )
    
            self.running = True
            self.statusChanged.emit("Vosk dictation started")
    
            # Main dictation loop
            while self.running and not self._stop_event.is_set():
                try:
                    data = stream.read(4096, exception_on_overflow=False)
                    if recognizer.AcceptWaveform(data):
                        # Final result - user finished speaking
                        result = json.loads(recognizer.Result())
                        text = result.get('text', '')
                        if text.strip():
                            self.finalTextReceived.emit(text + " ")  # NEW: Final result
                    else:
                        # Partial result - user is still speaking
                        partial_result = json.loads(recognizer.PartialResult())
                        partial_text = partial_result.get('partial', '')
                        if partial_text.strip():
                            self.partialTextReceived.emit(partial_text)  # NEW: Partial result
                except Exception as e:
                    if self.running:
                        self.errorOccurred.emit(f"Audio processing error: {str(e)}")
                    break
    
            # Cleanup
            self.running = False
            stream.stop_stream()
            stream.close()
            p.terminate()
            self.statusChanged.emit("Vosk dictation stopped")
    
        except Exception as e:
            self.running = False
            self.errorOccurred.emit(f"Error in Vosk dictation: {str(e)}")

    def stop(self):
        """Stop the dictation thread"""
        self.running = False
        self._stop_event.set()


class RealtimeSTTWorker(QThread):
    """Worker thread for RealtimeSTT-based dictation"""
    textReceived = Signal(str)
    errorOccurred = Signal(str)
    statusChanged = Signal(str)
    
    def __init__(self, model_path):
        super().__init__()
        self.model_path = model_path
        self.running = False
        self.recorder = None
        self._stop_event = threading.Event()  # Use event for cleaner termination
        self._text_callback_lock = threading.Lock()  # Lock for thread safety
        # Store config path for punctuation processing
        self._config_path = None

        # Set config path for accessing settings
        try:
            # Get config path from main application
            import os
            from pathlib import Path
            home_dir = Path.home()
            self._config_path = os.path.join(home_dir, ".assistivox", "config.json")
        except:
            self._config_path = None

    def process_faster_whisper_text(self, text):
        """Process faster-whisper text to handle punctuation substitution"""
        import re

        # Check if substitution commands are enabled
        try:
            # Load config to check if substitution commands are enabled
            if hasattr(self, '_config_path') and self._config_path:
                import json
                with open(self._config_path, 'r') as f:
                    config = json.load(f)
            
                substitution_enabled = config.get('dictation_settings', {}).get('enable_substitution_commands', False)
        
                if substitution_enabled:
                    # Check if text ends with sentence-final punctuation
                    sentence_final_pattern = r'[.!?]\s*$'
                    if re.search(sentence_final_pattern, text.strip()):
                        # Remove trailing period if it exists (faster-whisper adds periods automatically)
                        text = re.sub(r'\.\s*$', '', text.strip())
                        # Add back the original punctuation that was spoken
                        # (This logic assumes the spoken punctuation was correctly transcribed)
                
        except Exception as e:
            # If config reading fails, just return original text
            pass
            
        return text

    def run(self):
        """Main processing loop for RealtimeSTT dictation"""
        if not REALTIMESTT_AVAILABLE:
            self.errorOccurred.emit("RealtimeSTT is not available. Please install the required dependencies.")
            return
            
        try:
            self.running = True
            self._stop_event.clear()
            self.statusChanged.emit("RealtimeSTT dictation started")
            
            # Custom text callback to emit signals with thread safety
            def text_callback(text):
                with self._text_callback_lock:
                    if text and self.running:
                        # Process text for punctuation handling
                        processed_text = self.process_faster_whisper_text(text)
                        self.textReceived.emit(processed_text)

            # Create recorder with model and a fixed timeout
            # Determine device based on settings and availability
            try:
                import torch

                # Check if GPU is requested in settings
                use_gpu = False
                if hasattr(self, '_config_path') and self._config_path:
                    try:
                        import json
                        with open(self._config_path, 'r') as f:
                            config = json.load(f)
                        use_gpu = config.get("faster_whisper_settings", {}).get("use_gpu", False)
                    except:
                        pass

                # Final device selection
                if use_gpu and torch.cuda.is_available():
                    device = 'cuda'
                else:
                    device = 'cpu'

            except ImportError:
                device = 'cpu'
            print(f"Using device: {device} for RealtimeSTT")

            with AudioToTextRecorder(model=self.model_path, device=device) as recorder:
                self.recorder = recorder
                
                # We'll only process one recognition at a time
                while self.running and not self._stop_event.is_set():
                    try:
                        # Process one text recognition with a timeout
                        recorder.text(text_callback)
                        
                        # Check if we need to stop
                        if self._stop_event.is_set():
                            break
                            
                    except Exception as inner_e:
                        # Only report error if we're still running and didn't trigger the stop
                        if self.running and not self._stop_event.is_set():
                            error_msg = str(inner_e)
                            # Don't report "handle is closed" errors during shutdown
                            if "handle is closed" not in error_msg:
                                self.errorOccurred.emit(f"Error during recognition: {error_msg}")
                            break
                        else:
                            # This is expected when stopping
                            break
                
                # Clean up carefully
                self.recorder = None
        
        except Exception as e:
            error_msg = str(e)
            # Don't report "handle is closed" errors during shutdown
            if self.running and not self._stop_event.is_set() and "handle is closed" not in error_msg:
                self.errorOccurred.emit(f"Error in RealtimeSTT dictation: {error_msg}")
        
        finally:
            # Ensure we're marked as not running
            self.running = False
            self.statusChanged.emit("RealtimeSTT dictation stopped")
   
    def stop(self):
        """Stop the dictation thread with forceful cleanup"""
        if not self.running:
            return
        
        # Signal the thread to stop
        self._stop_event.set()
        self.running = False
    
        # RealtimeSTT uses multiprocessing and doesn't respond well to gentle shutdown
        # Force the recorder to close if it exists
        if hasattr(self, 'recorder') and self.recorder:
            try:
                # Try to force recorder to clean up its processes
                if hasattr(self.recorder, '_recording_process') and self.recorder._recording_process:
                    self.recorder._recording_process.terminate()
                if hasattr(self.recorder, '_recognition_process') and self.recorder._recognition_process:
                    self.recorder._recognition_process.terminate()
                # Close the recorder explicitly
                self.recorder.__exit__(None, None, None)
            except Exception as e:
                print(f"Error during forced recorder cleanup: {e}")


class DictationEngine(QObject):
    """
    Specialized dictation engine for GUI integration
    
    This class manages dictation in a separate thread to avoid
    blocking the GUI, and provides signals for text output.
    """
    
    # Signals
    textReceived = Signal(str)  # Emitted when transcribed text is received
    statusChanged = Signal(bool, str)  # Emitted when dictation status changes
    # ADD these missing signals:
    partialTextReceived = Signal(str)
    finalTextReceived = Signal(str)
    
    def __init__(self, assistivox_dir, config_path):
        super().__init__()
        self.assistivox_dir = assistivox_dir
        self.config_path = config_path
        self.is_running = False
        self.worker = None
        self._stop_lock = threading.Lock()  # Add lock for thread safety during stopping
        
        # Load configuration
        self.config = self._load_config()
    
    def _load_config(self):
        """Load the configuration file"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def get_selected_model(self):
        """
        Get the currently selected STT model
        
        Returns:
            tuple: (model_type, model_size) or (None, None) if no model selected
        """
        # First check the dictation engine
        engine = self.get_dictation_engine()
        if not engine:
            return None, None
        
        if engine == "vosk":
            # For Vosk, check vosk_settings section
            if "vosk_settings" in self.config and "model" in self.config["vosk_settings"]:
                model_size = self.config["vosk_settings"]["model"]
                return "vosk", model_size
            return None, None
        
        elif engine == "faster-whisper":
            # For faster-whisper, check faster_whisper_settings section
            if "faster_whisper_settings" in self.config and "model" in self.config["faster_whisper_settings"]:
                model_size = self.config["faster_whisper_settings"]["model"]
                return "faster-whisper", model_size
            return None, None
        
        # If we get here, the engine is set but no model is configured
        return None, None

    def is_model_selected(self):
        """Check if an STT model is currently selected"""
        model_type, model_size = self.get_selected_model()
        return model_type is not None and model_size is not None
   
    def get_model_path(self, model_type, model_size):
        """Get the full path to the model directory based on type and size"""
        try:
            # Load MODEL_MAP from stt.json (same as stt_models.py does)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            stt_json_path = os.path.join(project_root, "stt.json")
            
            with open(stt_json_path, 'r') as f:
                stt_data = json.load(f)
            
            # Get model_id from stt.json
            model_id = stt_data[model_type][model_size]["model_id"]
        except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
            print(f"DEBUG: Failed to get model_id from stt.json: {e}")
            return None
    
        # Construct model path
        model_dir = os.path.join(
            self.assistivox_dir,
            "stt-models", 
            model_type,
            model_id
        )
        
        print(f"DEBUG: Looking for model at: {model_dir}")
        print(f"DEBUG: Model exists: {os.path.exists(model_dir)}")
    
        # For faster-whisper, we need to go one level deeper
        if model_type == "faster-whisper" and os.path.exists(model_dir):
            for item in os.listdir(model_dir):
                item_path = os.path.join(model_dir, item)
                if os.path.isdir(item_path) and item.startswith("faster-whisper-"):
                    return item_path
    
        return model_dir if os.path.exists(model_dir) else None

    def get_dictation_engine(self):
        """
        Get the currently selected dictation engine
    
        Returns:
            str: 'vosk' or 'faster-whisper' or None if not set
        """
        if "dictation_settings" not in self.config:
            return None
        
        return self.config["dictation_settings"].get("engine", None)

    def start_dictation(self):
        """Start dictation in a separate thread"""
        if self.is_running:
            return True
    
        # Check which engine is selected
        engine = self.get_dictation_engine()
        if not engine:
            self.statusChanged.emit(False, "No dictation engine selected")
            return False
    
        if engine == "vosk":
            # For Vosk, get the selected model
            model_type, model_size = self.get_selected_model()
            if not model_type or model_type != "vosk":
                self.statusChanged.emit(False, "No Vosk model selected")
                return False
        
            model_path = self.get_model_path(model_type, model_size)
            if not model_path:
                self.statusChanged.emit(False, f"Vosk model {model_type}_{model_size} not found")
                return False
        
            self.worker = VoskWorker(model_path)
    
        elif engine == "faster-whisper":
            # For faster-whisper, get the selected model
            model_type, model_size = self.get_selected_model()
            if not model_type or model_type != "faster-whisper":
                self.statusChanged.emit(False, "No faster-whisper model selected")
                return False
        
            model_path = self.get_model_path(model_type, model_size)
            if not model_path:
                self.statusChanged.emit(False, f"Faster-whisper model {model_type}_{model_size} not found")
                return False
    
            self.worker = RealtimeSTTWorker(model_path)
            self.worker._config_path = self.config_path
    
        else:
            self.statusChanged.emit(False, f"Unsupported dictation engine: {engine}")
            return False
    
        # Connect worker signals
        self.connect_worker_signals()
    
        # Start worker thread
        self.worker.start()
        self.is_running = True
        self.statusChanged.emit(True, f"Dictation started with {engine}")
        return True
    
    def stop_dictation(self):
        """Stop the dictation thread with thread safety"""
        # Use a lock to ensure we don't have race conditions during stopping
        with self._stop_lock:
            if not self.is_running:
                return
        
            if self.worker:
                # First signal the worker to stop gracefully
                self.worker.stop()
            
                # Wait a limited time for the thread to finish naturally
                if not self.worker.wait(1000):  # Wait up to 1 second
                    # This is still happening, so we need to be more aggressive
                    print("Forcing dictation thread termination")
                    self.worker.terminate()
                    self.worker.wait(1000)  # Give it a second to clean up
            
                self.worker = None
        
            self.is_running = False
            self.statusChanged.emit(False, "Dictation stopped")
    
    def on_text_received(self, text):
        """Forward text from worker thread to registered listeners"""
        self.textReceived.emit(text)
    
    def on_error(self, error_msg):
        """Handle errors from worker thread"""
        print(f"Dictation error: {error_msg}")
        # Only notify UI if the error isn't about a closed handle during shutdown
        if "handle is closed" not in error_msg:
            self.statusChanged.emit(False, f"Error: {error_msg}")
        
        # Stop dictation system - this error is unrecoverable
        self.stop_dictation()
    
    def on_status_changed(self, status_msg):
        """Handle status changes from worker thread"""
        print(f"Dictation status: {status_msg}")
    
    def on_worker_finished(self):
        """Handle worker thread finishing"""
        # If we're still marked as running but the thread finished, update state
        if self.is_running:
            self.is_running = False
            self.statusChanged.emit(False, "Dictation stopped unexpectedly")

    def connect_worker_signals(self):
        """Connect worker signals - called after worker is created"""
        if self.worker:
            # Connect existing signals
            self.worker.textReceived.connect(self.on_text_received)
            self.worker.errorOccurred.connect(self.on_error)
            self.worker.statusChanged.connect(self.on_status_changed)
            self.worker.finished.connect(self.on_worker_finished)
        
            # Connect new signals if they exist (for VoskWorker)
            if hasattr(self.worker, 'partialTextReceived'):
                self.worker.partialTextReceived.connect(self.on_partial_text_received)
            if hasattr(self.worker, 'finalTextReceived'):
                self.worker.finalTextReceived.connect(self.on_final_text_received)

    def on_partial_text_received(self, text):
        """Handle partial text - emit to UI components"""
        self.partialTextReceived.emit(text)

    def on_final_text_received(self, text):
        """Handle final text - emit to UI components"""
        self.finalTextReceived.emit(text)
