from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage
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
) -> StateGraph:
    """Factory to create the LangGraph StateGraph with injected use cases.

    This graph coordinates the privacy preservation workflow: guardrails, 
    detection, masking, cloud processing, and re-identification.

    Args:
        detection_uc: Use case for PII detection.
        labeling_uc: Use case for PII labeling.
        masking_uc: Use case for text pseudonymization.
        guardrail_uc: Use case for security verification.
        cloud_uc: Use case for cloud LLM processing.
        privacy_engine: Engine for underlying privacy operations (e.g. Presidio).

    Returns:
        StateGraph: Compiled and executable LangGraph workflow.
    """
    
    workflow = StateGraph(GraphState)

    # --- NODE DEFINITIONS ---

    async def privacy_wrapper_node(state: GraphState) -> Dict[str, Any]:
        """Node for PII detection, labeling, and masking.

        Args:
            state (GraphState): Current conversation state.

        Returns:
            Dict[str, Any]: Updates for state containing masked text and vault.
        """
        text = f"{state.file_context}\n{state.user_query}"
        
        # 1. Detection and Labeling
        if state.detection_mode == "ner-only":
            new_labeled_entities = privacy_engine.get_labeled_entities(text)
            pii_strings = [e.value for e in new_labeled_entities]
            detection_logs = [f"NER-only mode: Found {len(pii_strings)} entities locally."]
        else:
            # 1a. Get detailed entities from NER engine first (to keep labels)
            detailed_ner_entities = privacy_engine.analyze_detailed(text)
            
            # 1b. Use LLM to adjudicate (verify) these entities
            verified_pii_strings, detection_logs = await detection_uc.execute(
                text, 
                mode=state.detection_mode,
                model_name=state.local_model
            )
            
            # 1c. Filter original entities - PRESERVE LABELS from NER
            new_labeled_entities = []
            for ent in detailed_ner_entities:
                if ent.value in verified_pii_strings:
                    new_labeled_entities.append(ent)
                    
            # 1d. Handle entities discovered by LLM that were NOT found by NER (if any)
            ner_values = {e.value for e in detailed_ner_entities}
            missing_pii = [val for val in verified_pii_strings if val not in ner_values]
            
            if missing_pii:
                # Only call labeling for truly new findings
                newly_labeled = await labeling_uc.execute(missing_pii, model_name=state.local_model)
                new_labeled_entities.extend(newly_labeled)
            
            pii_strings = verified_pii_strings
        
        # Merge with existing entities to maintain recall over multiple turns
        all_labeled_entities = state.labeled_pii_entities + new_labeled_entities
        
        # 2. Masking
        masked_query, vault_query = masking_uc.execute(state.user_query, all_labeled_entities)
        masked_context, vault_context = masking_uc.execute(state.file_context, all_labeled_entities, shorten=True)
        
        # Merge vaults
        combined_vault = {**state.vault, **vault_context, **vault_query}
        
        print(f"[DEBUG: GRAPH] PII detection finished. Found {len(pii_strings)} new entities.")
        print(f"[DEBUG: GRAPH] Masked Query: {masked_query[:50]}...")
        
        return {
            "raw_pii_strings": list(set(state.raw_pii_strings + pii_strings)),
            "labeled_pii_entities": all_labeled_entities,
            "masked_query": masked_query,
            "masked_context": masked_context,
            "vault": combined_vault,
            "messages": [HumanMessage(content=masked_query)],
            "detection_debug": detection_logs
        }

    async def guardrail_node(state: GraphState) -> Dict[str, Any]:
        """Node for security verification using PromptGuard.

        Args:
            state (GraphState): Current conversation state.

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
        """Node for external cloud LLM processing."""
        print(f"[DEBUG: GRAPH] Entering Cloud LLM Node with model: {state.cloud_model}")
        result = await cloud_uc.execute(
            context=state.masked_context,
            query=state.masked_query,
            model_name=state.cloud_model,
            history=state.messages
        )
        print(f"[DEBUG: GRAPH] Cloud LLM Response received (len: {len(result['answer'])})")
        return {
            "cloud_response": result["answer"],
            "cloud_query_debug": result["debug_prompt"],
            "privacy_warnings": result["warnings"]
        }

    def sync_node(state: GraphState) -> GraphState:
        """Synchronous node used to wait for parallel branches.
        
        Args:
            state (GraphState): Current conversation state.
            
        Returns:
            GraphState: Unchanged state to allow transition.
        """
        return state

    def block_request_node(state: GraphState) -> Dict[str, Any]:
        """Node invoked when a request is blocked by guardrails.

        Args:
            state (GraphState): Current conversation state.

        Returns:
            Dict[str, Any]: Blocking message.
        """
        return {"final_output": "🛑 SECURITY ERROR: Request blocked by Guardrail Agent."}

    async def re_identification_node(state: GraphState) -> Dict[str, Any]:
        """Node for restoring original PII values in the final response.

        Args:
            state (GraphState): Current conversation state.

        Returns:
            Dict[str, Any]: Final de-identified output.
        """
        result = state.cloud_response
        for token, original in state.vault.items():
            result = result.replace(token, original)
        return {
            "final_output": result,
            "messages": [AIMessage(content=result)]
        }

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

    # Checkpointing for memory support
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)
