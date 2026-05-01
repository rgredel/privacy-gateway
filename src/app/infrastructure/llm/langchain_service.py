from typing import List, Dict, Optional, Any
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import PromptTemplate

from src.app.domain.ports import ILLMService
from src.app.domain.entities import PIIData, PIIEntity, LabelingData, RecognizedEntity, MultiAdjudicationResult
from src.app.infrastructure.llm.prompts import (
    DETECTION_PROMPT_HYBRID, 
    DETECTION_SYSTEM_LLM_ONLY,
    LABELING_PROMPT,
    CLOUD_SYSTEM_PROMPT,
    CLOUD_USER_PROMPT,
    JUDGE_BATCH_PROMPT
)

class LangChainService(ILLMService):
    """Implementation of the LLM service using LangChain and multiple model providers.
    
    This service handles PII detection, adjudication, labeling, and response generation
    by orchestrating calls to local (Ollama) or cloud (Gemini) models.
    """
    
    def __init__(self) -> None:
        """Initializes the service. Models are dynamically selected per request via a factory."""
        from src.app.infrastructure.llm.factory import get_model
        self.get_model = get_model

    async def analyze_pii(self, text: str, model_name: str, candidates: Optional[List[str]] = None) -> List[str]:
        """Identifies PII strings in text using a structured LLM prompt.
        
        Args:
            text (str): Input text for analysis.
            model_name (str): Identifier of the LLM to use.
            candidates (Optional[List[str]]): NER-found candidates to help the LLM.
            
        Returns:
            List[str]: A list of verified PII strings.
        """
        llm = self.get_model(model_name=model_name, temperature=0.0)
        structured_llm = llm.with_structured_output(PIIData)
        
        if candidates is not None:
            # Hybrid Mode
            chain = DETECTION_PROMPT_HYBRID | structured_llm
            result: PIIData = await chain.ainvoke({
                "text": text,
                "candidates": ", ".join(candidates) if candidates else "None"
            })
        else:
            # LLM-only Mode
            prompt = (
                DETECTION_SYSTEM_LLM_ONLY + "\n\n" +
                "TEXT TO ANALYZE: {text}"
            )
            chain = PromptTemplate.from_template(prompt) | structured_llm
            result: PIIData = await chain.ainvoke({"text": text})
            
        return result.detected_strings if result else []

    async def adjudicate_entities(self, text: str, entities: List[RecognizedEntity], model_name: str) -> tuple[List[str], Dict[str, str]]:
        """Performs semantic adjudication on multiple NER entities in a single batch.
        
        Args:
            text (str): The full context text.
            entities (List[RecognizedEntity]): Candidate entities from NER engines.
            model_name (str): Identifier of the LLM to use.
            
        Returns:
            tuple[List[str], Dict[str, str]]: (List of approved PII strings, mapping of value to reasoning).
        """
        if not entities:
            return [], {}
            
        llm = self.get_model(model_name=model_name, temperature=0.0)
        structured_llm = llm.with_structured_output(MultiAdjudicationResult)
        
        # Format candidates for the batch prompt
        candidates_list = [f"- {e.value} (Type: {e.label})" for e in entities]
        candidates_str = "\n".join(candidates_list)
        
        chain = JUDGE_BATCH_PROMPT | structured_llm
        
        try:
            result: MultiAdjudicationResult = await chain.ainvoke({
                "text": text,
                "candidates": candidates_str
            })
            
            verified_strings = [v.original_value for v in result.verdicts if v.is_pii]
            reasoning_map = {v.original_value: v.reasoning for v in result.verdicts}
            
            return verified_strings, reasoning_map
        except Exception as e:
            print(f"[ERROR: ADJUDICATION] Batch processing failed: {e}")
            # Fallback: assume all are PII if the judge fails
            return [e.value for e in entities], {"error": str(e)}

    async def label_pii(self, pii_strings: List[str], model_name: str) -> List[PIIEntity]:
        """Classifies verified PII strings into specific domain categories.
        
        Args:
            pii_strings (List[str]): Verified PII values.
            model_name (str): Identifier of the LLM to use.
            
        Returns:
            List[PIIEntity]: A list of structured PII entities.
        """
        if not pii_strings:
            return []
            
        llm = self.get_model(model_name=model_name, temperature=0.0)
        structured_llm = llm.with_structured_output(LabelingData)
        
        chain = LABELING_PROMPT | structured_llm
        
        result: LabelingData = await chain.ainvoke({
            "context": "Context not provided for labeling",
            "pii_list": ", ".join(pii_strings)
        })
        return result.entities if result else []

    async def verify_security(self, query: str, threshold: float) -> bool:
        """Deprecated: Security is now handled by PromptGuardService.
        
        Maintained for interface compatibility.
        """
        return True

    async def generate_response(self, context: str, query: str, model_name: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Generates a final response based on sanitized context and user query.
        
        Args:
            context (str): Masked background context.
            query (str): Masked user query.
            model_name (str): Identifier of the cloud LLM to use.
            history (Optional[List[Any]]): Conversation history messages.
            
        Returns:
            Dict[str, Any]: Contains 'answer', 'debug_prompt', and 'warnings'.
        """
        llm = self.get_model(model_name=model_name, temperature=0.2)
        
        system_prompt = CLOUD_SYSTEM_PROMPT
        user_prompt = CLOUD_USER_PROMPT.format(context=context, query=query)
        
        messages = [
            SystemMessage(content=system_prompt),
            *(history if history else []),
            HumanMessage(content=user_prompt)
        ]
        
        response = await llm.ainvoke(messages)
        content = str(response.content)
        
        # Simple anti-leakage heuristic check
        warnings = []
        if "[BŁĄD BEZPIECZEŃSTWA]" in content:
            warnings.append("Cloud model blocked the response due to suspected prompt injection.")
            
        return {
            "answer": content,
            "debug_prompt": f"System: {system_prompt}\nUser: {user_prompt}",
            "warnings": warnings
        }
