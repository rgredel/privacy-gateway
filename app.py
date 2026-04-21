import asyncio
import chainlit as cl
from state import GraphState
from privacy_gateway import build_graph

@cl.on_chat_start
async def on_chat_start():
    # Inicjalizacja grafu LangGraph pobrana bezposrednio z `privacy_gateway.py`
    app_graph = build_graph()
    cl.user_session.set("app_graph", app_graph)
    
    try:
        with open("fake_data.xml", "r", encoding="utf-8") as f:
            xml_input = f.read()
    except FileNotFoundError:
        xml_input = "<root><info>Brak danych</info></root>"
        
    cl.user_session.set("xml_input", xml_input)
    await cl.Message(
        content="🛡️ **Privacy Gateway UI uruchomiony!** \n\nWpisz swoje pytanie (np. 'Z kim powinienem się kontaktować?'), a ja anonimizuje je i puszczę przez zabezpieczony graf LangGraph przed wyjściem w chmurę.", 
        author="System"
    ).send()

@cl.on_message
async def on_message(message: cl.Message):
    app_graph = cl.user_session.get("app_graph")
    xml_input = cl.user_session.get("xml_input")
    
    initial_state = GraphState(
        raw_xml=xml_input,
        user_query=message.content,
        raw_pii_strings=[],
        masked_context="",
        masked_query="",
        vault={},
        is_safe=False,
        cloud_response="",
        final_output=""
    )
    
    # Interfejs z informacja dla usera, ze silniki pomagaja
    msg = cl.Message(content="🔄 Trwa weryfikacja Guardrail i maskowanie struktury PII...", author="Privacy Gateway")
    await msg.send()
    
    # Funkcja zawijająca wykonanie grafu powiązana z symulacją asynchronizacji,
    # ponieważ standardowy invoke zawarty w GraphState LangGraph blokuje wątek.
    def process_graph():
        return app_graph.invoke(initial_state)
        
    final_state = await asyncio.to_thread(process_graph)
    
    final_output = final_state.get("final_output", "Brak odpowiedzi")
    detected_pii = final_state.get("vault", {})
    masked_query = final_state.get("masked_query", "")
    
    # Budowa elementow podsumowujacych zabezpieczone mechanizmy, jak w CLI:
    debug_info = ""
    if final_state.get("is_safe") and detected_pii:
        debug_info += "\n\n---\n**⚠️ Logi Zabezpieczające:**\n"
        debug_info += f"- **Skarbiec PII:** `{detected_pii}`\n"
        debug_info += f"- **Co ostatecznie widział Gemini (Cloud LLM):**\n> `{masked_query}`"
    elif final_state.get("is_safe") is False:
        debug_info += "\n\n---\n**🛑 ZABLOKOWANO:** Atak typu Prompt Injection zatrzymany przez Guardrail Agent."
        
    msg.content = final_output + debug_info
    await msg.update()
