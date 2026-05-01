from typing import List, Dict, Optional
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

from src.app.domain.ports import IPrivacyEngine
from src.app.domain.entities import RecognizedEntity, PIIEntity

class PresidioService(IPrivacyEngine):
    """Adapter for Microsoft Presidio library.
    
    Handles PII detection (Analyzer) and anonymization (Anonymizer).
    """
    
    def __init__(self, analyzer: AnalyzerEngine) -> None:
        """Initializes the service with a pre-configured analyzer engine.
        
        Args:
            analyzer (AnalyzerEngine): Presidio analyzer with loaded recognizers.
        """
        self.analyzer = analyzer
        self.anonymizer = AnonymizerEngine()

    def get_candidates(self, text: str) -> List[str]:
        """Extracts raw PII candidate strings from text.
        
        Args:
            text (str): Input text.
            
        Returns:
            List[str]: List of identified PII values.
        """
        results = self.analyzer.analyze(text=text, language="pl")
        return [text[r.start:r.end] for r in results]

    def analyze_detailed(self, text: str) -> List[RecognizedEntity]:
        """Performs detailed analysis including positions and scores.
        
        Args:
            text (str): Input text.
            
        Returns:
            List[RecognizedEntity]: Detailed entity models.
        """
        results = self.analyzer.analyze(text=text, language="pl")
        return [
            RecognizedEntity(
                value=text[r.start:r.end],
                label=r.entity_type,
                start=r.start,
                end=r.end,
                score=r.score,
                recognizer=r.recognizer if hasattr(r, 'recognizer') else "unknown"
            ) for r in results
        ]

    def get_labeled_entities(self, text: str) -> List[PIIEntity]:
        """Returns PII entities with their labels directly from the engine.
        
        Args:
            text (str): Input text.
            
        Returns:
            List[PIIEntity]: List of labeled entities.
        """
        results = self.analyzer.analyze(text=text, language="pl")
        return [
            PIIEntity(value=text[r.start:r.end], label=r.entity_type) 
            for r in results
        ]

    def mask_text(self, text: str, pii_entities: List[PIIEntity]) -> tuple[str, Dict[str, str]]:
        """Masks the text using a vault-based mapping.
        
        Args:
            text (str): Original text.
            pii_entities (List[PIIEntity]): Entities to mask.
            
        Returns:
            tuple[str, Dict[str, str]]: (Masked text, Vault).
        """
        vault: Dict[str, str] = {}
        masked_text = text
        
        # Sort from longest to shortest to avoid partial replacements
        sorted_entities = sorted(pii_entities, key=lambda x: len(x.value), reverse=True)
        
        for i, entity in enumerate(sorted_entities):
            val = entity.value
            label = entity.label
            token = f"[{label}_{i}]"
            vault[token] = val
            masked_text = masked_text.replace(val, token)
            
        return masked_text, vault

    def de_identify(self, text: str, vault: Dict[str, str]) -> str:
        """Restores original values from the vault.
        
        Args:
            text (str): Masked text.
            vault (Dict[str, str]): Token -> Original mapping.
            
        Returns:
            str: De-identified text.
        """
        result = text
        for token, original in vault.items():
            result = result.replace(token, original)
        return result
