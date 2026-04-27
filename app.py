import asyncio
import uuid
import chainlit as cl
from src.app.main import graph as app_graph
from src.app.utils.file_handler import process_uploaded_file
from chainlit.input_widget import Switch, Select, Slider
from src.app.domain.entities import GraphState

@cl.on_chat_start
async def on_chat_start():
    # Konfiguracja ustawień w panelu bocznym
    settings = await cl.ChatSettings([
        Switch(id="enable_guardrail", label="Włącz Guardrail (Security)", initial=False),
        Slider(
            id="guardrail_threshold",
            label="Próg czułości Guardrail (PromptGuard)",
            initial=0.85,
            min=0.5,
            max=1.0,
            step=0.05,
            description="Im niższy próg, tym czulsze wykrywanie ataków (więcej fałszywych alarmów)."
        ),
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
            values=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-pro"], 
            initial_value="gemini-2.5-flash"
        ),
        Switch(id="show_debug", label="Pokaż logi zabezpieczeń", initial=True)
    ]).send()
    cl.user_session.set("settings", settings)

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

    # Update session context (adding new files to knowledge base)
    if files_text:
        xml_input += files_text
        cl.user_session.set("xml_input", xml_input)

    # 2. Prepare initial state for the graph
    settings = cl.user_session.get("settings")
    
    initial_state = GraphState(
        file_context=xml_input,
        user_query=message.content,
        enable_guardrail=settings.get("enable_guardrail", False),
        guardrail_threshold=settings.get("guardrail_threshold", 0.85),
        detection_mode=settings.get("detection_mode", "ner-only"),
        cloud_model=settings.get("cloud_model", "gemini-2.5-flash"),
        local_model=settings.get("local_model", "qooba/bielik-1.5b-v3.0-instruct:Q8_0"),
        show_debug=settings.get("show_debug", True)
    )
    
    config = {"configurable": {"thread_id": thread_id}}
    
    msg = cl.Message(content="🔄 Verifying Guardrails and masking PII...", author="Privacy Gateway")
    await msg.send()
    
    # 3. Invoke the Privacy Graph
    final_state_dict = await app_graph.ainvoke(initial_state, config=config)
    final_state = GraphState(**final_state_dict) if isinstance(final_state_dict, dict) else final_state_dict
    
    final_output = final_state.final_output
    detected_pii = final_state.vault
    masked_query = final_state.masked_query
    
    # 4. Build debug interface
    debug_info = ""
    if settings.get("show_debug"):
        debug_info += "\n\n---\n**⚙️ System Logs (Debug):**\n"
        
        detected_pii_str = ", ".join(final_state.raw_pii_strings) if final_state.raw_pii_strings else "(No PII detected)"
        debug_info += f"- **PII Vault:** `{detected_pii_str}`\n"
        debug_info += f"- **Masked Query:**\n> `{masked_query}`\n"
        
        if final_state.masked_context:
            context_snippet = final_state.masked_context[:200] + "..." if len(final_state.masked_context) > 200 else final_state.masked_context
            debug_info += f"- **Masked Context (Files):**\n```\n{context_snippet}\n```\n"

        # Show cloud LLM prompt details
        cloud_debug = final_state.cloud_query_debug or "No data available"
        debug_info += f"\n**☁️ Cloud LLM View (Gemini):**\n```\n{cloud_debug}\n```"
        
        # PII Leak Warnings
        privacy_warnings = final_state.privacy_warnings
        if privacy_warnings:
            debug_info += "\n**🛑 Data Leakage Warnings (Anti-Leakage):**\n"
            for warn in privacy_warnings:
                debug_info += f"- {warn}\n"
        
        if final_state.is_safe is False:
            debug_info += "\n**🛑 BLOCKED:** Prompt Injection attack intercepted by Guardrail Agent."
        
    msg.content = final_output + debug_info
    await msg.update()
