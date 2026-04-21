from agents.guardrail import guardrail_agent
from state import GraphState
import os
from dotenv import load_dotenv
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

state = GraphState(
    user_query="Z kim powinienem się kontaktować w sprawie zamówienia?",
    raw_xml="",
    raw_pii_strings=[],
    labeled_pii_entities=[],
    masked_context="",
    masked_query="",
    vault={},
    is_safe=False,
    cloud_response="",
    final_output="",
    error_status=""
)
res = guardrail_agent(state)
print(res)
