from typing import List, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.runnables import Runnable
from src.app.domain.ports import IPIILabelingService

class PIIEntity(BaseModel):
    """Represents a single PII entity with its value and classification label."""
    value: str = Field(description="The original PII value from the text")
    label: str = Field(description="The classification label (e.g., PERSON, NIP, ADDRESS)")

class LabelingData(BaseModel):
    """Collection of classified PII entities."""
    entities: List[PIIEntity] = Field(description="List of classified PII entities")

class LangChainPIILabelingService(IPIILabelingService):
    """
    Implementation of the PII labeling service using LangChain and structured output.
    """

    def __init__(self, llm: Any):
        """
        Initializes the service with a specific LLM instance.
        
        Args:
            llm: A LangChain-compatible LLM instance.
        """
        self.llm = llm
        from .prompts import LABELING_PROMPT
        self.chain = LABELING_PROMPT | self.llm.with_structured_output(LabelingData)

    async def label(self, pii_strings: List[str], context: str) -> List[Dict[str, str]]:
        """
        Classifies the provided PII strings based on the given context.
        
        Args:
            pii_strings: List of raw PII strings to classify.
            context: Contextual text to help the model identify entity types.
            
        Returns:
            A list of dictionaries containing 'value' and 'label' for each entity.
        """
        if not pii_strings:
            return []

        try:
            result: LabelingData = await self.chain.ainvoke({
                "context": context,
                "pii_list": ", ".join(pii_strings)
            })
            
            # Create a map for quick lookup, normalizing strings for better matching
            labeled_map = {e.value.strip().lower(): e.label.upper() for e in result.entities}
            
            entities = []
            for pii in pii_strings:
                label = labeled_map.get(pii.strip().lower(), "DANA")
                entities.append({"value": pii, "label": label})
            
            return entities
            
        except Exception as e:
            # Fallback to generic 'DANA' label in case of LLM failure
            # In a production system, we might want to log this to a monitoring service
            return [{"value": p, "label": "DANA"} for p in pii_strings]
