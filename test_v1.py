from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
import os

load_dotenv()

try:
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", version="v1")
    res = llm.invoke("Hi")
    print("Success with v1!")
except Exception as e:
    print(f"Error with v1: {e}")
