from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
import os

load_dotenv()

models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]

for m in models:
    try:
        llm = ChatGoogleGenerativeAI(model=m)
        res = llm.invoke("Hi")
        print(f"Model {m} działa!")
        break
    except Exception as e:
        print(f"Model {m} błąd: {e}")
