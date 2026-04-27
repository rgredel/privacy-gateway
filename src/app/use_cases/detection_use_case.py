from typing import List, Optional
from src.app.domain.ports import ILLMService, IPrivacyEngine

class DetectionUseCase:
    """Use case responsible for PII detection.
    
    Handles hybrid (NER + LLM) and LLM-only detection modes with chunking support.
    """
    
    def __init__(self, llm_service: ILLMService, privacy_engine: IPrivacyEngine):
        """Initializes the use case with required services.

        Args:
            llm_service: Service for LLM operations.
            privacy_engine: Engine for local NER/Presidio operations.
        """
        self.llm_service = llm_service
        self.privacy_engine = privacy_engine
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=4000, chunk_overlap=200)

    async def execute(self, text: str, mode: str = "hybrid") -> List[str]:
        """Executes the PII detection process with chunking for large texts.

        This method coordinates between NER-only, LLM-only, and Hybrid modes.
        Large texts are split into chunks to fit within model context limits.

        Args:
            text (str): Input text to analyze.
            mode (str): Detection mode ('hybrid', 'llm-only', or 'ner-only'). 
                Defaults to 'hybrid'.

        Returns:
            List[str]: A unique list of raw PII strings found in the text.
        """
        # Small texts are processed in a single pass
        if len(text) < 5000:
            return await self._process_chunk(text, mode)
            
        # Large texts use a Map-Reduce strategy via chunking
        chunks = self.text_splitter.split_text(text)
        all_pii = set()
        
        for chunk in chunks:
            chunk_pii = await self._process_chunk(chunk, mode)
            all_pii.update(chunk_pii)
            
        return list(all_pii)

    async def _process_chunk(self, text: str, mode: str) -> List[str]:
        """Processes a single text chunk based on the selected mode.

        Args:
            text (str): The chunk of text to analyze.
            mode (str): The detection mode to apply.

        Returns:
            List[str]: PII strings found in this chunk.
        """
        if mode == "ner-only":
            return self.privacy_engine.get_candidates(text)
            
        if mode == "llm-only":
            return await self.llm_service.analyze_pii(text)
            
        # Hybrid Mode: Filter candidates via LLM
        candidates = self.privacy_engine.get_candidates(text)
        if not candidates:
            return []
            
        return await self.llm_service.analyze_pii(text, candidates=candidates)
