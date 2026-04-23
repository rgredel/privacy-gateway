import asyncio
import uuid
import chainlit as cl
from state import GraphState
from privacy_gateway import build_graph
from utils.file_handler import process_uploaded_file

@cl.on_chat_start
async def on_chat_start():
    # Inicjalizacja grafu LangGraph (Checkpointer jest wbudowany w build_graph)
    app_graph = build_graph()
    cl.user_session.set("app_graph", app_graph)
    
    # Generowanie unikalnego ID wątku dla tej sesji rozmowy
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id)
    
    try:
        with open("fake_data.xml", "r", encoding="utf-8") as f:
            xml_input = f.read()
    except FileNotFoundError:
        xml_input = "<root><info>Brak danych</info></root>"
        
    cl.user_session.set("xml_input", xml_input)
    
    await cl.Message(
        content="🛡️ **Privacy Gateway UI uruchomiony!** \n\n"
                "Możesz zadawać pytania, a także **dołączać pliki** (TXT, PDF z OCR, XML, obrazy). "
                "Wszystko zostanie zanonimizowane przed wysłaniem do chmury. "
                "Pamiętam też naszą rozmowę (Memory enabled!).", 
        author="System"
    ).send()

@cl.on_message
async def on_message(message: cl.Message):
    app_graph = cl.user_session.get("app_graph")
    xml_input = cl.user_session.get("xml_input")
    thread_id = cl.user_session.get("thread_id")
    
    # 1. Obsługa załączników (Files context)
    files_text = ""
    if message.elements:
        for element in message.elements:
            if element.path:
                status_msg = cl.Message(content=f"⏳ Przetwarzam plik: {element.name}...", author="System")
                await status_msg.send()
                
                # Ekstrakcja tekstu (obsługa OCR dla PDF/IMG w środku)
                content = await asyncio.to_thread(process_uploaded_file, element.path, element.name)
                files_text += f"\n\n--- ZAŁĄCZNIK: {element.name} ---\n{content}"
                
                status_msg.content = f"✅ Przetworzono plik: {element.name}"
                await status_msg.update()

    # Aktualizacja kontekstu w sesji (dodanie nowych plików do bazy wiedzy)
    if files_text:
        xml_input += files_text
        cl.user_session.set("xml_input", xml_input)

    # 2. Przygotowanie stanu początkowego dla tej tury
    # Uwaga: 'messages' nie ustawiamy ręcznie, LangGraph sam je dociągnie z checkpointera na podstawie thread_id
    initial_state = {
        "raw_xml": xml_input,
        "user_query": message.content,
        "raw_pii_strings": [],
        "masked_context": "",
        "masked_query": "",
        "vault": {},
        "is_safe": False,
        "cloud_response": "",
        "final_output": ""
    }
    
    # Konfiguracja dla pamięci
    config = {"configurable": {"thread_id": thread_id}}
    
    msg = cl.Message(content="🔄 Trwa weryfikacja Guardrail i maskowanie PII...", author="Privacy Gateway")
    await msg.send()
    
    def process_graph():
        # Używamy config z thread_id dla zachowania pamięci
        return app_graph.invoke(initial_state, config=config)
        
    final_state = await asyncio.to_thread(process_graph)
    
    final_output = final_state.get("final_output", "Brak odpowiedzi")
    detected_pii = final_state.get("vault", {})
    masked_query = final_state.get("masked_query", "")
    
    # 3. Budowa interfejsu debugowania
    debug_info = ""
    if final_state.get("is_safe") and detected_pii:
        debug_info += "\n\n---\n**⚠️ Logi Zabezpieczające:**\n"
        debug_info += f"- **Skarbiec PII:** `{detected_pii}`\n"
        debug_info += f"- **Ostatnie zamaskowane pytanie:**\n> `{masked_query}`"
    elif final_state.get("is_safe") is False:
        debug_info += "\n\n---\n**🛑 ZABLOKOWANO:** Atak typu Prompt Injection zatrzymany przez Guardrail Agent."
        
    msg.content = final_output + debug_info
    await msg.update()
