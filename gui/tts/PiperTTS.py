# gui/tts/PiperTTS.py
import subprocess
import tempfile
import soundfile as sf
import sounddevice as sd
import os
import numpy as np
import threading
from typing import Callable, Optional
from pathlib import Path

class PiperTTS:
    def __init__(self, piper_binary, model_path, config_path):
        self.piper_binary = piper_binary
        self.model_path = model_path
        self.config_path = config_path
        self._stop_requested = False
        self._playback_lock = threading.Lock()
        self._current_playback_thread = None
        # Add a lock for the audio device to ensure proper release
        self._audio_device_lock = threading.Lock()
        
        # Set up ESPEAK_DATA_PATH if needed
        self._setup_espeak_path()
    
    def _setup_espeak_path(self):
        """Set up ESPEAK_DATA_PATH environment variable if needed"""
        # Check if ESPEAK_DATA_PATH is already set
        if os.environ.get("ESPEAK_DATA_PATH"):
            return
        
        # Get the piper directory from the binary path
        piper_dir = Path(self.piper_binary).parent.parent
        
        # Look for espeak-ng-data in common locations
        possible_paths = [
            piper_dir / "espeak-ng-data",
            piper_dir / "build" / "piper" / "share" / "espeak-ng-data",
            piper_dir / "build" / "share" / "espeak-ng-data",
            piper_dir / "share" / "espeak-ng-data",
        ]
        
        for path in possible_paths:
            if path.exists() and (path / "phontab").exists():
                os.environ["ESPEAK_DATA_PATH"] = str(path)
                print(f"Set ESPEAK_DATA_PATH to: {path}")
                return
        
        # If not found, print warning
        print("Warning: Could not find espeak-ng-data directory. Piper may fail to run.")

    def _speed_adjust_audio(self, input_wav: str, speed: float) -> str:
        """Run audiostretchy on input_wav with speed, return path to adjusted wav."""
        if speed == 1.0:
            return input_wav  # No adjustment needed

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp2:
            adjusted_wav = tmp2.name

        ratio = 1.0 / speed  # audiostretchy expects <1 to speed up

        try:
            from audiostretchy.stretch import stretch_audio
            stretch_audio(input_wav, adjusted_wav, ratio=ratio)
        except Exception as e:
            if os.path.exists(adjusted_wav):
                os.remove(adjusted_wav)
            raise RuntimeError(f"audiostretchy failed: {str(e)}")

        return adjusted_wav

    def request_stop(self):
        """Request that any ongoing TTS playback be stopped."""
        self._stop_requested = True
        
    def is_speaking(self):
        """Check if TTS is currently playing audio."""
        return self._current_playback_thread is not None and self._current_playback_thread.is_alive()

