import pytest
from privacy_gateway import build_graph
from utils.ocr_processor import OCRProcessor

from langgraph.checkpoint.memory import MemorySaver

@pytest.fixture
def app_graph():
    """Fixture zwracający skompilowany graf LangGraph z czystą pamięcią."""
    return build_graph(checkpointer=MemorySaver())

@pytest.fixture
def ocr_processor():
    """Fixture dla procesora OCR."""
    return OCRProcessor()
