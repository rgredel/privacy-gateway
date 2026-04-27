from typing import Dict, Any, List
from src.app.domain.entities import GraphState
from src.app.domain.ports import IPIIDetectionService, IPIILabelingService, IMaskingService

class ProcessPrivacyUseCase:
    """
    Use case responsible for the end-to-end privacy protection process.
    It coordinates detection, labeling, and masking of PII.
    """

    def __init__(
        self, 
        detection_service: IPIIDetectionService,
        labeling_service: IPIILabelingService,
        masking_service: IMaskingService
    ):
        """
        Initializes the use case with required domain services.
        
        Args:
            detection_service: Service to detect raw PII strings.
            labeling_service: Service to classify detected PII.
            masking_service: Service to pseudonymize the text.
        """
        self.detection_service = detection_service
        self.labeling_service = labeling_service
        self.masking_service = masking_service

    async def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        Executes the privacy protection flow.
        
        Args:
            state: The current state of the graph.
            
        Returns:
            A dictionary with updated state fields (raw_pii_strings, labeled_pii_entities, masked_context, etc.).
        """
        # 1. Detection
        full_text = f"{state.raw_xml}\n{state.user_query}"
        raw_pii = await self.detection_service.detect(full_text)
        
        # 2. Labeling
        labeled_entities = await self.labeling_service.label(raw_pii, full_text)
        
        # 3. Masking
        masking_result = self.masking_service.mask(
            context=state.raw_xml,
            query=state.user_query,
            entities=labeled_entities
        )
        
        return {
            "raw_pii_strings": raw_pii,
            "labeled_pii_entities": labeled_entities,
            **masking_result
        }
