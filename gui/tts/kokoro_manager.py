# gui/tts/kokoro_manager.py
import subprocess
import sys
import time
import requests
import tempfile
import os
import threading
import json
from pathlib import Path
import shutil

import struct
import numpy as np
import sounddevice as sd
import soundfile as sf
from PySide6.QtCore import QObject, Signal


class KokoroDockerManager:
    """Manages the Kokoro Docker container lifecycle"""
    
    def __init__(self, port=8880):
        self.port = port
        self.container_name = "kokoro_tts_assistivox"
        self.api_url = f"http://localhost:{self.port}/v1/audio/speech"
        self.voices_url = f"http://localhost:{self.port}/v1/audio/voices"
        self._container_started = False
        
    def check_docker_installed(self):
        """Check if Docker is installed and accessible"""
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def is_container_running(self):
        """Check if the Kokoro container is already running"""
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={self.container_name}"],
                capture_output=True,
                text=True
            )
            return bool(result.stdout.strip())
        except subprocess.SubprocessError:
            return False
    
    def start_container(self, use_gpu=False):
        """Start the Kokoro Docker container"""
        if not self.check_docker_installed():
            raise RuntimeError("Docker is not installed. Please install Docker to use Kokoro TTS.")
        
        if self.is_container_running():
            print(f"Kokoro container '{self.container_name}' is already running.")
            self._container_started = True
            return True
            
        print(f"Starting Kokoro TTS Docker container on port {self.port}...")
        
        try:
            # Stop any existing container with the same name
            subprocess.run(
                ["docker", "stop", self.container_name],
                capture_output=True,
                timeout=10
            )
            subprocess.run(
                ["docker", "rm", self.container_name],
                capture_output=True,
                timeout=5
            )
        except subprocess.SubprocessError:
            pass  # Container might not exist
        
        # Start new container with appropriate image
        if use_gpu:
            image = "ghcr.io/remsky/kokoro-fastapi-gpu:latest"
            docker_cmd = [
                "docker", "run", "--rm", "-d", "--gpus", "all",
                "-p", f"{self.port}:{self.port}",
                "--name", self.container_name,
                image
            ]
        else:
            image = "ghcr.io/remsky/kokoro-fastapi-cpu:latest"
            docker_cmd = [
                "docker", "run", "--rm", "-d",
                "-p", f"{self.port}:{self.port}",
                "--name", self.container_name,
                image
            ]
        
        try:
            subprocess.run(docker_cmd, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to start Kokoro Docker container: {str(e)}")
        
        # Wait for container to be ready
        for i in range(30):
            try:
                r = requests.get(f"http://localhost:{self.port}/docs", timeout=1)
                if r.status_code == 200:
                    print("Kokoro TTS container is ready.")
                    self._container_started = True
                    return True
            except Exception:
                pass
            time.sleep(1)
        
        raise RuntimeError("Kokoro TTS container did not start in time.")

    def stop_container(self):
        """Stop the Kokoro Docker container"""
        if not self._container_started:
            return
            
        print(f"Stopping Kokoro TTS container '{self.container_name}'...")
        try:
            subprocess.run(
                ["docker", "stop", self.container_name],
                capture_output=True,
                timeout=15
            )
            self._container_started = False
            print("Kokoro TTS container stopped.")
        except subprocess.SubprocessError as e:
            print(f"Error stopping Kokoro container: {e}")
    
    def get_voices(self):
        """Get available voices from the Kokoro API"""
        try:
            r = requests.get(self.voices_url, timeout=5)
            if r.status_code == 200:
                return r.json().get("voices", [])
        except Exception as e:
            print(f"Error fetching voices from Kokoro API: {e}")
        
        # Return default list if API fails
        return []
    
    def synthesize_speech(self, text, voice, output_path=None):
        """Synthesize speech using Kokoro API"""
        payload = {
            "model": "kokoro",
            "voice": voice,
            "input": text,
            "response_format": "wav"
        }
        
        try:
            resp = requests.post(self.api_url, json=payload, stream=True, timeout=30)
            if resp.status_code == 200:
                # Save to file
                if output_path is None:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                        output_path = f.name
                
                with open(output_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                return output_path
            else:
                raise RuntimeError(f"Kokoro API error: {resp.status_code} {resp.text}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error calling Kokoro API: {str(e)}")


class KokoroTTS:
    """Kokoro TTS implementation compatible with PiperTTS interface"""

    def __init__(self, docker_manager, voice_name):
        self.docker_manager = docker_manager
        self.voice_name = voice_name
        self._stop_requested = False
        self._playback_lock = threading.Lock()
        self._current_playback_thread = None
        self._audio_device_lock = threading.Lock()

    def request_stop(self):
        """Request that any ongoing TTS playback be stopped."""
        self._stop_requested = True

    def is_speaking(self):
        """Check if TTS is currently playing audio."""
        return self._current_playback_thread is not None and self._current_playback_thread.is_alive()

    def _fix_wav_header(self, filename):
        with open(filename, "r+b") as f:
            f.seek(0)
            riff = f.read(12)
            if riff[0:4] != b'RIFF' or riff[8:12] != b'WAVE':
                raise ValueError("Not a valid WAV file")

            # Scan for the 'data' chunk
            while True:
                chunk_header = f.read(8)
                if len(chunk_header) < 8:
                    raise ValueError("No data chunk found")
                chunk_id, chunk_size = struct.unpack('<4sI', chunk_header)
                if chunk_id == b'data':
                    data_chunk_pos = f.tell() - 8
                    break
                # Skip this chunk's data
                f.seek(chunk_size, 1)

            # Calculate sizes
            file_size = f.seek(0, 2)
            data_size = file_size - (data_chunk_pos + 8)

            # Patch RIFF chunk size
            f.seek(4)
            f.write(struct.pack('<I', file_size - 8))
            # Patch data chunk size
            f.seek(data_chunk_pos + 4)
            f.write(struct.pack('<I', data_size))

    def _speed_adjust_audio(self, input_wav: str, speed: float) -> str:
        """Run audiostretchy on input_wav with speed, return path to adjusted wav."""
        print(f"DEBUG: _speed_adjust_audio called with speed={speed}")
    
        if speed == 1.0:
            print("DEBUG: Speed is 1.0, no adjustment needed")
            return input_wav
    
        # Read the audio data and write to a clean WAV file for audiostretchy
        try:
            data, samplerate = sf.read(input_wav, dtype='float32')
    
            # Create a clean WAV file with proper headers
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as clean_tmp:
                clean_wav = clean_tmp.name
    
            sf.write(clean_wav, data, samplerate)
            print(f"DEBUG: Created clean WAV file: {clean_wav}")
    
        except Exception as e:
            print(f"DEBUG: Failed to create clean WAV: {e}")
            # Fall back to original file
            clean_wav = input_wav
    
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp2:
            adjusted_wav = tmp2.name
    
        ratio = 1.0 / speed  # audiostretchy expects <1 to speed up
        print(f"DEBUG: Calculated ratio: {ratio}")
    
        try:
            from audiostretchy.stretch import stretch_audio
            print(f"DEBUG: Calling audiostretchy.stretch_audio with ratio: {ratio}")
            stretch_audio(clean_wav, adjusted_wav, ratio=ratio)
            print(f"DEBUG: audiostretchy succeeded, output file: {adjusted_wav}")
        except Exception as e:
            print(f"DEBUG: audiostretchy failed with error: {str(e)}")
            # Clean up the temporary clean WAV file if we created one
            if clean_wav != input_wav and os.path.exists(clean_wav):
                os.remove(clean_wav)
            if os.path.exists(adjusted_wav):
                os.remove(adjusted_wav)
            raise RuntimeError(f"audiostretchy failed: {str(e)}")
    
        # Clean up the temporary clean WAV file if we created one
        if clean_wav != input_wav and os.path.exists(clean_wav):
            os.remove(clean_wav)
    
        return adjusted_wav
    
    def _speak_via_stdin_internal(self, text: str, silence_ms: int = 0, speed: float = 1.0,
                                 on_finished=None, on_error=None):
        """Internal implementation of speak that matches PiperTTS interface"""
        output_path = None
        adjusted_path = None
        trimmed_path = None
        playback_path = None
        success = False

        try:
            # Debug logging
            print(f"DEBUG: _speak_via_stdin_internal called with speed={speed}, type={type(speed)}")

            # Validate speed parameter
            if speed is None or speed <= 0:
                print(f"DEBUG: Invalid speed {speed}, defaulting to 1.0")
                speed = 1.0

            # Synthesize speech via API
            print("About to send speech to docker")
            output_path = self.docker_manager.synthesize_speech(text, self.voice_name)
            print("Return from docker")
            self._fix_wav_header(output_path)
            print("Fixed WAV header")

            # Get original duration
            original_data, original_samplerate = sf.read(output_path, dtype='float32')
            original_duration = len(original_data) / original_samplerate

            # Apply speed adjustment if needed
            adjusted_path = output_path
            if speed != 1.0:
                adjusted_path = self._speed_adjust_audio(output_path, speed)
                print("Adjusted speed")

                # Calculate expected duration after speed adjustment
                expected_duration = original_duration / speed

                # Read adjusted file
                adjusted_data, adjusted_samplerate = sf.read(adjusted_path, dtype='float32')

                # Create a new file with trimmed audio
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    trimmed_path = tmp.name

                # Calculate how many samples to keep (based on expected duration)
                samples_to_keep = int(expected_duration * adjusted_samplerate)

                # Ensure we don't exceed the actual data length
                samples_to_keep = min(samples_to_keep, len(adjusted_data))

                # Write trimmed data to file
                sf.write(trimmed_path, adjusted_data[:samples_to_keep], adjusted_samplerate)

                # Use the trimmed file for playback
                playback_path = trimmed_path
            else:
                # No speed adjustment, use original file
                playback_path = output_path

            # Read audio data
            data, samplerate = sf.read(playback_path, dtype='float32')
            print("Read in audio")

            # Add silence if requested
            if silence_ms > 0:
                silence_samples = int((silence_ms / 1000.0) * samplerate)
                if len(data.shape) == 1:  # Mono
                    silence = np.zeros(silence_samples, dtype='float32')
                else:  # Stereo
                    silence = np.zeros((silence_samples, data.shape[1]), dtype='float32')
                data = np.concatenate([silence, data])

            # Calculate playback duration
            playback_duration = len(data) / samplerate

            # Use the audio device lock to ensure exclusive access
            with self._audio_device_lock:
                # Play audio
                sd.play(data, samplerate)

                # Wait for playback to complete with stop check
                start_time = time.time()
                end_time = start_time + playback_duration + 0.05  # Small buffer

                while time.time() < end_time and not self._stop_requested:
                    print("Sleep", time.time())
                    time.sleep(0.01)  # Short sleep for responsiveness

                # Stop any ongoing playback
                sd.stop()

                # Mark as successful if not stopped
                success = not self._stop_requested

        except Exception as e:
            if on_error:
                on_error(str(e))
            success = False

        finally:
            # Clean up temp files
            if output_path and adjusted_path and adjusted_path != output_path:
                if os.path.exists(adjusted_path):
                    try:
                        os.remove(adjusted_path)
                    except:
                        pass

            # Clean up original output file
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except:
                    pass

            # Mark thread as finished
            with self._playback_lock:
                self._current_playback_thread = None

            # Call completion callback if provided
            if success and on_finished:
                on_finished()

            return success

    def speak_via_stdin(self, sents, silence_ms: int = 0, speed: float = 1.0,
                        on_finished=None, on_error=None, blocking: bool = True):
        """Speak a list of sentences"""
        # Reset stop flag
        self._stop_requested = False

        if not blocking:
            # Run in background thread
            thread = threading.Thread(
                target=self._speak_sentences,
                args=(sents, silence_ms, speed, on_finished, on_error)
            )
            thread.daemon = True
            with self._playback_lock:
                self._current_playback_thread = thread
            thread.start()
            return None
        else:
            # Run synchronously
            return self._speak_sentences(sents, silence_ms, speed, on_finished, on_error)

    def _speak_sentences(self, sents, silence_ms: int = 0, speed: float = 1.0,
                        on_finished=None, on_error=None):
        """Process a list of sentences, speaking each one."""
        success = True

        for i, text in enumerate(sents):
            # For all sentences except the last one, don't call on_finished
            if i < len(sents) - 1:
                result = self._speak_via_stdin_internal(text, silence_ms, speed, None, on_error)
            else:
                # Only call on_finished when the last sentence is complete
                result = self._speak_via_stdin_internal(text, silence_ms, speed, on_finished, on_error)

            # If any sentence fails or stop is requested, break the loop
            if not result or self._stop_requested:
                success = False
                break

        return success

# Global instance for managing Docker container
_kokoro_docker_manager = None

def get_kokoro_docker_manager(port=8880):
    """Get or create the global Kokoro Docker manager"""
    global _kokoro_docker_manager
    if _kokoro_docker_manager is None:
        _kokoro_docker_manager = KokoroDockerManager(port)
    return _kokoro_docker_manager

def cleanup_kokoro_docker():
    """Clean up the global Kokoro Docker manager"""
    global _kokoro_docker_manager
    if _kokoro_docker_manager:
        _kokoro_docker_manager.stop_container()
        _kokoro_docker_manager = None

