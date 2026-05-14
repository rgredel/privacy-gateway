import logging
from typing import List, Literal, Optional
from src.app.domain.ports import ILLMService
from src.app.domain.entities import PIIEntity

logger = logging.getLogger(__name__)

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

    async def execute(self, pii_strings: List[str], model_name: Optional[str] = None) -> List[PIIEntity]:
        """Classifies the given PII strings.
        
        Args:
            pii_strings (List[str]): Verified PII values to be labeled.
            model_name (Optional[str]): Identifier of the LLM model to use. Defaults to cloud_model_default.
            
        Returns:
            List[PIIEntity]: A list of structured PII entities.
        """
        from src.app.core.config import settings
        m_name = model_name or settings.cloud_model_default
        
        if not pii_strings:
            return []
            
        try:
            logger.info(f"Labeling {len(pii_strings)} PII strings using model {m_name}")
            return await self.llm_service.label_pii(pii_strings, model_name=m_name)
        except Exception as e:
            logger.error(f"Error during PII labeling: {e}", exc_info=True)
            # Depending on business logic, we might want to return empty or re-raise
            # Here we re-raise to let the caller handle the failure
            raise
