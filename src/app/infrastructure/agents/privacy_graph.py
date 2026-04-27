from langgraph.graph import StateGraph, END, START
from typing import Dict, Any

from src.app.domain.entities import GraphState
from src.app.domain.ports import IPrivacyEngine
from src.app.use_cases.detection_use_case import DetectionUseCase
from src.app.use_cases.labeling_use_case import LabelingUseCase
from src.app.use_cases.masking_use_case import MaskingUseCase
from src.app.use_cases.guardrail_use_case import GuardrailUseCase
from src.app.use_cases.cloud_processing_use_case import CloudProcessingUseCase

def create_privacy_graph(
    detection_uc: DetectionUseCase,
    labeling_uc: LabelingUseCase,
    masking_uc: MaskingUseCase,
    guardrail_uc: GuardrailUseCase,
    cloud_uc: CloudProcessingUseCase,
    privacy_engine: IPrivacyEngine
):
    """Factory to create the LangGraph StateGraph with injected use cases.

    Args:
        detection_uc: Use case for PII detection.
        labeling_uc: Use case for PII labeling.
        masking_uc: Use case for text pseudonymization.
        guardrail_uc: Use case for security verification.
        cloud_uc: Use case for cloud LLM processing.
        privacy_engine: Engine for underlying privacy operations (e.g. Presidio).

    Returns:
        Compiled StateGraph: The executable privacy workflow.
    """
    
    workflow = StateGraph(GraphState)

    # --- NODE DEFINITIONS ---

    async def privacy_wrapper_node(state: GraphState) -> Dict[str, Any]:
        """Node for PII detection, labeling, and masking.

        Combines file context and user query, detects PII, and applies masking.
        Returns updated state with masked contents and the PII vault.

        Args:
            state: Current graph state.

        Returns:
            Dict[str, Any]: State updates for PII related fields.
        """
        text = f"{state.file_context}\n{state.user_query}"
        
        # 1. Detection and Labeling
        if state.detection_mode == "ner-only":
            # Direct labels from engine, bypassing LLM for speed
            labeled_entities = privacy_engine.get_labeled_entities(text)
            pii_strings = [e["value"] for e in labeled_entities]
        else:
            # Multi-agent approach with chunking support
            pii_strings = await detection_uc.execute(text, mode=state.detection_mode)
            labeled_entities = await labeling_uc.execute(pii_strings)
        
        # 3. Masking
        masked_query, vault_query = masking_uc.execute(state.user_query, labeled_entities)
        masked_context, vault_context = masking_uc.execute(state.file_context, labeled_entities)
        
        # Merge vaults to ensure all tokens are restorable
        combined_vault = {**vault_context, **vault_query}
        
        return {
            "raw_pii_strings": pii_strings,
            "labeled_pii_entities": labeled_entities,
            "masked_query": masked_query,
            "masked_context": masked_context,
            "vault": combined_vault
        }

    async def guardrail_node(state: GraphState) -> Dict[str, Any]:
        """Node for security verification using PromptGuard.

        Args:
            state: Current graph state.

        Returns:
            Dict[str, Any]: Safety status update.
        """
        is_safe = await guardrail_uc.execute(
            query=state.user_query, 
            threshold=state.guardrail_threshold,
            enabled=state.enable_guardrail
        )
        return {"is_safe": is_safe}

    async def cloud_llm_node(state: GraphState) -> Dict[str, Any]:
        """Node for external cloud LLM processing (Gemini).

        Uses pseudonymized data to preserve privacy.

        Args:
            state: Current graph state.

        Returns:
            Dict[str, Any]: Cloud LLM response and debug info.
        """
        result = await cloud_uc.execute(
            context=state.masked_context,
            query=state.masked_query,
            model_name=state.cloud_model
        )
        return {
            "cloud_response": result["answer"],
            "cloud_query_debug": result["debug_prompt"],
            "privacy_warnings": result["warnings"]
        }

    def sync_node(state: GraphState) -> GraphState:
        """Synchronous node used to wait for parallel branches."""
        return state

    def block_request_node(state: GraphState) -> Dict[str, Any]:
        """Node invoked when a request is blocked by guardrails."""
        return {"final_output": "🛑 SECURITY ERROR: Request blocked by Guardrail Agent."}

    async def re_identification_node(state: GraphState) -> Dict[str, Any]:
        """Node for restoring original PII values in the final response.

        Args:
            state: Current graph state.

        Returns:
            Dict[str, Any]: Final de-identified output.
        """
        result = state.cloud_response
        for token, original in state.vault.items():
            result = result.replace(token, original)
        return {"final_output": result}

    # --- GRAPH CONSTRUCTION ---

    workflow.add_node("privacy_wrapper", privacy_wrapper_node)
    workflow.add_node("guardrail_node", guardrail_node)
    workflow.add_node("sync_node", sync_node)
    workflow.add_node("cloud_llm", cloud_llm_node)
    workflow.add_node("block_request", block_request_node)
    workflow.add_node("re_identification", re_identification_node)

    # Parallel entry points
    workflow.add_edge(START, "privacy_wrapper")
    workflow.add_edge(START, "guardrail_node")
    workflow.add_edge("privacy_wrapper", "sync_node")
    workflow.add_edge("guardrail_node", "sync_node")

    def check_guardrail_condition(state: GraphState):
        """Routing logic based on safety status."""
        return "cloud_llm" if state.is_safe else "blocked"

    workflow.add_conditional_edges(
        "sync_node",
        check_guardrail_condition,
        {"cloud_llm": "cloud_llm", "blocked": "block_request"}
    )

    workflow.add_edge("cloud_llm", "re_identification")
    workflow.add_edge("re_identification", END)
    workflow.add_edge("block_request", END)

    return workflow.compile()
