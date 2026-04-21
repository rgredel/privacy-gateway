from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
import os

load_dotenv()

try:
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
    res = llm.invoke("Hi")
    print(f"Gemini 2.5 Flash działa: {res.content}")
except Exception as e:
    print(f"Gemini 2.5 Flash błąd: {e}")
