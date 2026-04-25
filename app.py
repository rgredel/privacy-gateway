import asyncio
import uuid
import chainlit as cl
from state import GraphState
from privacy_gateway import build_graph
from utils.file_handler import process_uploaded_file
from chainlit.input_widget import Switch, Select

@cl.on_chat_start
async def on_chat_start():
    # Konfiguracja ustawień w panelu bocznym
    settings = await cl.ChatSettings([
        Switch(id="enable_guardrail", label="Włącz Guardrail (Security)", initial=False),
        Select(
            id="detection_mode", 
            label="Tryb Detekcji PII", 
            values=["hybrid", "llm-only", "ner-only"], 
            initial_value="ner-only"
        ),
        Select(
            id="local_model", 
            label="Model Przetwarzania PII (Lokalny lub Chmurowy)", 
            values=["qooba/bielik-1.5b-v3.0-instruct:Q8_0", "llama3.2", "phi3", "gemini-2.5-flash", "gemini-1.5-pro"], 
            initial_value="qooba/bielik-1.5b-v3.0-instruct:Q8_0"
        ),
        Select(
            id="cloud_model", 
            label="Model Chmurowy (GenAI)", 
            values=["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"], 
            initial_value="gemini-2.5-flash"
        ),
        Switch(id="show_debug", label="Pokaż logi zabezpieczeń", initial=True)
    ]).send()
    cl.user_session.set("settings", settings)

    # Inicjalizacja grafu LangGraph (Checkpointer jest wbudowany w build_graph)
    app_graph = build_graph()
    cl.user_session.set("app_graph", app_graph)
    
    # Generowanie unikalnego ID wątku dla tej sesji rozmowy
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id)

    await cl.Message(
        content="🛡️ **Privacy Gateway UI uruchomiony!** \n\n"
                "Możesz konfigurować agenty w panelu bocznym (ikona suwaków). \n"
                "Obsługuję pliki (TXT, PDF, XML, obrazy) i pamiętam kontekst rozmowy.", 
        author="System"
    ).send()
    
    # Generowanie unikalnego ID wątku dla tej sesji rozmowy

@cl.on_settings_update
async def setup_agent_config(settings):
    cl.user_session.set("settings", settings)
    await cl.Message(content="✅ Ustawienia agentów zostały zaktualizowane.").send()

@cl.on_message
async def on_message(message: cl.Message):
    app_graph = cl.user_session.get("app_graph")
    xml_input = cl.user_session.get("xml_input", "")
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
    # Pobranie aktualnych ustawień z sesji
    settings = cl.user_session.get("settings")
    
    initial_state = {
        "raw_xml": xml_input,
        "user_query": message.content,
        "raw_pii_strings": [],
        "labeled_pii_entities": [],
        "masked_context": "",
        "masked_query": "",
        "vault": {},
        "is_safe": False,
        "cloud_response": "",
        "final_output": "",
        "error_status": "",
        "cloud_query_debug": "",
        "privacy_warnings": [],
        # Przekazanie ustawień z UI do LangGraph
        "enable_guardrail": settings.get("enable_guardrail", False),
        "detection_mode": settings.get("detection_mode", "ner-only"),
        "cloud_model": settings.get("cloud_model", "gemini-2.5-flash"),
        "local_model": settings.get("local_model", "qooba/bielik-1.5b-v3.0-instruct:Q8_0"),
        "show_debug": settings.get("show_debug", True)
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
    if settings.get("show_debug"):
        if final_state.get("is_safe") and detected_pii:
            debug_info += "\n\n---\n**⚠️ Logi Zabezpieczające:**\n"
            debug_info += f"- **Skarbiec PII:** `{detected_pii}`\n"
            debug_info += f"- **Ostatnie zamaskowane pytanie:**\n> `{masked_query}`"
            
            # Dodano wyświetlanie pełnego zapytania do chmury
            cloud_debug = final_state.get("cloud_query_debug", "Brak danych")
            debug_info += f"\n\n**☁️ Co widzi Cloud LLM (Gemini):**\n```\n{cloud_debug}\n```"
            
            # Dodano wyświetlanie ostrzeżeń o wyciekach PII
            privacy_warnings = final_state.get("privacy_warnings", [])
            if privacy_warnings:
                debug_info += "\n\n**🛑 Ostrzeżenia o wyciekach (Anti-Leakage):**\n"
                for warn in privacy_warnings:
                    debug_info += f"- {warn}\n"
        elif final_state.get("is_safe") is False:
            debug_info += "\n\n---\n**🛑 ZABLOKOWANO:** Atak typu Prompt Injection zatrzymany przez Guardrail Agent."
        
    msg.content = final_output + debug_info
    await msg.update()
