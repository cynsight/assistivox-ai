# gui/tts/tts_manager.py
import os
import json
import threading
from PySide6.QtCore import QObject, Signal, QThread
from PySide6.QtWidgets import QMessageBox
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor
import time
import subprocess

class TTSWorker(QThread):
    """Worker thread for Text-to-Speech with read-ahead buffering to avoid blocking the UI"""
    finished = Signal()  # Signal emitted when speech is complete
    error = Signal(str)  # Signal emitted if an error occurs
    sentence_started = Signal(int, int)  # Signal emitted when a new sentence starts (block_index, sentence_index)

    def __init__(self, tts, sentence_data, silence_ms=0, speed=1.0, start_block=0, start_sentence=0):
        super().__init__()
        self.tts = tts
        self.sentence_data = sentence_data  # List of blocks with sentences and offsets
        self.silence_ms = silence_ms
        self.speed = speed
        self.start_block = start_block
        self.start_sentence = start_sentence
        self._stop_flag = False
        
        # Read-ahead buffer management
        self._audio_buffer = {}  # Dict mapping (block_idx, sent_idx) to audio file path
        self._buffer_lock = threading.Lock()
        self._readahead_thread = None
        self._readahead_stop_flag = False
        self._current_playback_position = (start_block, start_sentence)

    def stop(self):
        """Stop both the TTS engine and this thread"""
        # Signal the TTS engine to stop
        self.tts.request_stop()
        # Set our stop flags
        self._stop_flag = True
        self._readahead_stop_flag = True
        
        # Wait for read-ahead thread to finish
        if self._readahead_thread and self._readahead_thread.is_alive():
            self._readahead_thread.join(timeout=1.0)

    def run(self):
        """Run TTS in the thread starting from specified position with read-ahead buffering"""
        print(f"DEBUG: TTSWorker.run() starting from block {self.start_block}, sentence {self.start_sentence}")
        
        try:
            # Start the read-ahead thread
            self._start_readahead_thread()
            
            # Process each block starting from start_block
            for block_index in range(self.start_block, len(self.sentence_data)):
                # Check stop condition at the beginning of each block
                if self._stop_flag or self.tts._stop_requested:
                    print("DEBUG: Stop requested, breaking from block loop")
                    break
                    
                block_data = self.sentence_data[block_index]
                sentences = block_data['sentences']
                
                print(f"DEBUG: Processing block {block_index} with {len(sentences)} sentences")
                
                if not sentences:  # Skip empty blocks
                    print(f"DEBUG: Block {block_index} is empty, skipping")
                    continue
                
                # Determine starting sentence index
                start_sent_idx = self.start_sentence if block_index == self.start_block else 0
                print(f"DEBUG: Starting from sentence {start_sent_idx} in block {block_index}")
                
                # Process each sentence in the block starting from start_sent_idx
                for sentence_index in range(start_sent_idx, len(sentences)):
                    # Check our stop flag before processing each sentence
                    if self._stop_flag or self.tts._stop_requested:
                        print("DEBUG: Stop requested, exiting from sentence loop")
                        return  # Exit immediately when stopped
                        
                    sentence = sentences[sentence_index]
                    print(f"DEBUG: Speaking sentence {block_index}-{sentence_index}: '{sentence[:50]}...'")
                    
                    # Update current position for read-ahead thread
                    self._current_playback_position = (block_index, sentence_index)
                    
                    # Emit which sentence we're starting (block_index, sentence_index)
                    self.sentence_started.emit(block_index, sentence_index)
                    
                    # Get audio for current sentence (from buffer or generate)
                    audio_path = self._get_audio_for_sentence(block_index, sentence_index, sentence)
                    
                    if not audio_path:
                        print(f"DEBUG: Failed to get audio for sentence {block_index}-{sentence_index}")
                        return
                    
                    # Play the audio
                    result = self._play_audio_file(audio_path)
                    
                    print(f"DEBUG: Sentence {block_index}-{sentence_index} result: {result}")
                    
                    # Check stop condition immediately after each sentence
                    if not result or self.tts._stop_requested or self._stop_flag:
                        print("DEBUG: Sentence failed or stop requested, exiting")
                        return  # Exit immediately when stopped
                
                # Reset start_sentence for the next block
                self.start_sentence = 0
                
                # Check stop condition after each block
                if self._stop_flag or self.tts._stop_requested:
                    print("DEBUG: Stop requested after block, exiting")
                    return  # Exit immediately when stopped
            
            # Only emit finished if we weren't stopped and completed all sentences
            if not self._stop_flag and not self.tts._stop_requested:
                print("DEBUG: All sentences completed, emitting finished signal")
                self.finished.emit()
            else:
                print("DEBUG: Worker stopped before completion")
            
        except Exception as e:
            print(f"DEBUG: Error in TTS thread: {str(e)}")
            self.error.emit(str(e))
        finally:
            # Clean up read-ahead thread
            self._readahead_stop_flag = True
            if self._readahead_thread and self._readahead_thread.is_alive():
                self._readahead_thread.join(timeout=1.0)
            
            # Clean up any remaining audio files in buffer
            self._cleanup_audio_buffer()

    def _start_readahead_thread(self):
        """Start the read-ahead thread"""
        self._readahead_stop_flag = False
        self._readahead_thread = threading.Thread(target=self._readahead_worker, daemon=True)
        self._readahead_thread.start()

    def _readahead_worker(self):
        """Read-ahead thread that maintains a buffer of 2 sentences"""
        print("DEBUG: Read-ahead thread started")
        
        while not self._readahead_stop_flag:
            try:
                # Get current playback position
                current_block, current_sent = self._current_playback_position
                
                # Find next 5 sentences to buffer
                sentences_to_buffer = self._get_next_sentences(current_block, current_sent, 5)
                
                for block_idx, sent_idx in sentences_to_buffer:
                    # Check if we should stop
                    if self._readahead_stop_flag:
                        break
                    
                    # Skip if already in buffer
                    with self._buffer_lock:
                        if (block_idx, sent_idx) in self._audio_buffer:
                            continue
                    
                    # Generate audio for this sentence
                    if block_idx < len(self.sentence_data):
                        block_data = self.sentence_data[block_idx]
                        if sent_idx < len(block_data['sentences']):
                            sentence = block_data['sentences'][sent_idx]
                            audio_path = self._generate_audio_for_sentence(sentence)
                            
                            if audio_path:
                                with self._buffer_lock:
                                    self._audio_buffer[(block_idx, sent_idx)] = audio_path
                                print(f"DEBUG: Buffered audio for sentence {block_idx}-{sent_idx}")
                
                # Sleep briefly before checking again
                time.sleep(0.1)
                
            except Exception as e:
                print(f"DEBUG: Error in read-ahead thread: {str(e)}")
                
        print("DEBUG: Read-ahead thread finished")

    def _get_next_sentences(self, current_block, current_sent, count):
        """Get the next 'count' sentences starting from current position"""
        sentences = []
        block_idx = current_block
        sent_idx = current_sent + 1  # Start from next sentence
        
        while len(sentences) < count and block_idx < len(self.sentence_data):
            block_data = self.sentence_data[block_idx]
            block_sentences = block_data['sentences']
            
            # Add sentences from current block
            while sent_idx < len(block_sentences) and len(sentences) < count:
                sentences.append((block_idx, sent_idx))
                sent_idx += 1
            
            # Move to next block
            if sent_idx >= len(block_sentences):
                block_idx += 1
                sent_idx = 0
        
        return sentences

    def _get_audio_for_sentence(self, block_idx, sent_idx, sentence):
        """Get audio path for sentence, either from buffer or generate immediately"""
        # First check if it's in the buffer
        with self._buffer_lock:
            if (block_idx, sent_idx) in self._audio_buffer:
                audio_path = self._audio_buffer.pop((block_idx, sent_idx))
                print(f"DEBUG: Retrieved sentence {block_idx}-{sent_idx} from buffer")
                return audio_path
        
        # Not in buffer, generate immediately
        print(f"DEBUG: Generating audio immediately for sentence {block_idx}-{sent_idx}")
        return self._generate_audio_for_sentence(sentence)

    def _check_if_sentence_in_buffer(self, block_idx, sent_idx):
        """Check if a sentence is already in the buffer"""
        with self._buffer_lock:
            return (block_idx, sent_idx) in self._audio_buffer

    def _generate_audio_for_sentence(self, sentence):
        """Generate audio file for a single sentence with proper silence trimming"""
        output_path = None
        adjusted_path = None
        trimmed_path = None
    
        try:
            # Check if this is a Kokoro TTS object (doesn't have piper_binary)
            if hasattr(self.tts, 'docker_manager'):
                # This is a KokoroTTS object - use its synthesize_speech method
                output_path = self.tts.docker_manager.synthesize_speech(sentence, self.tts.voice_name)
                # Fix WAV header for Kokoro files
                self.tts._fix_wav_header(output_path)
                adjusted_path = output_path
            else:
                # This is a PiperTTS object - use Piper command
                import tempfile
    
                # Create temp file for original output
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    output_path = tmp.name
    
                # Generate audio with Piper
                cmd = [
                    self.tts.piper_binary,
                    "--model", self.tts.model_path,
                    "--config", self.tts.config_path,
                    "--output_file", output_path
                ]
    
                # Run Piper
                result = subprocess.run(
                    cmd,
                    input=sentence,
                    capture_output=True,
                    text=True,
                    timeout=20
                )
    
                if result.returncode != 0:
                    print(f"DEBUG: Piper failed for sentence: {result.stderr}")
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    return None
    
                adjusted_path = output_path
    
            # Get original duration for trimming calculation
            import soundfile as sf
            original_data, original_samplerate = sf.read(output_path, dtype='float32')
            original_duration = len(original_data) / original_samplerate
    
            # Adjust speed if needed
            if self.speed != 1.0:
                adjusted_path = self.tts._speed_adjust_audio(output_path, self.speed)
    
                # Calculate expected duration after speed adjustment
                expected_duration = original_duration / self.speed
    
                # Read adjusted file
                adjusted_data, adjusted_samplerate = sf.read(adjusted_path, dtype='float32')
    
                # Create a new file with trimmed audio to remove audiostretchy silence padding
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    trimmed_path = tmp.name
    
                # Calculate how many samples to keep (based on expected duration)
                samples_to_keep = int(expected_duration * adjusted_samplerate)
    
                # Ensure we don't exceed the actual data length
                samples_to_keep = min(samples_to_keep, len(adjusted_data))
    
                # Write trimmed data to file
                sf.write(trimmed_path, adjusted_data[:samples_to_keep], adjusted_samplerate)
    
                # Clean up intermediate files
                if adjusted_path != output_path and os.path.exists(adjusted_path):
                    os.remove(adjusted_path)
                if os.path.exists(output_path):
                    os.remove(output_path)
    
                return trimmed_path
            else:
                return output_path
    
        except Exception as e:
            print(f"DEBUG: Error generating audio: {str(e)}")
            # Clean up any created files on error
            for path in [output_path, adjusted_path, trimmed_path]:
                if path and os.path.exists(path):
                    os.remove(path)
            return None

    def _play_audio_file(self, audio_path):
        """Play an audio file and clean it up"""
        try:
            import soundfile as sf
            import sounddevice as sd
            
            # Read and play audio
            data, samplerate = sf.read(audio_path, dtype='float32')
            
            # Use the TTS audio device lock for thread safety
            with self.tts._audio_device_lock:
                if self._stop_flag or self.tts._stop_requested:
                    return False
                
                sd.play(data, samplerate)
                
                # Wait for playback to complete, checking stop condition
                import time
                while sd.get_stream().active and not self._stop_flag and not self.tts._stop_requested:
                    time.sleep(0.01)  # Check every 10ms
                
                # Stop playback if requested
                if self._stop_flag or self.tts._stop_requested:
                    sd.stop()
                    return False
                
            return True
            
        except Exception as e:
            print(f"DEBUG: Error playing audio: {str(e)}")
            return False
        finally:
            # Clean up audio file
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except Exception:
                    pass

    def _cleanup_audio_buffer(self):
        """Clean up all audio files in the buffer"""
        with self._buffer_lock:
            for audio_path in self._audio_buffer.values():
                if os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                    except Exception:
                        pass
            self._audio_buffer.clear()


class TTSManager(QObject):
    """
    Text-to-speech manager for handling speech synthesis in the application
    
    This class encapsulates all TTS-related functionality that was previously
    in the TextEditorWidget class.
    """
    
    # Signals
    sentenceIndexChanged = Signal(int, int)  # Emitted when sentence index changes (block, sentence)
    
    def __init__(self, text_edit, config=None, assistivox_dir=None):
        super().__init__()
        self.text_edit = text_edit
        self.config = config
        self.assistivox_dir = assistivox_dir
        self.is_speaking = False
        self.tts_worker = None
        self.sentence_data = None  # Store sentence detection results
        self.current_highlight_cursor = None  # Store cursor for current highlight
        self._is_navigating = False  # Flag to track navigation state
        
        # TTS sentence index (block_index, sentence_index)
        self.tts_sentence_index = (0, 0)
    
    def reset_sentence_index(self):
        """Reset TTS sentence index to (0, 0)"""
        self.tts_sentence_index = (0, 0)
        self.sentenceIndexChanged.emit(0, 0)
    
    def get_sentence_index(self):
        """Get current TTS sentence index"""
        return self.tts_sentence_index
    
    def set_sentence_index(self, block_index, sentence_index):
        """Set TTS sentence index"""
        self.tts_sentence_index = (block_index, sentence_index)
        self.sentenceIndexChanged.emit(block_index, sentence_index)
    
    def navigate_to_next_sentence(self):
        """Navigate to next sentence and start speaking it"""
        print(f"DEBUG: TTSManager.navigate_to_next_sentence() called")
        print(f"DEBUG: sentence_data exists: {self.sentence_data is not None}")
        print(f"DEBUG: is_speaking: {self.is_speaking}")
        
        if not self.sentence_data or not self.is_speaking:
            print("DEBUG: Early return - no sentence data or not speaking")
            return False
            
        block_idx, sent_idx = self.tts_sentence_index
        print(f"DEBUG: Current position: block {block_idx}, sentence {sent_idx}")
        
        # Find next sentence
        while block_idx < len(self.sentence_data):
            block_data = self.sentence_data[block_idx]
            sentences = block_data['sentences']
            
            if not sentences:  # Empty block, move to next
                block_idx += 1
                sent_idx = 0
                continue
                
            if sent_idx + 1 < len(sentences):
                # Next sentence in same block
                sent_idx += 1
                break
            else:
                # Move to next block
                block_idx += 1
                sent_idx = 0
                if block_idx < len(self.sentence_data):
                    # Check if next block has sentences
                    next_block = self.sentence_data[block_idx]
                    if next_block['sentences']:
                        break
        
        # Check if we found a valid next sentence
        if (block_idx >= len(self.sentence_data) or 
            not self.sentence_data[block_idx]['sentences']):
            print("DEBUG: No next sentence found")
            return False  # No next sentence
        
        print(f"DEBUG: Next position: block {block_idx}, sentence {sent_idx}")
        
        # Update index first
        self.set_sentence_index(block_idx, sent_idx)
        
        # Navigate by stopping current worker and starting new one from new position
        result = self._navigate_to_sentence(block_idx, sent_idx)
        print(f"DEBUG: Navigate result: {result}")
        return result
    
    def navigate_to_previous_sentence(self):
        """Navigate to previous sentence and start speaking it"""
        if not self.sentence_data or not self.is_speaking:
            return False
            
        block_idx, sent_idx = self.tts_sentence_index
        
        # Find previous sentence
        while block_idx >= 0:
            if sent_idx > 0:
                # Previous sentence in same block
                sent_idx -= 1
                block_data = self.sentence_data[block_idx]
                if block_data['sentences']:  # Make sure block has sentences
                    break
            else:
                # Move to previous block
                block_idx -= 1
                if block_idx >= 0:
                    # Find last sentence in previous block
                    prev_block = self.sentence_data[block_idx]
                    if prev_block['sentences']:
                        sent_idx = len(prev_block['sentences']) - 1
                        break
                    # If previous block is empty, continue searching
        
        # Check if we found a valid previous sentence
        if (block_idx < 0 or 
            not self.sentence_data[block_idx]['sentences']):
            return False  # No previous sentence
        
        # Update index first
        self.set_sentence_index(block_idx, sent_idx)
        
        # Navigate by stopping current worker and starting new one from new position
        return self._navigate_to_sentence(block_idx, sent_idx)

    def navigate_to_next_paragraph(self):
        """Navigate to next paragraph (block) and start speaking it"""
        if not self.sentence_data or not self.is_speaking:
            return False
            
        block_idx, sent_idx = self.tts_sentence_index
        
        # Find next block with sentences
        next_block_idx = block_idx + 1
        while next_block_idx < len(self.sentence_data):
            if self.sentence_data[next_block_idx]['sentences']:
                # Found next block with sentences, go to first sentence
                self.set_sentence_index(next_block_idx, 0)
                return self._navigate_to_sentence(next_block_idx, 0)
            next_block_idx += 1
        
        return False  # No next paragraph found
    
    def navigate_to_previous_paragraph(self):
        """Navigate to previous paragraph (block) and start speaking it"""
        if not self.sentence_data or not self.is_speaking:
            return False
            
        block_idx, sent_idx = self.tts_sentence_index
        
        # Find previous block with sentences
        prev_block_idx = block_idx - 1
        while prev_block_idx >= 0:
            if self.sentence_data[prev_block_idx]['sentences']:
                # Found previous block with sentences, go to first sentence
                self.set_sentence_index(prev_block_idx, 0)
                return self._navigate_to_sentence(prev_block_idx, 0)
            prev_block_idx -= 1
        
        return False  # No previous paragraph found
    
    def _navigate_to_sentence(self, block_idx, sent_idx):
        """Navigate to a specific sentence by cleanly stopping and restarting TTS"""
        print(f"DEBUG: _navigate_to_sentence called for {block_idx}-{sent_idx}")
        print(f"DEBUG: is_speaking: {self.is_speaking}, worker exists: {self.tts_worker is not None}")

        if not self.is_speaking or not self.tts_worker:
            print("DEBUG: Not speaking or no worker, returning False")
            return False
    
        # Check if target sentence is already in buffer
        target_in_buffer = self.tts_worker._check_if_sentence_in_buffer(block_idx, sent_idx)
        print(f"DEBUG: Target sentence {block_idx}-{sent_idx} in buffer: {target_in_buffer}")
    
        # EXTRACT USEFUL BUFFER ENTRIES BEFORE STOPPING WORKER
        preserved_buffer = {}
        if target_in_buffer:
            print("DEBUG: Target sentence in buffer - extracting relevant buffer entries")
            preserved_buffer = self._extract_relevant_buffer_entries(block_idx, sent_idx)
            print(f"DEBUG: Extracted {len(preserved_buffer)} buffer entries for inheritance")

        # Set navigation flag to prevent on_speech_finished from clearing is_speaking
        self._is_navigating = True
        
        # Disconnect the finished signal from the old worker to prevent it from firing
        try:
            self.tts_worker.finished.disconnect(self.on_speech_finished)
        except Exception:
            pass  # Signal might not be connected
    
        # Signal the worker to stop
        print("DEBUG: Stopping worker")
        self.tts_worker.stop()

        # Wait for worker to stop with a reasonable timeout
        if not self.tts_worker.wait(1000):  # 1 second timeout
            print("DEBUG: Worker didn't stop cleanly, terminating")
            self.tts_worker.terminate()
            self.tts_worker.wait(500)
        else:
            print("DEBUG: Worker stopped cleanly")

        # Clean up old worker 
        old_worker = self.tts_worker
        self.tts_worker = None
        old_worker.deleteLater()

        # Stop any lingering audio
        import sounddevice as sd
        sd.stop()

        # Clear highlighting
        self.clear_sentence_highlighting()
    
        print("DEBUG: Starting new worker from new position")
        result = self._start_speaking_from_index(preserved_buffer)
        print(f"DEBUG: New worker started: {result}")
        return result

    def _extract_relevant_buffer_entries(self, target_block, target_sent):
        """Extract buffer entries that are still useful around the target position"""
        if not self.tts_worker:
            return {}

        extracted_buffer = {}

        # Extract sentences within reasonable distance of target
        with self.tts_worker._buffer_lock:
            keys_to_transfer = []
            for (block_idx, sent_idx), audio_path in self.tts_worker._audio_buffer.items():
                # Calculate distance from target
                block_distance = abs(block_idx - target_block)

                # Keep if within 2 blocks or same block within 10 sentences
                if block_distance <= 2:
                    if block_distance == 0:  # Same block
                        sent_distance = abs(sent_idx - target_sent)
                        if sent_distance <= 10:
                            extracted_buffer[(block_idx, sent_idx)] = audio_path
                            keys_to_transfer.append((block_idx, sent_idx))
                    else:  # Different block within 2 blocks
                        extracted_buffer[(block_idx, sent_idx)] = audio_path
                        keys_to_transfer.append((block_idx, sent_idx))
    
            # REMOVE transferred entries from old buffer so they don't get cleaned up
            for key in keys_to_transfer:
                self.tts_worker._audio_buffer.pop(key, None)
    
        print(f"DEBUG: Extracted {len(extracted_buffer)} relevant buffer entries")
        return extracted_buffer

    def _start_speaking_from_index(self, inherited_buffer=None):
        """Start speaking from current sentence index"""
        if not self.sentence_data or not self.config or not self.assistivox_dir:
            return False
            
        block_idx, sent_idx = self.tts_sentence_index
        
        # Validate index
        if (block_idx >= len(self.sentence_data) or 
            sent_idx >= len(self.sentence_data[block_idx]['sentences'])):
            return False
        
        try:
            # Get config path for reading
            config_path = os.path.join(self.assistivox_dir, "config.json")
            
            # Reload config to get latest settings
            with open(config_path, 'r') as f:
                self.config = json.load(f)
           
           # Get engine and voice from new config structure
            engine = self.config["tts_settings"]["engine"]

            if engine == "kokoro":
                selected = self.config["kokoro_settings"]["voice"]
            elif engine == "piper":
                selected = self.config["piper_settings"]["voice"]

            if engine == "piper":
                # Import dynamically to avoid startup dependencies
                from gui.tts.PiperTTS import PiperTTS
                
                # Voice name
                engine_type = "piper"
                model_nickname = selected

                # Find the Piper path from config.json
                if "piper_settings" not in self.config or "path" not in self.config["piper_settings"]:
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.critical(self.text_edit, "Piper Not Installed",
                                       "Piper TTS is not properly installed. Please run the setup script to install Piper.")
                    return False
                
                piper_path = self.config["piper_settings"]["path"]

                # Construct path to piper binary
                piper_bin = os.path.join(piper_path, "build", "piper")
                if not os.path.isfile(piper_bin):
                    print(f"Piper binary not found at {piper_bin}")
                    return False

                # Find model paths
                engine_dir = os.path.join(self.assistivox_dir, "tts-models", "piper")
                model_path = None
                config_json = None

                if os.path.isdir(engine_dir):
                    # try exact match (new structure)
                    exact_match_dir = os.path.join(engine_dir, model_nickname)
                    if os.path.isdir(exact_match_dir):
                        for fname in os.listdir(exact_match_dir):
                            if fname.endswith(".onnx") and model_nickname in fname:
                                model_path = os.path.join(exact_match_dir, fname)
                                config_json = model_path + ".json"
                                if os.path.exists(config_json):
                                    break

                if not model_path or not config_json:
                    print(f"Model '{model_nickname}' not found in {engine_dir}")
                    return False

                # Create TTS object
                tts = PiperTTS(piper_bin, model_path, config_json)
                
            elif engine == "kokoro":
                # Import Kokoro TTS
                from gui.tts.kokoro_manager import KokoroTTS, get_kokoro_docker_manager
    
                # Get Docker manager
                docker_port = self.config.get("kokoro_settings", {}).get("docker_port", 8880)
                docker_manager = get_kokoro_docker_manager(docker_port)

                # Get GPU setting
                use_gpu = self.config.get("kokoro_settings", {}).get("use_gpu", False)

                # Start Docker container if not already running
                try:
                    docker_manager.start_container(use_gpu=use_gpu)
                except RuntimeError as e:
                    print(f"Failed to start Kokoro Docker container: {e}")
                    return False
    
                # Use the voice directly from kokoro_settings
                voice_name = selected

                # Create Kokoro TTS object
                tts = KokoroTTS(docker_manager, voice_name)

            else:
                print(f"Unknown TTS engine: {engine}")
                return False

            print(f"DEBUG: Fresh TTS object created, _stop_requested: {getattr(tts, '_stop_requested', 'N/A')}")

            # Get speed (default 1.0)
            speed = 1.0
            if "tts_settings" in self.config and "speed" in self.config["tts_settings"]:
                speed = float(self.config["tts_settings"]["speed"])

            # Get pause (default 0)
            pause_ms = 0
            if "tts_settings" in self.config and "pause_ms" in self.config["tts_settings"]:
                pause_ms = int(self.config["tts_settings"]["pause_ms"])

            # Ensure no worker is running before creating a new one
            if self.tts_worker:
                print("Warning: Starting new TTS worker while old one exists")
                if self.tts_worker.isRunning():
                    self.tts_worker.stop()
                    self.tts_worker.wait(1000)
                    if self.tts_worker.isRunning():
                        self.tts_worker.terminate()
                        self.tts_worker.wait(500)
                self.tts_worker.deleteLater()
                self.tts_worker = None

            # Create and start the worker thread from current index
            print(f"DEBUG: Creating new TTSWorker from {block_idx}-{sent_idx}")
            self.tts_worker = TTSWorker(tts, self.sentence_data, silence_ms=pause_ms, speed=speed, start_block=block_idx, start_sentence=sent_idx)

            # INHERIT BUFFER FROM PREVIOUS WORKER
            if inherited_buffer:
                print(f"DEBUG: Inheriting {len(inherited_buffer)} buffer entries to new worker")
                with self.tts_worker._buffer_lock:
                    self.tts_worker._audio_buffer.update(inherited_buffer)
                print("DEBUG: Buffer inheritance complete")
            
            # Connect signals with unique connection to prevent duplicate connections
            from PySide6.QtCore import Qt
            self.tts_worker.finished.connect(self.on_speech_finished, Qt.UniqueConnection)
            self.tts_worker.error.connect(self.on_speech_error, Qt.UniqueConnection)
            self.tts_worker.sentence_started.connect(self.highlight_current_sentence, Qt.UniqueConnection)

            # Update state
            self.is_speaking = True

            # Start the thread
            self.tts_worker.start()
            print(f"Started TTS worker from sentence {block_idx}-{sent_idx}")
            
            # Clear navigation flag AFTER starting the worker
            # This gives time for any pending finished signals to be processed
            if self._is_navigating:
                # Use a QTimer to clear the flag after a short delay
                from PySide6.QtCore import QTimer
                QTimer.singleShot(100, lambda: setattr(self, '_is_navigating', False))
            
            return True

        except Exception as e:
            print(f"Failed to start speaking from index: {str(e)}")
            self.is_speaking = False
            return False

    def toggle_speech(self):
        """Toggle text-to-speech on/off"""
        import json

        if self.is_speaking:
            print("Toggle speech: stopping active speech")
            # If already speaking, stop it
            self.stop_speech()
            return

        # Get the text to speak - we need the document, not just plain text
        document = self.text_edit.document()
        if document.isEmpty():
            return  # Nothing to speak

        print("Toggle speech: preparing to speak text")

        # Check if config exists
        if not self.config or not self.assistivox_dir:
            QMessageBox.warning(self.text_edit, "Configuration Missing",
                              "Text-to-speech configuration is missing.")
            return

        # Check if TTS is properly configured in settings
        if ("tts_settings" not in self.config or 
            "engine" not in self.config["tts_settings"]):
            QMessageBox.warning(self.text_edit, "TTS Not Configured",
                             "Text-to-speech is not configured. Please go to Settings and select a TTS model.")
            return

        engine = self.config["tts_settings"]["engine"]
        if engine == "kokoro":
            if ("kokoro_settings" not in self.config or 
                "voice" not in self.config["kokoro_settings"]):
                QMessageBox.warning(self.text_edit, "TTS Not Configured",
                                 "Kokoro voice is not configured. Please go to Settings and select a Kokoro voice.")
                return
        elif engine == "piper":
            if ("piper_settings" not in self.config or 
                "voice" not in self.config["piper_settings"] or
                "path" not in self.config["piper_settings"]):
                QMessageBox.warning(self.text_edit, "TTS Not Configured",
                                 "Piper voice is not configured. Please go to Settings and select a Piper voice.")
                return

        try:
            # Get the parent ReadOnlyTTSWidget to reuse its sentence boundary data
            parent_widget = self.text_edit.parent()
            if (hasattr(parent_widget, 'sentence_boundary_data') and 
                parent_widget.sentence_boundary_data is not None):
                print("Reusing sentence boundary data from ReadOnlyTTSWidget...")
                self.sentence_data = parent_widget.sentence_boundary_data
            else:
                # Fallback: Run sentence detection if no pre-calculated data exists
                from gui.nlp.sentence_detector import SentenceDetector
                
                config_path = os.path.join(self.assistivox_dir, "config.json")
                detector = SentenceDetector(config_path)
                
                print("Running sentence detection...")
                self.sentence_data = detector.detect_sentences_in_document(document)

            # Check if we have any sentences to speak
            total_sentences = sum(len(block['sentences']) for block in self.sentence_data)
            if total_sentences == 0:
                print("No sentences found to speak")
                return
                
            print(f"Found {total_sentences} sentences across {len(self.sentence_data)} blocks")

            # Reset navigation flag
            self._is_navigating = False

            # Start speaking from current index
            self._start_speaking_from_index(None)

        except Exception as e:
            self.is_speaking = False
            QMessageBox.critical(self.text_edit, "TTS Error", f"Failed to speak text: {str(e)}")

    def stop_speech(self):
        """Stop current speech if in progress"""
        if self.is_speaking and self.tts_worker and self.tts_worker.isRunning():
            print("Stopping speech...")
            
            # Disconnect the finished signal to prevent it from firing
            try:
                self.tts_worker.finished.disconnect(self.on_speech_finished)
            except Exception:
                pass  # Signal might not be connected
            
            # Signal the worker to stop
            self.tts_worker.stop()
            
            # Wait for the thread to finish with a longer timeout
            if not self.tts_worker.wait(2000):  # Wait up to 2 seconds
                print("Thread didn't exit cleanly, forcing termination")
                self.tts_worker.terminate()
                self.tts_worker.wait(1000)  # Wait for forced termination
            
            # Make sure we explicitly stop any audio playback
            import sounddevice as sd
            sd.stop()
            
            # Clear highlighting
            self.clear_sentence_highlighting()
            
            # Clean up the worker
            self.tts_worker.deleteLater()
            self.tts_worker = None
            
            # Update state
            self.is_speaking = False
            self._is_navigating = False
            print("Speech state set to stopped")

    def on_speech_finished(self):
        """Called when speech completes normally"""
        print("DEBUG: on_speech_finished() called")
        print(f"DEBUG: Current sentence index: {self.tts_sentence_index}")
        print(f"DEBUG: Total blocks: {len(self.sentence_data) if self.sentence_data else 0}")
        print(f"DEBUG: _is_navigating: {self._is_navigating}")
        
        # If we're navigating, don't change is_speaking state
        if self._is_navigating:
            print("DEBUG: Navigation in progress, not changing is_speaking state")
            return
        
        # Check if there are more sentences to speak
        if self.sentence_data:
            block_idx, sent_idx = self.tts_sentence_index
            has_more = False
            
            # Check if there are more sentences in current block or future blocks
            for check_block in range(block_idx, len(self.sentence_data)):
                block_sentences = self.sentence_data[check_block]['sentences']
                if check_block == block_idx:
                    # Current block - check if more sentences after current
                    if sent_idx + 1 < len(block_sentences):
                        has_more = True
                        break
                else:
                    # Future block - check if it has any sentences
                    if block_sentences:
                        has_more = True
                        break
            
            print(f"DEBUG: Has more sentences: {has_more}")
            
            if has_more:
                print("DEBUG: More sentences available, but worker finished unexpectedly")
                # This shouldn't happen - the worker should continue to next sentences
                # This indicates the TTSWorker.run() method has a problem
        
        # Clear any highlighting
        self.clear_sentence_highlighting()
    
        self.is_speaking = False
        print(f"DEBUG: is_speaking set to False")

    def on_speech_error(self, error_message):
        """Called when an error occurs during speech"""
        print(f"DEBUG: Speech error: {error_message} - setting is_speaking to False")
        self.is_speaking = False
        QMessageBox.critical(self.text_edit, "TTS Error", f"Error during speech: {error_message}")

    def highlight_current_sentence(self, block_index, sentence_index):
        """Highlight the sentence at the given block and sentence index"""
        # Skip highlighting if text_edit is None (voice test mode)
        if not self.text_edit:
            return
            
        # Update our internal index
        self.set_sentence_index(block_index, sentence_index)
        
        if not self.sentence_data or block_index >= len(self.sentence_data):
            return

        block_data = self.sentence_data[block_index]
        offsets = block_data['offsets']
        
        if sentence_index >= len(offsets):
            return

        # Clear any existing highlighting first
        self.clear_sentence_highlighting()

        # Calculate absolute position in the document
        # We need to find the start of the target block
        document = self.text_edit.document()
        block = document.begin()
        absolute_block_start = 0
        
        # Find the target block and calculate its absolute start position
        current_block_index = 0
        while block.isValid() and current_block_index < block_index:
            absolute_block_start += len(block.text()) + 1  # +1 for newline
            block = block.next()
            current_block_index += 1
        
        if not block.isValid():
            return
        
        # Get the sentence offsets relative to the block
        sentence_start, sentence_end = offsets[sentence_index]
        
        # Calculate absolute positions
        absolute_start = absolute_block_start + sentence_start
        absolute_end = absolute_block_start + sentence_end
        
        # Create cursor for highlighting
        cursor = QTextCursor(document)
        cursor.setPosition(absolute_start)
        cursor.setPosition(absolute_end + 1, QTextCursor.KeepAnchor)  # +1 to include last char

        # Store the cursor for later clearing
        self.current_highlight_cursor = QTextCursor(cursor)

        # Apply highlight format - preserve existing formatting and only change text color
        highlight_format = QTextCharFormat()
        highlight_format.setForeground(QColor(0, 120, 215))  # Blue color for better contrast
        cursor.mergeCharFormat(highlight_format)  # Use mergeCharFormat to preserve other formatting

    def clear_sentence_highlighting(self):
        """Clear sentence highlighting while preserving original formatting"""
        if self.current_highlight_cursor:
            # Get the original format by looking at adjacent text
            cursor = QTextCursor(self.current_highlight_cursor)
            
            # Move to just before the highlighted text to get the original color
            temp_cursor = QTextCursor(cursor.document())
            temp_cursor.setPosition(max(0, cursor.selectionStart() - 1))
            original_format = temp_cursor.charFormat()
            
            # If we're at the beginning, try to get format from after the selection
            if cursor.selectionStart() == 0:
                temp_cursor.setPosition(min(cursor.document().characterCount() - 1, cursor.selectionEnd() + 1))
                original_format = temp_cursor.charFormat()
            
            # Create a format that only resets the foreground color
            reset_format = QTextCharFormat()
            reset_format.setForeground(original_format.foreground())
            
            # Apply the reset format to restore original color
            cursor.mergeCharFormat(reset_format)
            
            # Clear the stored cursor
            self.current_highlight_cursor = None

    def cleanup_resources(self):
        """Clean up TTS resources"""
        # Stop any ongoing speech
        if self.is_speaking:
            self.stop_speech()

        # Make sure the thread is properly terminated and cleaned up
        if self.tts_worker and self.tts_worker.isRunning():
            print("Cleaning up TTS worker thread")
            
            # Disconnect signals to prevent them from firing during cleanup
            try:
                self.tts_worker.finished.disconnect()
                self.tts_worker.error.disconnect()
                self.tts_worker.sentence_started.disconnect()
            except Exception:
                pass  # Signals might not be connected
            
            self.tts_worker.stop()
            
            # Wait for the thread to finish with a longer timeout
            if not self.tts_worker.wait(2000):  # Wait up to 2 seconds
                print("Thread didn't exit cleanly during cleanup, forcing termination")
                self.tts_worker.terminate()
                self.tts_worker.wait(1000)  # Wait for forced termination
            
            # Schedule thread object for deletion
            self.tts_worker.deleteLater()
            self.tts_worker = None

        # Make sure the audio device is released
        try:
            import sounddevice as sd
            sd.stop()
        except Exception as e:
            print(f"Error stopping sounddevice: {str(e)}")

    def navigate_to_first_sentence(self):
        """Navigate to the first sentence in the first block"""
        if not self.sentence_data or not self.is_speaking:
            return False
    
        # Set to first sentence (0, 0)
        self.set_sentence_index(0, 0)
    
        # Navigate by stopping current worker and starting from first sentence
        return self._navigate_to_sentence(0, 0)
