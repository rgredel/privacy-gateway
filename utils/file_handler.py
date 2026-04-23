import os
from utils.ocr_processor import OCRProcessor

# Inicjalizacja procesora OCR (singleton)
ocr_processor = OCRProcessor()

def process_uploaded_file(file_path: str, file_name: str) -> str:
    """
    Rozpoznaje typ pliku i ekstrahuje tekst.
    """
    ext = os.path.splitext(file_name)[1].lower()
    
    if ext == ".pdf":
        return ocr_processor.extract_text_from_pdf(file_path)
    
    if ext in [".txt", ".xml", ".json", ".csv", ".md", ".py"]:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            # Próba innego kodowania (np. cp1250 dla starych plików Windows)
            with open(file_path, "r", encoding="cp1250") as f:
                return f.read()
    
    if ext in [".jpg", ".jpeg", ".png"]:
        return ocr_processor.extract_text_from_image(file_path)
        
    return f"\n[BŁĄD: Nieobsługiwany format pliku {file_name}]\n"
