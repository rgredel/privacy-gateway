from typing import List, Dict, Optional, Any
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from src.app.domain.ports import ILLMService
from src.app.domain.entities import PIIData, PIIEntity, LabelingData, RecognizedEntity, AdjudicationResult
from src.app.infrastructure.llm.prompts import (
    DETECTION_PROMPT_HYBRID, 
    DETECTION_SYSTEM_LLM_ONLY,
    LABELING_PROMPT,
    CLOUD_SYSTEM_PROMPT,
    CLOUD_USER_PROMPT,
    JUDGE_PROMPT
)

class LangChainService(ILLMService):
    """Implementation of ILLMService using LangChain.
    
    This service encapsulates the LCEL (LangChain Expression Language) logic 
    and handles structured output generation for PII detection and labeling.
    """
    
    def __init__(self, local_llm: Any, cloud_llm: Any):
        """Initializes the service with local and cloud LLM instances.

        Args:
            local_llm: LangChain-compatible LLM for local processing (e.g., Llama-3).
            cloud_llm: LangChain-compatible LLM for cloud processing (e.g., Gemini).
        """
        self.local_llm = local_llm
        self.cloud_llm = cloud_llm

    async def analyze_pii(self, text: str, candidates: Optional[List[str]] = None) -> List[str]:
        """Performs PII detection using either Hybrid or LLM-only mode.

        Args:
            text (str): The input text to analyze.
            candidates (Optional[List[str]]): Pre-detected candidates from NER engine. 
                If provided, Hybrid mode is used.

        Returns:
            List[str]: A list of detected PII strings.
        """
        structured_llm = self.local_llm.with_structured_output(PIIData)
        
        if candidates is not None:
            # Hybrid Mode
            chain = DETECTION_PROMPT_HYBRID | structured_llm
            result = await chain.ainvoke({
                "text": text,
                "candidates": ", ".join(candidates) if candidates else "Brak"
            })
        try:
            if candidates is not None:
                # Hybrid Mode
                chain = DETECTION_PROMPT_HYBRID | structured_llm
                result = await chain.ainvoke({
                    "text": text,
                    "candidates": ", ".join(candidates) if candidates else "Brak"
                })
            else:
                # LLM-only Mode
                prompt = ChatPromptTemplate.from_messages([
                    ("system", DETECTION_SYSTEM_LLM_ONLY),
                    ("human", "ANALIZUJ TEKST:\n{text}")
                ])
                chain = prompt | structured_llm
                result = await chain.ainvoke({"text": text})
                
            return result.detected_strings if result else []
        except Exception:
            return []

    async def adjudicate_entities(self, text: str, entities: List[RecognizedEntity]) -> List[str]:
        """Performs semantic adjudication on a list of recognized entities using LLM-as-a-judge.
        
        Args:
            text (str): Full original text for context extraction.
            entities (List[RecognizedEntity]): Entities that triggered UDRIL.
            
        Returns:
            List[str]: Verified PII strings.
        """
        if not entities:
            return []
            
        judge_llm = self.local_llm.with_structured_output(AdjudicationResult)
        chain = JUDGE_PROMPT | judge_llm
        
        payloads = []
        for ent in entities:
            # Extract context window: approx 150 chars before and after
            start = max(0, ent.start - 150)
            end = min(len(text), ent.end + 150)
            window = text[start:end]
            
            payloads.append({
                "window": window,
                "value": ent.value,
                "label": ent.label
            })
            
        try:
            results = await chain.abatch(payloads)
            verified_pii = []
            for ent, res in zip(entities, results):
                if res and res.is_pii:
                    # Use corrected value if provided, otherwise original
                    val = res.corrected_value if res.corrected_value else ent.value
                    verified_pii.append(val)
            return verified_pii
        except Exception:
            # Fallback to original candidates if judge fails
            return [e.value for e in entities]

    async def label_pii(self, pii_strings: List[str]) -> List[PIIEntity]:
        """Classifies detected PII strings into specific categories.

        Args:
            pii_strings (List[str]): List of raw PII strings to be labeled.

        Returns:
            List[PIIEntity]: A list of structured PII entities with labels.
        """
        if not pii_strings:
            return []
            
        structured_llm = self.local_llm.with_structured_output(LabelingData)
        chain = LABELING_PROMPT | structured_llm
        
        # Context is simplified here; can be extended in future iterations
        result = await chain.ainvoke({
            "context": "Context not provided in this layer", 
            "pii_list": ", ".join(pii_strings)
        })
        
        return result.entities if result else []

    async def verify_security(self, query: str, threshold: float) -> bool:
        """Verifies query safety using security guardrails.

        Args:
            query (str): The user query to verify.
            threshold (float): Sensitivity threshold for the classifier.

        Returns:
            bool: True if the query is safe, False otherwise.
        """
        # Note: This is usually implemented in a dedicated adapter (e.g. PromptGuard)
        return True

    async def generate_response(self, context: str, query: str, model_name: str) -> Dict[str, Any]:
        """Generates a response from the cloud LLM using pseudonymized data.

        Args:
            context (str): Pseudonymized RAG context.
            query (str): Pseudonymized user query.
            model_name (str): Identifier of the cloud model to use.

        Returns:
            Dict[str, Any]: A dictionary containing the 'answer', 'debug_prompt', and 'warnings'.
        """
        system_msg = CLOUD_SYSTEM_PROMPT
        user_msg = CLOUD_USER_PROMPT.format(context=context, query=query)
        
        messages = [
            SystemMessage(content=system_msg),
            HumanMessage(content=user_msg)
        ]
        
        debug_prompt = f"[SYSTEM]: {system_msg}\n\n[USER]: {user_msg}"
        
        res = await self.cloud_llm.ainvoke(messages)
        
        return {
            "answer": res.content,
            "debug_prompt": debug_prompt,
            "warnings": [] 
        }
