from typing import List, Optional
from src.app.domain.ports import ILLMService, IPrivacyEngine

class DetectionUseCase:
    """Use case responsible for identifying PII in mixed-context text.
    
    This use case coordinates multiple detection methods: NER-only, LLM-only, 
    and Hybrid (NER + LLM adjudication).
    """
    
    def __init__(self, llm_service: ILLMService, privacy_engine: IPrivacyEngine) -> None:
        """Initializes the detection use case.
        
        Args:
            llm_service (ILLMService): Injected service for LLM operations.
            privacy_engine (IPrivacyEngine): Injected engine for NER and regex detection.
        """
        self.llm_service = llm_service
        self.privacy_engine = privacy_engine

    async def execute(self, text: str, mode: str = "hybrid", model_name: Optional[str] = None) -> tuple[List[str], List[str]]:
        """Executes the PII detection process based on the selected mode.
        
        Args:
            text (str): The input text to be scanned for PII.
            mode (str): Detection strategy: 'ner-only', 'llm-only', or 'hybrid'.
            model_name (Optional[str]): Identifier of the LLM model. Defaults to local_model_default.
            
        Returns:
            tuple[List[str], List[str]]: (List of detected PII strings, Debug logs).
        """
        from src.app.core.config import settings
        m_name = model_name or settings.local_model_default
        logs = [f"Detection started in '{mode}' mode using model '{m_name}'."]
        
        if mode == "llm-only":
            pii = await self.llm_service.analyze_pii(text, model_name=m_name)
            logs.append(f"LLM-only: Detected {len(pii)} items.")
            return pii, logs
            
        # For hybrid and ner-only, we start with NER
        detailed_entities = self.privacy_engine.analyze_detailed(text)
        logs.append(f"NER: Found {len(detailed_entities)} raw candidates.")
        
        if mode == "ner-only":
            pii = list(set([ent.value for ent in detailed_entities]))
            return pii, logs
            
        # Hybrid Mode: Semantic Adjudication (UDRIL pattern)
        verified_pii, reasonings = await self.llm_service.adjudicate_entities(
            text, 
            detailed_entities, 
            model_name=m_name
        )
        
        for val, reason in reasonings.items():
            status = "✅ APPROVED" if val in verified_pii else "❌ REJECTED"
            logs.append(f"Judge: {val} -> {status} ({reason})")
            
        return verified_pii, logs
