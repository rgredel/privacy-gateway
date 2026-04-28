from typing import Protocol, List, Dict, Any, Optional
from src.app.domain.entities import GraphState, RecognizedEntity, AdjudicationResult, PIIEntity

class IPIIDetectionService(Protocol):
    """Interface for PII detection services."""
    async def detect(self, text: str) -> List[str]:
        """Identifies raw PII strings in the given text."""
        ...

class IPIILabelingService(Protocol):
    """Interface for PII labeling/classification services."""
    async def label(self, pii_strings: List[str], context: str) -> List[Dict[str, str]]:
        """Classifies raw PII strings into specific categories."""
        ...

class IMaskingService(Protocol):
    """Interface for PII masking (pseudonymization) services."""
    def mask(self, context: str, query: str, entities: List[Dict[str, str]]) -> Dict[str, Any]:
        """Masks PII entities in both context and query."""
        ...

class ISecurityService(Protocol):
    """Interface for security guardrail services."""
    async def verify_query(self, query: str, threshold: float) -> bool:
        """Validates if a query is safe from prompt injection attacks."""
        ...

class IPrivacyEngine(Protocol):
    """Interface for low-level privacy operations (Presidio/Regex)."""
    def get_candidates(self, text: str) -> List[str]:
        ...
    def analyze_detailed(self, text: str) -> List[RecognizedEntity]:
        ...
    def get_labeled_entities(self, text: str) -> List[Dict[str, str]]:
        ...
    def mask_text(self, text: str, pii_entities: List[Dict[str, str]]) -> tuple[str, Dict[str, str]]:
        ...
    def de_identify(self, text: str, vault: Dict[str, str]) -> str:
        ...

class ILLMService(Protocol):
    """Interface for the core LLM orchestration service."""
    async def analyze_pii(self, text: str, candidates: Optional[List[str]] = None) -> List[str]:
        ...
    async def adjudicate_entities(self, text: str, entities: List[RecognizedEntity]) -> List[str]:
        ...
    async def label_pii(self, pii_strings: List[str]) -> List[PIIEntity]:
        ...
    async def verify_security(self, query: str, threshold: float) -> bool:
        ...
    async def generate_response(self, context: str, query: str, model_name: str) -> Dict[str, Any]:
        ...
