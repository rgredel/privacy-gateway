from langchain_ollama import ChatOllama

try:
    llm = ChatOllama(model="qooba/bielik-1.5b-v3.0-instruct:Q8_0")
    res = llm.invoke("Cześć, jak się masz?")
    print(f"Bielik działa: {res.content}")
except Exception as e:
    print(f"Bielik błąd: {e}")
