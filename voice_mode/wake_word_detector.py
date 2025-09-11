"""Wake word detection with fuzzy matching and phonetic alternatives."""

import re
import difflib
from typing import List, Tuple, Optional, Dict
import logging

logger = logging.getLogger("voice-mode")


class WakeWordDetector:
    """Improved wake word detection with fuzzy matching and phonetic alternatives."""
    
    # Phonetic alternatives for commonly misheard wake words
    PHONETIC_ALTERNATIVES = {
        "voicemode": [
            "voice mode", "voice mood", "voice moad", "boys mode", "voice moat",
            "voice mod", "voice note", "voice load", "voice code", "voice road",
            "boyce mode", "voices mode", "voice mo", "voice most", "voice boat"
        ],
        "hey voicemode": [
            "hey voice mode", "hey voice mood", "hey boys mode", "a voice mode",
            "hey voice mod", "hey voice note", "hey voice load", "hey voice code",
            "hey boyce mode", "hey voices mode", "hey voice mo", "hay voice mode"
        ],
        "cora": [
            "kora", "corra", "korra", "coral", "cora", "core a", "cor a",
            "kora", "quora", "corer", "korea", "koura", "courra", "kura"
        ],
        "hey cora": [
            "hey kora", "hey corra", "hey korra", "hey coral", "hey core a",
            "hey cor a", "hey quora", "hey korea", "hey koura", "hey kura",
            "a cora", "a kora", "hey corer", "hay cora", "hay kora",
            "hey corah", "hey korah", "hey corey", "hey coura", "hey coraa"
        ],
        "computer": [
            "computer", "commuter", "computers", "compute her", "compute or",
            "competer", "komputor", "can pewter", "com pewter"
        ],
        "hey claude": [
            "hey claud", "hey cloud", "hey clade", "hey clauds", "hey clod",
            "a claude", "hey claude", "hey clawd", "hey klaud", "hay claude"
        ],
        "assistant": [
            "assistant", "assistance", "assistants", "assist ant", "a sistant",
            "assistent", "asistant"
        ]
    }
    
    def __init__(self, wake_words: List[str], similarity_threshold: float = 0.7):
        """Initialize the wake word detector.
        
        Args:
            wake_words: List of wake words to detect
            similarity_threshold: Minimum similarity score for fuzzy matching (0-1)
        """
        self.wake_words = [w.lower().strip() for w in wake_words]
        self.similarity_threshold = similarity_threshold
        
        # Build expanded wake word list with alternatives
        self.expanded_wake_words = self._build_expanded_list()
        
        # Create regex patterns for more flexible matching
        self.patterns = self._build_patterns()
        
        logger.info(f"Wake word detector initialized with {len(self.wake_words)} wake words")
        logger.debug(f"Expanded to {len(self.expanded_wake_words)} variants with phonetic alternatives")
        
    def _build_expanded_list(self) -> Dict[str, str]:
        """Build expanded list of wake words with phonetic alternatives.
        
        Returns:
            Dict mapping variant -> original wake word
        """
        expanded = {}
        
        for wake_word in self.wake_words:
            # Add original
            expanded[wake_word] = wake_word
            
            # Add phonetic alternatives if available
            if wake_word in self.PHONETIC_ALTERNATIVES:
                for variant in self.PHONETIC_ALTERNATIVES[wake_word]:
                    expanded[variant.lower()] = wake_word
            
            # Add versions with/without "hey"
            if wake_word.startswith("hey "):
                base = wake_word[4:]
                expanded[base] = wake_word
                if base in self.PHONETIC_ALTERNATIVES:
                    for variant in self.PHONETIC_ALTERNATIVES[base]:
                        expanded[variant.lower()] = wake_word
            elif "hey " + wake_word in self.PHONETIC_ALTERNATIVES:
                for variant in self.PHONETIC_ALTERNATIVES["hey " + wake_word]:
                    expanded[variant.lower()] = wake_word
                    
        return expanded
    
    def _build_patterns(self) -> List[Tuple[re.Pattern, str]]:
        """Build regex patterns for flexible matching.
        
        Returns:
            List of (pattern, original_wake_word) tuples
        """
        patterns = []
        
        for wake_word in self.wake_words:
            # Create pattern with optional word boundaries and spacing variations
            # Allow for some characters before/after
            escaped = re.escape(wake_word)
            # Replace spaces with flexible whitespace
            escaped = escaped.replace(r"\ ", r"\s+")
            
            # Create pattern that's somewhat flexible
            pattern = re.compile(
                r"(?:^|[^a-z])(" + escaped + r")(?:[^a-z]|$)",
                re.IGNORECASE
            )
            patterns.append((pattern, wake_word))
            
        return patterns
    
    def detect(self, text: str) -> Tuple[bool, Optional[str], Optional[str], float]:
        """Detect wake word in text with fuzzy matching.
        
        Args:
            text: Text to search for wake words
            
        Returns:
            Tuple of (detected, wake_word, command, confidence)
            - detected: Whether a wake word was found
            - wake_word: The original wake word that was detected
            - command: Text after the wake word
            - confidence: Confidence score (0-1)
        """
        text_lower = text.lower().strip()
        
        # First try exact matching with expanded list
        for variant, original in self.expanded_wake_words.items():
            if variant in text_lower:
                pos = text_lower.find(variant)
                command = text[pos + len(variant):].strip()
                logger.debug(f"Exact match found: '{variant}' -> '{original}'")
                return True, original, command, 1.0
        
        # Try regex patterns
        for pattern, original in self.patterns:
            match = pattern.search(text_lower)
            if match:
                pos = match.end(1)
                command = text[pos:].strip()
                logger.debug(f"Regex match found: '{match.group(1)}' -> '{original}'")
                return True, original, command, 0.9
        
        # Try fuzzy matching
        best_match = self._fuzzy_match(text_lower)
        if best_match:
            variant, original, similarity, pos, length = best_match
            command = text[pos + length:].strip()
            logger.debug(f"Fuzzy match found: '{variant}' -> '{original}' (similarity: {similarity:.2f})")
            return True, original, command, similarity
            
        return False, None, None, 0.0
    
    def _fuzzy_match(self, text: str) -> Optional[Tuple[str, str, float, int, int]]:
        """Perform fuzzy matching against wake words.
        
        Args:
            text: Text to search
            
        Returns:
            Tuple of (matched_variant, original_wake_word, similarity, position, length)
            or None if no match above threshold
        """
        best_match = None
        best_similarity = 0.0
        
        # Split text into words and phrases
        words = text.split()
        
        # Check different n-grams
        for n in range(1, min(4, len(words) + 1)):  # Check up to 3-word phrases
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i+n])
                
                # Check against all expanded wake words
                for variant, original in self.expanded_wake_words.items():
                    # Use sequence matcher for similarity
                    similarity = difflib.SequenceMatcher(None, phrase, variant).ratio()
                    
                    if similarity > best_similarity and similarity >= self.similarity_threshold:
                        # Calculate position in original text
                        pos = text.find(phrase)
                        best_match = (phrase, original, similarity, pos, len(phrase))
                        best_similarity = similarity
        
        return best_match
    
    def add_wake_word(self, wake_word: str, alternatives: Optional[List[str]] = None):
        """Add a new wake word with optional alternatives.
        
        Args:
            wake_word: The wake word to add
            alternatives: Optional list of phonetic alternatives
        """
        wake_word_lower = wake_word.lower().strip()
        
        if wake_word_lower not in self.wake_words:
            self.wake_words.append(wake_word_lower)
            
            # Add to phonetic alternatives if provided
            if alternatives:
                self.PHONETIC_ALTERNATIVES[wake_word_lower] = alternatives
            
            # Rebuild expanded list and patterns
            self.expanded_wake_words = self._build_expanded_list()
            self.patterns = self._build_patterns()
            
            logger.info(f"Added wake word: '{wake_word}' with {len(alternatives or [])} alternatives")


def test_detector():
    """Test the wake word detector with various inputs."""
    
    # Create detector with common wake words
    detector = WakeWordDetector([
        "hey voicemode",
        "hey cora", 
        "computer",
        "hey claude"
    ])
    
    # Test cases that might be misheard
    test_cases = [
        "hey voice mode what time is it",
        "hey kora tell me the weather",
        "a voice mode open safari",
        "hey coral what's the date",
        "commuter play some music",
        "hey cloud explain quantum physics",
        "hey boys mode what's happening",
        "hey core a how are you",
        "the computer is ready",  # Should not match (computer not at start)
        "computer what's the battery level",
        "hey claud can you help me"
    ]
    
    print("Wake Word Detection Tests")
    print("=" * 50)
    
    for text in test_cases:
        detected, wake_word, command, confidence = detector.detect(text)
        
        if detected:
            print(f"✓ '{text}'")
            print(f"  Wake word: '{wake_word}' (confidence: {confidence:.2f})")
            print(f"  Command: '{command}'")
        else:
            print(f"✗ '{text}' - No wake word detected")
        print()


if __name__ == "__main__":
    test_detector()