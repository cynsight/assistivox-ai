# gui/nlp/sentence_detector.py
"""
Sentence boundary detection for TTS highlighting
Supports both nupunkt and spaCy methods
"""

from PySide6.QtGui import QTextDocument, QTextCursor
from typing import List, Dict, Tuple
import json

# Import sentence detection libraries
try:
    from nupunkt import PunktSentenceTokenizer
    NUPUNKT_AVAILABLE = True
except ImportError:
    NUPUNKT_AVAILABLE = False
    print("Warning: nupunkt not available")

try:
    import spacy
    SPACY_AVAILABLE = True
    # Try to load the model
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        print("Warning: spaCy model 'en_core_web_sm' not found")
        SPACY_AVAILABLE = False
except ImportError:
    SPACY_AVAILABLE = False
    print("Warning: spaCy not available")


class SentenceDetector:
    """Main sentence boundary detection class"""
    
    def __init__(self, config_path=None):
        self.config_path = config_path
        self.method = self._load_method_from_config()
        
        # Initialize tokenizers
        if NUPUNKT_AVAILABLE:
            self.nupunkt_tokenizer = PunktSentenceTokenizer()
        else:
            self.nupunkt_tokenizer = None
            
    def _load_method_from_config(self):
        """Load sentence boundary method from config"""
        if not self.config_path:
            return "nupunkt"  # Default to nupunkt
            
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                
            if "nlp_settings" in config and "sentence_boundaries" in config["nlp_settings"]:
                method = config["nlp_settings"]["sentence_boundaries"]
                # Handle both old numeric format and new string format
                if isinstance(method, int):
                    return "nupunkt" if method == 1 else "spacy"
                elif isinstance(method, str):
                    return method if method in ["nupunkt", "spacy"] else "nupunkt"
                else:
                    return "nupunkt"
            else:
                return "nupunkt"  # Default to nupunkt
        except Exception:
            return "nupunkt"  # Default to nupunkt
    
    def detect_sentences_in_document(self, document: QTextDocument) -> List[Dict]:
        """
        Main method: Process QTextDocument block by block
        
        Args:
            document: QTextDocument to process
            
        Returns:
            List of dictionaries, one per block:
            [
                {
                    'block_text': str,
                    'sentences': [str, str, ...],
                    'offsets': [(start, end), (start, end), ...]
                },
                ...
            ]
        """
        results = []
        
        # Iterate through document blocks (paragraphs)
        block = document.begin()
        while block.isValid():
            block_text = block.text()
            
            if block_text.strip():  # Only process non-empty blocks
                # Get sentences and offsets for this block
                sentences, offsets = self._detect_sentences_in_block(block_text)
                # Get font size for each sentence in this block
                font_sizes = self._get_font_sizes_for_sentences(document, block, sentences, offsets)
                
                results.append({
                    'block_text': block_text,
                    'sentences': sentences,
                    'offsets': offsets,
                    'font_sizes': font_sizes
                })
            else:
                # Empty block - still add it to maintain block indexing
                results.append({
                    'block_text': block_text,
                    'sentences': [],
                    'offsets': [],
                    'font_sizes': []
                })
            
            block = block.next()
            
        return results

    def _get_font_sizes_for_sentences(self, document: QTextDocument, block, sentences: List[str], offsets: List[Tuple[int, int]]) -> List[float]:
        """
        Get font size for each sentence in a block
        
        Args:
            document: QTextDocument to analyze
            block: Current text block
            sentences: List of sentence strings
            offsets: List of (start, end) offsets for each sentence relative to block
            
        Returns:
            List of font sizes (in points) for each sentence
        """
        font_sizes = []
        
        # Calculate absolute block start position in document
        block_start_pos = 0
        temp_block = document.begin()
        while temp_block.isValid() and temp_block != block:
            block_start_pos += len(temp_block.text()) + 1  # +1 for newline
            temp_block = temp_block.next()
        
        # Get font size for each sentence
        for sentence_start, sentence_end in offsets:
            # Calculate absolute position in document
            abs_pos = block_start_pos + sentence_start
            
            # Create cursor at sentence start to get formatting
            cursor = QTextCursor(document)
            cursor.setPosition(abs_pos)
            char_format = cursor.charFormat()
            
            # Get font size - use pointSizeF for precision, fallback to pointSize
            font_size = char_format.fontPointSize()
            if font_size <= 0:  # Invalid font size
                # Get document default font size
                font_size = document.defaultFont().pointSizeF()
                if font_size <= 0:
                    font_size = 12.0  # Fallback default
            
            font_sizes.append(font_size)
        
        return font_sizes
    
    def _detect_sentences_in_block(self, text: str) -> Tuple[List[str], List[Tuple[int, int]]]:
        """
        Detect sentences in a single block of text
        
        Args:
            text: Text block to process
            
        Returns:
            Tuple of (sentences_list, offsets_list)
            offsets are relative to the start of the block
        """
        if not text.strip():
            return [], []
            
        if self.method == "nupunkt":
            return self._nupunkt_sentences(text)
        elif self.method == "spacy":
            return self._spacy_sentences(text)
        else:
            # Fallback to nupunkt
            return self._nupunkt_sentences(text)
    
    def _nupunkt_sentences(self, text: str) -> Tuple[List[str], List[Tuple[int, int]]]:
        """Sentence detection using nupunkt"""
        if not NUPUNKT_AVAILABLE or not self.nupunkt_tokenizer:
            # Fallback: treat entire text as one sentence
            return [text], [(0, len(text) - 1)]
            
        try:
            spans = list(self.nupunkt_tokenizer.span_tokenize(text))
            sentences = [text[start:end] for start, end in spans]
            offsets = [(start, end - 1) for start, end in spans]  # Convert to inclusive end
            return sentences, offsets
        except Exception as e:
            print(f"Error in nupunkt sentence detection: {e}")
            # Fallback: treat entire text as one sentence
            return [text], [(0, len(text) - 1)]
    
    def _spacy_sentences(self, text: str) -> Tuple[List[str], List[Tuple[int, int]]]:
        """Sentence detection using spaCy"""
        if not SPACY_AVAILABLE:
            # Fallback to nupunkt or simple fallback
            return self._nupunkt_sentences(text)
            
        try:
            doc = nlp(text)
            sentences = [sent.text for sent in doc.sents]
            offsets = [(sent.start_char, sent.end_char - 1) for sent in doc.sents]  # Convert to inclusive end
            return sentences, offsets
        except Exception as e:
            print(f"Error in spaCy sentence detection: {e}")
            # Fallback to nupunkt
            return self._nupunkt_sentences(text)
    
    def set_method(self, method: str):
        """Set the sentence detection method ('nupunkt' or 'spacy')"""
        if method in ["nupunkt", "spacy"]:
            self.method = method
        else:
            self.method = "nupunkt"
    
    def get_available_methods(self) -> Dict[str, str]:
        """Get available sentence detection methods"""
        methods = {}
        
        if NUPUNKT_AVAILABLE:
            methods["nupunkt"] = "nupunkt (Default)"
        else:
            methods["nupunkt"] = "nupunkt (Not Available)"
            
        if SPACY_AVAILABLE:
            methods["spacy"] = "spaCy"
        else:
            methods["spacy"] = "spaCy (Not Available)"
            
        return methods
