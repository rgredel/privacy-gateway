from src.app.core.config import settings
from src.app.infrastructure.llm.langchain_service import LangChainService
from src.app.infrastructure.services.presidio_service import PresidioService
from src.app.infrastructure.services.prompt_guard_service import PromptGuardService
# Prompty są już wewnątrz LangChainService, ale można je tu wstrzyknąć jeśli trzeba

from src.app.use_cases.detection_use_case import DetectionUseCase
from src.app.use_cases.labeling_use_case import LabelingUseCase
from src.app.use_cases.masking_use_case import MaskingUseCase
from src.app.use_cases.guardrail_use_case import GuardrailUseCase
from src.app.use_cases.cloud_processing_use_case import CloudProcessingUseCase

from src.app.infrastructure.agents.privacy_graph import create_privacy_graph

def bootstrap_app():
    """Initializes all components and returns the compiled Privacy Graph.
    
    This function handles Dependency Injection (DI) by wiring infrastructure
    adapters to application use cases.
    """
    
    # 1. Infrastruktura (Adaptery)
    from src.app.infrastructure.llm.factory import get_local_model, get_cloud_gemini_2_5_flash, get_prompt_guard_classifier, translate_pl_to_en
    from src.app.infrastructure.services.presidio_factory import setup_presidio_analyzer
    
    local_llm = get_local_model(model_name=settings.local_model_default)
    cloud_llm = get_cloud_gemini_2_5_flash(model_name=settings.cloud_model_default)
    
    llm_service = LangChainService(local_llm=local_llm, cloud_llm=cloud_llm)
    
    analyzer = setup_presidio_analyzer()
    privacy_engine = PresidioService(analyzer=analyzer)
    
    classifier = get_prompt_guard_classifier()
    security_service = PromptGuardService(classifier=classifier, translator=translate_pl_to_en)
    
    # 2. Use Cases
    detection_uc = DetectionUseCase(llm_service=llm_service, privacy_engine=privacy_engine)
    labeling_uc = LabelingUseCase(llm_service=llm_service)
    masking_uc = MaskingUseCase(privacy_engine=privacy_engine)
    guardrail_uc = GuardrailUseCase(security_service=security_service)
    cloud_uc = CloudProcessingUseCase(llm_service=llm_service)
    
    # 3. Graf
    app_graph = create_privacy_graph(
        detection_uc=detection_uc,
        labeling_uc=labeling_uc,
        masking_uc=masking_uc,
        guardrail_uc=guardrail_uc,
        cloud_uc=cloud_uc,
        privacy_engine=privacy_engine
    )
    
    return app_graph

# Globalna instancja grafu
graph = bootstrap_app()
