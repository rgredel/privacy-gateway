from typing import Annotated, Dict, List, Optional, Any
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages

class PIIEntity(BaseModel):
    """Represents a structured PII entity with its value and label.
    
    Attributes:
        value (str): The original PII string found in text.
        label (str): The category of the PII (e.g., PERSON, EMAIL, PESEL).
    """
    value: str = Field(description="Original PII value")
    label: str = Field(description="Entity label/category")

class PIIData(BaseModel):
    """Wrapper for raw PII strings detected by LLM.
    
    Attributes:
        detected_strings (List[str]): List of strings identified as potential PII.
    """
    detected_strings: List[str] = Field(description="List of strings identified as PII")

class LabelingData(BaseModel):
    """Wrapper for a list of classified PII entities.
    
    Attributes:
        entities (List[PIIEntity]): List of structured PII entities.
    """
    entities: List[PIIEntity] = Field(description="List of classified PII entities")

class RecognizedEntity(BaseModel):
    """Entity recognized by a base NLP engine with its position and confidence."""
    value: str
    label: str
    start: int
    end: int
    score: float
    recognizer: str = Field(default="unknown", description="Name of the recognizer that found the entity")

class AdjudicationResult(BaseModel):
    """Structured output from LLM-as-a-judge semantic adjudication."""
    thought: str = Field(description="Chain-of-thought reasoning")
    is_pii: bool = Field(description="Final verdict whether it is PII")
    score: float = Field(description="Confidence score for the verdict")
    corrected_value: Optional[str] = Field(None, description="Corrected string if boundaries were wrong")

class AdjudicationItem(BaseModel):
    """Represents a single item in a multi-adjudication result."""
    original_value: str = Field(description="The original value being adjudicated")
    is_pii: bool = Field(description="Final verdict")
    reasoning: str = Field(description="Brief reason for the decision")

class MultiAdjudicationResult(BaseModel):
    """Batch output from LLM-as-a-judge for multiple entities."""
    thought: str = Field(description="General reasoning for the batch")
    verdicts: List[AdjudicationItem] = Field(description="List of verdicts for each item")


class GraphState(BaseModel):
    """
    Represents the state of the Privacy Gateway conversation graph.
    
    Attributes:
        messages: Conversation history with automatic message merging.
        file_context: Input file content used for RAG context.
        user_query: The original question asked by the user.
        raw_pii_strings: List of raw strings identified as PII during detection.
        labeled_pii_entities: Structured PII entities with labels and values.
        masked_context: The context text after pseudonymization.
        masked_query: The user query after pseudonymization.
        vault: A mapping from tokens to original PII values.
        is_safe: Whether the request passed the Guardrail security check.
        cloud_response: The response received from the external cloud LLM.
        final_output: The decoded final response presented to the user.
        error_status: Description of any errors encountered during processing.
        enable_guardrail: Flag to activate or deactivate the Guardrail Agent.
        guardrail_threshold: Sensitivity threshold for PromptGuard (0.0 to 1.0).
        detection_mode: Selected detection method ('hybrid', 'llm-only', or 'ner-only').
        show_debug: Flag to enable or disable debug logging.
        cloud_query_debug: The full prompt sent to the cloud model for debugging.
        privacy_warnings: List of warnings regarding potential PII leaks.
        cloud_model: Identifier of the selected cloud LLM model.
        local_model: Identifier of the selected local LLM model.
    """
    messages: Annotated[list, add_messages] = Field(default_factory=list)
    file_context: str = Field(default="", description="Input file content for RAG context")
    user_query: str = Field(default="", description="Original user query")
    raw_pii_strings: List[str] = Field(default_factory=list, description="Raw detected PII strings")
    labeled_pii_entities: List[PIIEntity] = Field(default_factory=list, description="Labeled PII entities")
    masked_context: str = Field(default="", description="Pseudonymized context")
    masked_query: str = Field(default="", description="Pseudonymized query")
    vault: Dict[str, str] = Field(default_factory=dict, description="PII Token -> Original value mapping")
    is_safe: bool = Field(default=False, description="Guardrail safety status")
    cloud_response: str = Field(default="", description="Response from cloud LLM")
    final_output: str = Field(default="", description="Final decoded output")
    error_status: str = Field(default="", description="Error status message")
    
    # Configuration
    enable_guardrail: bool = Field(default=True)
    guardrail_threshold: float = Field(default=0.85)
    detection_mode: str = Field(default="hybrid")
    show_debug: bool = Field(default=False)
    cloud_query_debug: str = Field(default="")
    detection_debug: List[str] = Field(default_factory=list, description="Detailed logs from the detection pipeline")
    privacy_warnings: List[str] = Field(default_factory=list)
    cloud_model: str = Field(default="gemini-2.0-flash")
    local_model: str = Field(default="bielik-1.5b")

    class Config:
        arbitrary_types_allowed = True
