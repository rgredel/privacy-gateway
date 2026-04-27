from typing import List, Any, Set
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.app.domain.ports import IPIIDetectionService

class PIIData(BaseModel):
    """Model for structured PII detection output."""
    detected_strings: List[str] = Field(description="List of strings identified as PII or to be removed.")

class LangChainPIIDetectionService(IPIIDetectionService):
    """
    Implementation of PII detection using LangChain with Map-Reduce strategy.
    Supports both LLM-only and Hybrid (Presidio-assisted) detection.
    """

    def __init__(self, llm: Any):
        """
        Initializes the detection service.
        
        Args:
            llm: A LangChain-compatible LLM instance.
        """
        self.llm = llm
        self.structured_llm = self.llm.with_structured_output(PIIData)
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)

    async def detect(self, text: str) -> List[str]:
        """
        Performs LLM-only PII detection on the provided text.
        
        Args:
            text: The text to analyze.
            
        Returns:
            A list of identified raw PII strings.
        """
        from .prompts import DETECTION_SYSTEM_LLM_ONLY
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", DETECTION_SYSTEM_LLM_ONLY),
            ("human", "ANALIZUJ TEKST:\n{text}")
        ])
        
        chain = prompt | self.structured_llm
        chunks = self.text_splitter.split_text(text)
        payloads = [{"text": chunk} for chunk in chunks]
        
        try:
            results = await chain.abatch(payloads, return_exceptions=True)
            aggregated_pii: Set[str] = set()
            for res in results:
                if isinstance(res, Exception): continue
                if res and res.detected_strings:
                    for s in res.detected_strings:
                        aggregated_pii.add(s.strip())
            return list(aggregated_pii)
        except Exception:
            return []

class HybridPIIDetectionService(IPIIDetectionService):
    """
    Hybrid PII detection service that uses Presidio for candidate generation
    and LLM for precision filtering/verification.
    """

    def __init__(self, llm: Any, candidate_generator: Any):
        """
        Initializes the hybrid detection service.
        
        Args:
            llm: A LangChain-compatible LLM instance.
            candidate_generator: A service or function that generates PII candidates (e.g., Presidio).
        """
        self.llm = llm
        self.candidate_generator = candidate_generator
        self.structured_llm = self.llm.with_structured_output(PIIData)
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=150)

    async def detect(self, text: str) -> List[str]:
        """
        Performs hybrid PII detection by filtering Presidio candidates via LLM.
        
        Args:
            text: The text to analyze.
            
        Returns:
            A list of verified raw PII strings.
        """
        candidates = self.candidate_generator(text)
        if not candidates:
            return []

        from .prompts import DETECTION_PROMPT_HYBRID
        prompt = DETECTION_PROMPT_HYBRID

        
        chain = prompt | self.structured_llm
        chunks = self.text_splitter.split_text(text)
        
        payload_list = []
        for chunk in chunks:
            chunk_candidates = [c for c in candidates if c in chunk]
            payload_list.append({
                "text": chunk, 
                "candidates": ", ".join(chunk_candidates) if chunk_candidates else "None"
            })

        try:
            results = await chain.abatch(payload_list, return_exceptions=True)
            aggregated_pii: Set[str] = set()
            for res in results:
                if isinstance(res, Exception): continue
                if res and res.detected_strings:
                    for s in res.detected_strings:
                        if s.strip():
                            aggregated_pii.add(s.strip())
            return list(aggregated_pii)
        except Exception:
            # Fallback to returning all candidates if LLM fails
            return candidates
