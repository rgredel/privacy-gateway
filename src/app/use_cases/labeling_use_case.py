from typing import List
from src.app.domain.ports import ILLMService
from src.app.domain.entities import PIIEntity

class LabelingUseCase:
    """Use case responsible for categorizing detected PII strings.
    
    This use case takes raw strings and uses an LLM to assign them to 
    domain-specific categories like PERSON, NIP, PESEL, etc.
    """
    
    def __init__(self, llm_service: ILLMService) -> None:
        """Initializes the labeling use case.
        
        Args:
            llm_service (ILLMService): Injected service for LLM operations.
        """
        self.llm_service = llm_service

    async def execute(self, pii_strings: List[str], model_name: str) -> List[PIIEntity]:
        """Classifies the given PII strings.
        
        Args:
            pii_strings (List[str]): Verified PII values to be labeled.
            model_name (str): Identifier of the LLM model to use.
            
        Returns:
            List[PIIEntity]: A list of structured PII entities.
        """
        if not pii_strings:
            return []
            
        return await self.llm_service.label_pii(pii_strings, model_name=model_name)
