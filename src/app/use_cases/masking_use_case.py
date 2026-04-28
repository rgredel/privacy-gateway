from typing import List, Dict, Tuple
from src.app.domain.ports import IPrivacyEngine

class MaskingUseCase:
    """Use case responsible for text pseudonymization and vault management.
    
    This use case coordinates the physical masking of PII entities within a given text,
    leveraging the injected privacy engine.
    """
    
    def __init__(self, privacy_engine: IPrivacyEngine):
        """Initializes the use case with a privacy engine.

        Args:
            privacy_engine (IPrivacyEngine): The engine used for masking operations.
        """
        self.privacy_engine = privacy_engine

    def execute(self, text: str, pii_entities: List[Dict[str, str]], shorten: bool = False) -> Tuple[str, Dict[str, str]]:
        """Masks PII entities and optionally shortens the context.

        Args:
            text (str): The raw text to be masked.
            pii_entities (List[Dict[str, str]]): List of labeled PII entities to mask.
            shorten (bool): Whether to reduce the text to PII-containing fragments.

        Returns:
            Tuple[str, Dict[str, str]]: (masked_text, token_vault).
        """
        if not pii_entities:
            return text, {}
            
        masked_text, vault = self.privacy_engine.mask_text(text, pii_entities)
        
        if shorten:
            masked_text = self._reduce_to_pii_fragments(masked_text)
            
        return masked_text, vault

    def _reduce_to_pii_fragments(self, text: str, window: int = 1) -> str:
        """Algorithmic reduction of text to fragments containing PII tokens with a context window of sentences."""
        import re
        # Podział na zdania (uproszczony regex)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Wzór szukający tagów [ETYKIETA_ID]
        tag_pattern = r'\[[A-Z_]+_\d+\]'
        
        # Znajdź indeksy zdań zawierających PII
        pii_indices = [i for i, s in enumerate(sentences) if re.search(tag_pattern, s)]
        
        if not pii_indices:
            return "[...]"
            
        # Zbiór indeksów do zachowania (PII + okno)
        keep_indices = set()
        for idx in pii_indices:
            for i in range(max(0, idx - window), min(len(sentences), idx + window + 1)):
                keep_indices.add(i)
                
        sorted_indices = sorted(list(keep_indices))
        
        reduced = []
        last_idx = -2
        for idx in sorted_indices:
            if idx > last_idx + 1:
                if reduced:
                    reduced.append("[...]")
            reduced.append(sentences[idx])
            last_idx = idx
            
        if last_idx < len(sentences) - 1:
            reduced.append("[...]")
            
        # Usunięcie początkowych/końcowych [...]
        if reduced and reduced[0] == "[...]": reduced.pop(0)
        if reduced and reduced[-1] == "[...]": reduced.pop()
        
        return " ".join(reduced)
