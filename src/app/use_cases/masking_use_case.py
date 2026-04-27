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

    def execute(self, text: str, pii_entities: List[Dict[str, str]]) -> Tuple[str, Dict[str, str]]:
        """Masks PII entities in the provided text.

        Args:
            text (str): The raw text to be masked.
            pii_entities (List[Dict[str, str]]): List of labeled PII entities to mask.

        Returns:
            Tuple[str, Dict[str, str]]: A tuple containing (masked_text, token_vault).
        """
        if not pii_entities:
            return text, {}
            
        return self.privacy_engine.mask_text(text, pii_entities)
