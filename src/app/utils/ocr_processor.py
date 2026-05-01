import pymupdf4llm
from pathlib import Path

class OCRProcessor:
    """Professional "Out-of-the-box" document processor based on pymupdf4llm.
    
    Converts PDFs and images directly to Markdown format, preserving tables, 
    headers, and layout without complex custom logic.
    """
    
    def __init__(self) -> None:
        """Initializes the processor. No engine initialization required for pymupdf4llm."""
        pass

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extracts text from a PDF file into Markdown format in a single call.
        
        Args:
            pdf_path (str): The absolute or relative path to the PDF file.
            
        Returns:
            str: The extracted content in Markdown format.
        """
        try:
            path_obj = Path(pdf_path).resolve()
            if not path_obj.exists():
                return f"[ERROR: File does not exist at path {pdf_path}]"
                
            # to_markdown automatically detects tables and document structure
            return str(pymupdf4llm.to_markdown(str(path_obj)))
        except Exception as e:
            return f"\n[ERROR PDF4LLM: {str(e)}]\n"

    def extract_text_from_image(self, image_path: str) -> str:
        """Extracts text from an image file into Markdown format.
        
        Args:
            image_path (str): The absolute or relative path to the image file.
            
        Returns:
            str: The extracted content in Markdown format.
        """
        try:
            path_obj = Path(image_path).resolve()
            if not path_obj.exists():
                return f"[ERROR: File does not exist at path {image_path}]"

            return str(pymupdf4llm.to_markdown(str(path_obj)))
        except Exception as e:
            return f"\n[ERROR IMAGE4LLM: {str(e)}]\n"
