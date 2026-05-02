from typing import List, Dict, Optional, Any, Type, TypeVar
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

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

T = TypeVar("T", bound=BaseModel)

# Robust retry configuration for rate-limited providers like Replicate
# (Wait 2^x * 2s between attempts, stop after 3 attempts)
replicate_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    # We use a broad Exception here but could narrow it down to ReplicateError if needed
    reraise=True
)

class LangChainService(ILLMService):
    """Generic implementation of the LLM service using LangChain.
    
    Handles multi-provider routing and provides a standardized way to extract
    structured data, with an automatic fallback and retry mechanism for 
    rate-limited or non-native models.
    """
    
    def __init__(self) -> None:
        """Initializes the service with a dynamic model factory."""
        from src.app.infrastructure.llm.factory import get_model
        self.get_model = get_model

    def _get_structured_chain(self, llm: Any, pydantic_class: Type[T], prompt_template: Any) -> Any:
        """Generic helper to create a structured output chain."""
        try:
            # 1. Try native provider support (Gemini, Ollama)
            return prompt_template | llm.with_structured_output(pydantic_class)
        except (NotImplementedError, AttributeError):
            # 2. Generic Fallback (Replicate, legacy models)
            from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
            parser = PydanticOutputParser(pydantic_object=pydantic_class)
            format_instructions = parser.get_format_instructions().replace("{", "{{").replace("}", "}}")
            
            if isinstance(prompt_template, ChatPromptTemplate):
                messages = []
                for m in prompt_template.messages:
                    if isinstance(m, tuple) and m[0] == "human":
                        messages.append(("human", m[1] + "\n\n" + format_instructions))
                    elif hasattr(m, "content") and m.__class__.__name__ == "HumanMessage":
                        messages.append(("human", m.content + "\n\n" + format_instructions))
                    else:
                        messages.append(m)
                new_prompt = ChatPromptTemplate.from_messages(messages)
            elif isinstance(prompt_template, PromptTemplate):
                new_prompt = PromptTemplate.from_template(prompt_template.template + "\n\n" + format_instructions)
            else:
                new_prompt = PromptTemplate.from_template(str(prompt_template) + "\n\n" + format_instructions)
                
            return new_prompt | llm | parser

    @replicate_retry
    async def analyze_pii(self, text: str, model_name: str, candidates: Optional[List[str]] = None) -> List[str]:
        """Identifies PII strings in text. Uses retries for rate-limited models."""
        llm = self.get_model(model_name=model_name, temperature=0.0)
        
        if candidates is not None:
            prompt_template = DETECTION_PROMPT_HYBRID
            input_data = {"text": text, "candidates": ", ".join(candidates) if candidates else "None"}
        else:
            prompt_template = PromptTemplate.from_template(DETECTION_SYSTEM_LLM_ONLY + "\n\nTEXT TO ANALYZE: {text}")
            input_data = {"text": text}
            
        chain = self._get_structured_chain(llm, PIIData, prompt_template)
        result: PIIData = await chain.ainvoke(input_data)
        return result.detected_strings if result else []

    @replicate_retry
    async def adjudicate_entities(self, text: str, entities: List[RecognizedEntity], model_name: str) -> tuple[List[str], Dict[str, str]]:
        """Performs semantic adjudication. Uses retries for rate-limited models."""
        if not entities: return [], {}
        llm = self.get_model(model_name=model_name, temperature=0.0)
        candidates_str = "\n".join([f"- {e.value} (Type: {e.label})" for e in entities])
        
        # We use a custom parser approach for better robustness with Bielik/Replicate
        from langchain_core.output_parsers import PydanticOutputParser
        parser = PydanticOutputParser(pydantic_object=MultiAdjudicationResult)
        
        prompt = JUDGE_BATCH_PROMPT.format(text=text, candidates=candidates_str)
        
        try:
            # Get raw response first to allow for manual cleaning if needed
            raw_response = await llm.ainvoke(prompt)
            content = str(raw_response.content if hasattr(raw_response, 'content') else raw_response)
            
            # Clean markdown code blocks if present (common in Cloud LLMs)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            # Attempt to parse using the standard LangChain parser
            result = parser.parse(content)
            
            return [v.original_value for v in result.verdicts if v.is_pii], {v.original_value: v.reasoning for v in result.verdicts}
            
        except Exception as e:
            if "429" in str(e) or "throttled" in str(e).lower():
                raise e
            print(f"[ERROR: ADJUDICATION] Failed to process {model_name}: {e}")
            # Fallback: assume everything is PII to be safe
            return [e.value for e in entities], {"error": str(e)}

    @replicate_retry
    async def label_pii(self, pii_strings: List[str], model_name: str) -> List[PIIEntity]:
        """Classifies PII strings. Uses retries for rate-limited models."""
        if not pii_strings: return []
        llm = self.get_model(model_name=model_name, temperature=0.0)
        chain = self._get_structured_chain(llm, LabelingData, LABELING_PROMPT)
        result: LabelingData = await chain.ainvoke({
            "context": "PII Labeling Context",
            "pii_list": ", ".join(pii_strings)
        })
        return result.entities if result else []

    async def verify_security(self, query: str, threshold: float) -> bool: return True

    @replicate_retry
    async def generate_response(self, context: str, query: str, model_name: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Generates a final response. Uses retries for rate-limited models."""
        llm = self.get_model(model_name=model_name, temperature=0.2)
        messages = [
            SystemMessage(content=CLOUD_SYSTEM_PROMPT),
            *(history if history else []),
            HumanMessage(content=CLOUD_USER_PROMPT.format(context=context, query=query))
        ]
        
        if isinstance(llm, BaseChatModel):
            response = await llm.ainvoke(messages)
            content = str(response.content)
        else:
            prompt = "\n".join([f"{m.type}: {m.content}" for m in messages])
            content = str(await llm.ainvoke(prompt))
            
        return {
            "answer": content, 
            "debug_prompt": f"System: {CLOUD_SYSTEM_PROMPT[:100]}...\nUser: {CLOUD_USER_PROMPT.format(context='...', query=query)}", 
            "warnings": []
        }
