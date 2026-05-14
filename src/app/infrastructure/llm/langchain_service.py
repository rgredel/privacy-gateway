import logging
import json
from typing import List, Dict, Optional, Any, Type, TypeVar
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser, JsonOutputParser
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from src.app.domain.ports import ILLMService
from src.app.domain.entities import PIIData, PIIEntity, LabelingData, RecognizedEntity, MultiAdjudicationResult
from src.app.infrastructure.llm.prompts import (
    DETECTION_PROMPT_HYBRID, 
    DETECTION_SYSTEM_LLM_ONLY,
    LABELING_PROMPT,
    CLOUD_SYSTEM_PROMPT,
    CLOUD_USER_PROMPT,
    JUDGE_BATCH_PROMPT,
    TEXT_MARKER_START,
    TEXT_MARKER_END
)

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

# Retry configuration for rate-limited providers
replicate_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    reraise=True
)

class LangChainService(ILLMService):
    """Refactored LangChainService with enhanced logging and robust structured output."""
    
    def __init__(self, local_llm: Optional[Any] = None, cloud_llm: Optional[Any] = None) -> None:
        from src.app.infrastructure.llm.factory import get_model
        self.get_model = get_model
        self.local_llm = local_llm
        self.cloud_llm = cloud_llm

    def _get_structured_chain(self, llm: Any, pydantic_class: Type[T], prompt_template: Any) -> Any:
        """Creates a chain with raw response logging for diagnostics."""
        
        def log_raw_response(msg: Any) -> Any:
            content = msg.content if hasattr(msg, 'content') else str(msg)
            # Log first 500 chars of the raw response
            logger.info(f"[DEBUG LLM RAW] Model: {getattr(llm, 'model_name', 'unknown')} | Response: {content[:500]}")
            return msg

        # Logic for native vs fallback parsing
        try:
            # Native support (Gemini, Ollama)
            structured_llm = llm.with_structured_output(pydantic_class)
            return prompt_template | RunnableLambda(log_raw_response) | structured_llm
        except (NotImplementedError, AttributeError):
            # Fallback (Replicate, legacy)
            parser = PydanticOutputParser(pydantic_object=pydantic_class)
            return prompt_template | llm | RunnableLambda(log_raw_response) | parser

    @replicate_retry
    async def analyze_pii(self, text: str, model_name: str, candidates: Optional[List[str]] = None) -> List[str]:
        llm = self.local_llm if self.local_llm else self.get_model(model_name=model_name, temperature=0.0)
        
        if candidates is not None:
            prompt_template = DETECTION_PROMPT_HYBRID
            input_data = {"text": text, "candidates": ", ".join(candidates) if candidates else "None"}
        else:
            prompt_template = ChatPromptTemplate.from_messages([
                ("system", DETECTION_SYSTEM_LLM_ONLY),
                ("human", f"TEKST DO ANALIZY:\n{TEXT_MARKER_START}\n{{text}}\n{TEXT_MARKER_END}\n\nZWRÓĆ TYLKO LISTĘ JSON:")
            ])
            input_data = {"text": text}
            
        chain = self._get_structured_chain(llm, PIIData, prompt_template)
        try:
            result: PIIData = await chain.ainvoke(input_data)
            return result.detected_strings if result else []
        except Exception as e:
            logger.error(f"[ERROR: ANALYZE] {e}")
            return []

    @replicate_retry
    async def adjudicate_entities(self, text: str, entities: List[RecognizedEntity], model_name: str) -> tuple[List[str], Dict[str, str]]:
        if not entities: return [], {}
        llm = self.cloud_llm if self.cloud_llm else self.get_model(model_name=model_name, temperature=0.0)
        candidates_str = "\n".join([f"- {e.value} (Type: {e.label})" for e in entities])
        
        chain = self._get_structured_chain(llm, MultiAdjudicationResult, JUDGE_BATCH_PROMPT)
        
        try:
            result: MultiAdjudicationResult = await chain.ainvoke({"text": text, "candidates": candidates_str})
            return [v.original_value for v in result.verdicts if v.is_pii], {v.original_value: v.reasoning for v in result.verdicts}
        except Exception as e:
            logger.error(f"[ERROR: ADJUDICATION] {e}")
            return [e.value for e in entities], {"error": str(e)}

    @replicate_retry
    async def label_pii(self, pii_strings: List[str], model_name: str) -> List[PIIEntity]:
        if not pii_strings: return []
        llm = self.cloud_llm if self.cloud_llm else self.get_model(model_name=model_name, temperature=0.0)
        chain = self._get_structured_chain(llm, LabelingData, LABELING_PROMPT)
        try:
            result: LabelingData = await chain.ainvoke({"pii_list": ", ".join(pii_strings)})
            return result.entities if result else []
        except Exception as e:
            logger.error(f"[ERROR: LABELING] {e}")
            return []

    async def verify_security(self, query: str, threshold: float) -> bool:
        return True

    @replicate_retry
    async def generate_response(self, context: str, query: str, model_name: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
        llm = self.cloud_llm if self.cloud_llm else self.get_model(model_name=model_name, temperature=0.2)
        messages = [
            SystemMessage(content=CLOUD_SYSTEM_PROMPT),
            *(history if history else []),
            HumanMessage(content=CLOUD_USER_PROMPT.format(context=context, query=query))
        ]
        
        response = await llm.ainvoke(messages)
        content = response.content if hasattr(response, 'content') else str(response)
            
        return {
            "answer": content, 
            "debug_prompt": f"System: {CLOUD_SYSTEM_PROMPT[:100]}...\nUser: {CLOUD_USER_PROMPT.format(context='...', query=query)}", 
            "warnings": []
        }
