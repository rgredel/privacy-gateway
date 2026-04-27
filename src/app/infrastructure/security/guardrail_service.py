import logging
from typing import Any, Optional
from src.app.domain.ports import ISecurityService

class PromptGuardService(ISecurityService):
    """
    Implementation of the security guardrail using Meta's PromptGuard-2 model.
    
    This service translates Polish queries to English and then classifies them
    as 'benign' or 'malicious' using a fine-tuned transformer model.
    """

    def __init__(self, classifier: Any, translator: Any):
        """
        Initializes the guardrail service with required components.
        
        Args:
            classifier: A HuggingFace text-classification pipeline for PromptGuard.
            translator: A translator instance (e.g., GoogleTranslator).
        """
        self.classifier = classifier
        self.translator = translator

    async def verify_query(self, query: str, threshold: float = 0.85) -> bool:
        """
        Validates if the user query is safe from prompt injection attacks.
        
        Args:
            query: The user's input query in Polish.
            threshold: Probability threshold for blocking malicious queries.
            
        Returns:
            True if the query is considered safe, False otherwise.
        """
        if not query.strip():
            return True

        try:
            # 1. Translate Polish to English for optimal classification performance
            translated = self.translator.translate(query)
            logging.debug(f"Guardrail translation: '{query[:50]}...' -> '{translated[:50]}...'")

            # 2. Classify the translated text
            results = self.classifier(translated)
            if not results:
                return True
                
            top_result = results[0]
            label = top_result["label"]
            score = top_result["score"]

            # PromptGuard-2 labeling: LABEL_0 = benign, LABEL_1 = malicious
            is_malicious = (label == "LABEL_1" and score > threshold)
            is_safe = not is_malicious

            if not is_safe:
                logging.warning(f"Malicious query detected! Score: {score:.4f}, Label: {label}")
            
            return is_safe

        except Exception as e:
            # Fallback to safe mode on error to avoid disrupting the user experience,
            # but log the failure for security auditing.
            logging.error(f"Guardrail validation failed: {e}")
            return True
