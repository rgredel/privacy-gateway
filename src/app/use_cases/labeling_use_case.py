from typing import List
from src.app.domain.ports import ILLMService
from src.app.domain.entities import PIIEntity

class LabelingUseCase:
    """Use case responsible for labeling and classifying detected PII strings.
    
    Delegates the semantic classification task to the injected LLM service.
    """
    
    def __init__(self, llm_service: ILLMService):
        """Initializes the use case with an LLM service.

        Args:
            llm_service (ILLMService): The service used for semantic labeling.
        """
        self.llm_service = llm_service

    async def execute(self, pii_strings: List[str]) -> List[PIIEntity]:
        """Classifies a list of raw PII strings.

        Args:
            pii_strings (List[str]): List of raw strings identified as PII.

        Returns:
            List[PIIEntity]: A list of structured PII entities with labels.
        """
        if not pii_strings:
            return []
            
        return await self.llm_service.label_pii(pii_strings)
