from typing import Protocol, List, Dict, Any, Optional
from src.app.domain.entities import GraphState, RecognizedEntity, AdjudicationResult, PIIEntity

class IPIIDetectionService(Protocol):
    """Interface for PII detection services."""
    async def detect(self, text: str) -> List[str]:
        """Identifies raw PII strings in the given text.
        
        Args:
            text (str): The input text to analyze.
            
        Returns:
            List[str]: A list of identified PII strings.
        """
        ...

class IPIILabelingService(Protocol):
    """Interface for PII labeling/classification services."""
    async def label(self, pii_strings: List[str], context: str) -> List[PIIEntity]:
        """Classifies raw PII strings into specific categories.
        
        Args:
            pii_strings (List[str]): List of identified PII values.
            context (str): The surrounding text for better classification.
            
        Returns:
            List[PIIEntity]: A list of structured PII entities with labels.
        """
        ...

class IMaskingService(Protocol):
    """Interface for PII masking (pseudonymization) services."""
    def mask(self, context: str, query: str, entities: List[PIIEntity]) -> Dict[str, Any]:
        """Masks PII entities in both context and query.
        
        Args:
            context (str): The background text to mask.
            query (str): The user query to mask.
            entities (List[PIIEntity]): List of entities to be replaced with tokens.
            
        Returns:
            Dict[str, Any]: A dictionary containing masked_context, masked_query, and vault.
        """
        ...

class ISecurityService(Protocol):
    """Interface for security guardrail services."""
    async def verify_query(self, query: str, threshold: float) -> bool:
        """Validates if a query is safe from prompt injection attacks.
        
        Args:
            query (str): The user input to verify.
            threshold (float): Sensitivity threshold for detection.
            
        Returns:
            bool: True if safe, False if malicious.
        """
        ...

class IPrivacyEngine(Protocol):
    """Interface for low-level privacy operations (e.g., Presidio, Regex)."""
    def get_candidates(self, text: str) -> List[str]:
        """Gets potential PII strings using NER engines.
        
        Args:
            text (str): Input text.
            
        Returns:
            List[str]: List of candidate strings.
        """
        ...
        
    def analyze_detailed(self, text: str) -> List[RecognizedEntity]:
        """Performs detailed NER analysis with confidence scores.
        
        Args:
            text (str): Input text.
            
        Returns:
            List[RecognizedEntity]: List of entities with positions and scores.
        """
        ...
        
    def get_labeled_entities(self, text: str) -> List[PIIEntity]:
        """Directly classifies PII in text using the local engine.
        
        Args:
            text (str): Input text.
            
        Returns:
            List[PIIEntity]: List of labeled entities.
        """
        ...
        
    def mask_text(self, text: str, pii_entities: List[PIIEntity]) -> tuple[str, Dict[str, str]]:
        """Replaces PII values with tokens and returns a vault.
        
        Args:
            text (str): Original text.
            pii_entities (List[PIIEntity]): Entities to mask.
            
        Returns:
            tuple[str, Dict[str, str]]: (Masked text, Token -> Original mapping).
        """
        ...
        
    def de_identify(self, text: str, vault: Dict[str, str]) -> str:
        """Restores original values from tokens using the vault.
        
        Args:
            text (str): Masked text.
            vault (Dict[str, str]): Token -> Original mapping.
            
        Returns:
            str: De-identified text.
        """
        ...

class ILLMService(Protocol):
    """Interface for the core LLM orchestration service."""
    async def analyze_pii(self, text: str, model_name: str, candidates: Optional[List[str]] = None) -> List[str]:
        """Identifies PII strings using LLM semantic analysis.
        
        Args:
            text (str): Input text.
            model_name (str): Identifier of the LLM to use.
            candidates (Optional[List[str]]): NER candidates for filtering.
            
        Returns:
            List[str]: Verified PII strings.
        """
        ...
        
    async def adjudicate_entities(self, text: str, entities: List[RecognizedEntity], model_name: str) -> tuple[List[str], Dict[str, str]]:
        """Performs batch semantic adjudication on NER entities.
        
        Args:
            text (str): Original text.
            entities (List[RecognizedEntity]): Candidate entities from NER.
            model_name (str): Identifier of the LLM to use.
            
        Returns:
            tuple[List[str], Dict[str, str]]: (Verified PII strings, Reasoning logs).
        """
        ...
        
    async def label_pii(self, pii_strings: List[str], model_name: str) -> List[PIIEntity]:
        """Classifies PII strings into domain categories using LLM.
        
        Args:
            pii_strings (List[str]): Verified PII values.
            model_name (str): Identifier of the LLM to use.
            
        Returns:
            List[PIIEntity]: Labeled PII entities.
        """
        ...
        
    async def verify_security(self, query: str, threshold: float) -> bool:
        """Checks query for malicious intent using security guardrails.
        
        Args:
            query (str): User input.
            threshold (float): Sensitivity threshold.
            
        Returns:
            bool: Safety status.
        """
        ...
        
    async def generate_response(self, context: str, query: str, model_name: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Generates a final response based on masked context and query.
        
        Args:
            context (str): Masked RAG context.
            query (str): Masked user query.
            model_name (str): Cloud model to use.
            history (Optional[List[Any]]): Conversation history.
            
        Returns:
            Dict[str, Any]: Response data including answer and debug logs.
        """
        ...
