import re
import logging
from typing import List, Dict, Any
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from presidio_analyzer import RecognizerResult
from src.app.domain.ports import IMaskingService

class PresidioMaskingService(IMaskingService):
    """
    Implementation of the PII masking service using Microsoft Presidio Anonymizer.
    
    This service takes already identified and labeled PII entities and applies
    pseudonymization to the text, ensuring that overlapping or nested entities
    are handled correctly by the Presidio engine.
    """

    def __init__(self):
        """Initializes the Presidio Anonymizer engine."""
        self.engine = AnonymizerEngine()

    def _get_analyzer_results(self, text: str, pii_entities: List[Dict[str, str]]) -> List[RecognizerResult]:
        """
        Maps labeled PII entities to Presidio RecognizerResult objects by searching for their occurrences.
        
        Args:
            text: The text to search in.
            pii_entities: List of entities with 'value' and 'label'.
            
        Returns:
            List of RecognizerResult objects.
        """
        results = []
        for idx, ent in enumerate(pii_entities):
            val = ent["value"]
            lbl = ent["label"]
            # Find all occurrences of the PII value in the text
            for match in re.finditer(re.escape(val), text):
                results.append(RecognizerResult(
                    entity_type=f"{lbl}_{idx}", # Use unique type per entity instance to maintain ID
                    start=match.start(),
                    end=match.end(),
                    score=1.0
                ))
        return results

    def mask(self, context: str, query: str, entities: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Pseudonymizes both the context and the query using the provided entities.
        
        Args:
            context: The raw context string (e.g., XML).
            query: The user's original query.
            entities: List of identified and labeled PII entities.
            
        Returns:
            A dictionary containing:
            - masked_context: The pseudonymized context.
            - masked_query: The pseudonymized query.
            - vault: A mapping of tokens (e.g., [PERSON_0]) to original values.
        """
        if not entities:
            return {
                "masked_context": context,
                "masked_query": query,
                "vault": {}
            }

        # 1. Prepare analyzer results for Presidio engine
        context_results = self._get_analyzer_results(context, entities)
        query_results = self._get_analyzer_results(query, entities)
        
        # 2. Define operators for each entity to replace them with tokens like [LABEL_ID]
        operators = {}
        for idx, ent in enumerate(entities):
            lbl = ent["label"].upper()
            operators[f"{ent['label']}_{idx}"] = OperatorConfig(
                "replace", 
                {"new_value": f"[{lbl}_{idx}]"}
            )

        # 3. Anonymize context and query
        anonymized_context = self.engine.anonymize(
            text=context,
            analyzer_results=context_results,
            operators=operators
        )
        
        anonymized_query = self.engine.anonymize(
            text=query,
            analyzer_results=query_results,
            operators=operators
        )
        
        # 4. Build the vault for re-identification later
        vault = {}
        for idx, ent in enumerate(entities):
            token = f"[{ent['label'].upper()}_{idx}]"
            vault[token] = ent["value"]

        return {
            "masked_context": anonymized_context.text, 
            "masked_query": anonymized_query.text, 
            "vault": vault
        }
