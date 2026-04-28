from typing import List, Dict, Optional
from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from src.app.domain.ports import IPrivacyEngine
from src.app.domain.entities import RecognizedEntity

class PresidioService(IPrivacyEngine):
    """
    Adapter dla biblioteki Microsoft Presidio.
    Obsługuje detekcję (Analyzer) i anonimizację (Anonymizer).
    """
    
    def __init__(self, analyzer: AnalyzerEngine):
        self.analyzer = analyzer
        self.anonymizer = AnonymizerEngine()

    def get_candidates(self, text: str) -> List[str]:
        """Pobiera potencjalne PII (tylko wartości tekstowe)."""
        results = self.analyzer.analyze(text=text, language="pl")
        return [text[r.start:r.end] for r in results]

    def analyze_detailed(self, text: str) -> List[RecognizedEntity]:
        """Pobiera szczegółowe wyniki rozpoznawania wraz z pewnością (score)."""
        results = self.analyzer.analyze(text=text, language="pl")
        return [
            RecognizedEntity(
                value=text[r.start:r.end],
                label=r.entity_type,
                start=r.start,
                end=r.end,
                score=r.score
            ) for r in results
        ]

    def get_labeled_entities(self, text: str) -> List[Dict[str, str]]:
        """Pobiera potencjalne PII wraz z etykietami."""
        results = self.analyzer.analyze(text=text, language="pl")
        return [
            {"value": text[r.start:r.end], "label": r.entity_type} 
            for r in results
        ]

    def mask_text(self, text: str, pii_entities: List[Dict[str, str]]) -> tuple[str, Dict[str, str]]:
        """
        Maskuje tekst używając mapy pii_entities. 
        Uwaga: W tej wersji upraszczamy do mapowania ręcznego lub używamy operatorów Presidio.
        """
        # Implementacja zorientowana na tagi [ETYKIETA_ID]
        vault = {}
        masked_text = text
        
        # Sortujemy od najdłuższych, aby uniknąć błędów przy zagnieżdżonych frazach
        sorted_entities = sorted(pii_entities, key=lambda x: len(x["value"]), reverse=True)
        
        for i, entity in enumerate(sorted_entities):
            val = entity["value"]
            label = entity["label"]
            token = f"[{label}_{i}]"
            vault[token] = val
            masked_text = masked_text.replace(val, token)
            
        return masked_text, vault

    def de_identify(self, text: str, vault: Dict[str, str]) -> str:
        """Przywraca oryginalne wartości na podstawie skarbca."""
        result = text
        for token, original in vault.items():
            result = result.replace(token, original)
        return result
