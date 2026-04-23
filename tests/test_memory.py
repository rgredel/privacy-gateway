import uuid
import pytest
from langchain_core.messages import HumanMessage, AIMessage
from privacy_gateway import build_graph
from langgraph.checkpoint.memory import MemorySaver

def test_graph_memory_logic(mocker):
    """
    Test weryfikujący logikę pamięci w grafie bez użycia problematycznych mocków 
    wewnątrz stanu LangGraph.
    """
    # Patchujemy tam, gdzie symbole są używane (w privacy_gateway)
    mocker.patch("privacy_gateway.cloud_llm", side_effect=lambda state: {
        "cloud_response": "AI Answer",
        "messages": [HumanMessage(content=state.get("masked_query", "query")), 
                     AIMessage(content="AI Answer")]
    })
    mocker.patch("privacy_gateway.guardrail_agent", return_value={"is_safe": True})
    mocker.patch("privacy_gateway.retrieval_agent", return_value={})
    mocker.patch("privacy_gateway.privacy_wrapper_agent", return_value={
        "masked_context": "Safe Context",
        "masked_query": "Safe Query",
        "vault": {}
    })

    # Budujemy graf z checkpointerem
    app = build_graph(checkpointer=MemorySaver())
    thread_id = "test_thread"
    config = {"configurable": {"thread_id": thread_id}}
    
    # Tura 1
    app.invoke({"raw_xml": "X", "user_query": "Q1"}, config=config)
    
    # Tura 2
    res = app.invoke({"raw_xml": "X", "user_query": "Q2"}, config=config)
    
    # Weryfikacja
    messages = res.get("messages", [])
    assert len(messages) == 4
    assert messages[0].content == "Safe Query"
    print("✅ Test logiki pamięci zakończony sukcesem.")
