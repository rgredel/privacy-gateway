import os
import pytest
from utils.file_handler import process_uploaded_file

def test_process_text_file(tmp_path):
    """Test przetwarzania zwykłego pliku tekstowego."""
    d = tmp_path / "subdir"
    d.mkdir()
    p = d / "test.txt"
    p.write_text("Tajne dane: 123", encoding="utf-8")
    
    content = process_uploaded_file(str(p), "test.txt")
    assert "Tajne dane: 123" in content

def test_process_unsupported_file():
    """Test obsługi nieznanych formatów."""
    content = process_uploaded_file("some.exe", "some.exe")
    assert "[BŁĄD: Nieobsługiwany format pliku some.exe]" in content
