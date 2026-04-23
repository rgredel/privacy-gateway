import os
import fitz
import pytest

def test_extract_text_from_pdf_digital(ocr_processor):
    """Test ekstrakcji tekstu z 'cyfrowego' PDF (bez OCR)."""
    pdf_path = "tests/temp_digital.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Testowe PII: Jan Kowalski")
    doc.save(pdf_path)
    doc.close()

    try:
        text = ocr_processor.extract_text_from_pdf(pdf_path)
        assert "Jan Kowalski" in text
        assert "Strona 1" in text
    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

def test_extract_text_from_image_unsupported(ocr_processor):
    """Test obsługi nieistniejących plików."""
    with pytest.raises(Exception):
        ocr_processor.extract_text_from_image("non_existent.jpg")
