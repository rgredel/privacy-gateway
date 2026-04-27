from typing import Any, Callable
from src.app.domain.ports import ISecurityService

class PromptGuardService(ISecurityService):
    """
    Adapter dla modelu PromptGuard z HuggingFace.
    Wykorzystuje klasyfikator transformers oraz funkcję tłumaczącą.
    """
    
    def __init__(self, classifier: Any, translator: Callable[[str], str]):
        self.classifier = classifier
        self.translator = translator

    async def verify_query(self, query: str, threshold: float) -> bool:
        """
        Weryfikuje zapytanie.
        Zwraca True jeśli bezpieczne, False jeśli wykryto atak.
        """
        try:
            # 1. Tłumaczenie (PromptGuard najlepiej działa na angielskim)
            translated = self.translator(query)
            
            # 2. Klasyfikacja
            results = self.classifier(translated)
            top_result = results[0]
            label = top_result["label"]
            score = top_result["score"]
            
            # LABEL_1 oznacza 'malicious' w modelu Prompt Guard 2
            is_malicious = label == "LABEL_1" and score > threshold
            return not is_malicious
            
        except Exception as e:
            # W przypadku błędu technicznego domyślnie przepuszczamy (fail-safe)
            print(f"[ERROR: PROMPTGUARD] {e}")
            return True
