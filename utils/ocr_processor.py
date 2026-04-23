import fitz  # PyMuPDF
from rapidocr_onnxruntime import RapidOCR
import numpy as np
from PIL import Image
import io

class OCRProcessor:
    def __init__(self):
        # Inicjalizacja silnika OCR (ładowanie modeli przy pierwszym użyciu)
        self.engine = RapidOCR()

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Ekstrahuje tekst z PDF. Próbuje najpierw tekstu warstwowego, 
        a jeśli strona jest pusta/obrazkowa - używa OCR.
        """
        doc = fitz.open(pdf_path)
        full_text = []

        for page_index in range(len(doc)):
            page = doc[page_index]
            
            # 1. Próba wyciągnięcia tekstu "cyfrowego"
            text = page.get_text().strip()
            
            # 2. Jeśli tekstu mało (np. tylko znaki specjalne lub pusta strona), użyj OCR
            if len(text) < 50: 
                # Renderowanie strony do obrazu
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) # Zoom x2 dla lepszej jakości OCR
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                
                # Konwersja PIL Image na format akceptowany przez RapidOCR (numpy array)
                img_np = np.array(img)
                
                # Uruchomienie OCR
                result, _ = self.engine(img_np)
                
                if result:
                    ocr_text = "\n".join([line[1] for line in result])
                    full_text.append(f"--- Strona {page_index + 1} (OCR) ---\n{ocr_text}")
                else:
                    full_text.append(f"--- Strona {page_index + 1} (Brak tekstu) ---")
            else:
                full_text.append(f"--- Strona {page_index + 1} ---\n{text}")

        doc.close()
        return "\n\n".join(full_text)

    def extract_text_from_image(self, image_path_or_bytes) -> str:
        """Obsługa bezpośrednich plików graficznych (jpg, png)."""
        result, _ = self.engine(image_path_or_bytes)
        if result:
            return "\n".join([line[1] for line in result])
        return ""
