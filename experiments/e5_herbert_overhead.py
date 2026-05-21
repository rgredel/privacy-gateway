import time
import json
import numpy as np
from pathlib import Path
from src.app.infrastructure.services.presidio_factory import setup_presidio_analyzer

# Konfiguracja
BASE_DIR = Path(__file__).parent.parent
CORPUS_FILE = BASE_DIR / "experiments/corpus/benchmark_corpus.json"

def measure_ner_latency():
    print("START: EKSPERYMENT E5 - NARZUT MODELU HERBERT (NER)")
    
    # 1. Inicjalizacja pelnego analizatora (RegEx + HerBERT + Spacy)
    analyzer = setup_presidio_analyzer()
    
    with open(CORPUS_FILE, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    test_docs = corpus[:50] # Wieksza proba dla statystyki
    
    regex_times = []
    herbert_times = []
    total_ner_times = []

    print(f"Testowanie na {len(test_docs)} dokumentach...")

    for i, doc in enumerate(test_docs):
        text = doc['text']
        
        # POMIAR 1: Same RegEx
        start = time.perf_counter()
        res_regex = analyzer.analyze(text, language="pl", entities=["PL_PESEL", "PL_NIP", "PL_REGON", "PL_ZIP_CODE", "INV", "PL_IBAN"])
        regex_times.append(time.perf_counter() - start)
        
        # POMIAR 2: Sam HerBERT
        start = time.perf_counter()
        res_herbert = analyzer.analyze(text, language="pl", entities=["PERSON", "LOCATION", "ORGANIZATION"])
        herbert_times.append(time.perf_counter() - start)
        
        # POMIAR 3: Calosc
        start = time.perf_counter()
        res_total = analyzer.analyze(text, language="pl")
        total_ner_times.append(time.perf_counter() - start)
        
        if i == 0:
            print(f"  [WERYFIKACJA] Doc 1 len: {len(text)} znakow")
            print(f"  [WERYFIKACJA] RegEx znalazl: {len(res_regex)} encji")
            print(f"  [WERYFIKACJA] HerBERT znalazl: {len(res_herbert)} encji")
            if len(res_herbert) > 0:
                print(f"  [WERYFIKACJA] Przyklad HerBERTa: {res_herbert[0].entity_type} na poz. {res_herbert[0].start}")
        
        if (i+1) % 10 == 0:
            print(f"  Progres: {i+1}/50...")

    print("\n" + "="*60)
    print("WYNIKI NARZUTU LOKALNEJ DETEKCJI (Latency per doc)")
    print("="*60)
    print(f"RegEx Only (National IDs):  {np.mean(regex_times)*1000:.2f} ms")
    print(f"HerBERT NER (Transformers): {np.mean(herbert_times)*1000:.2f} ms")
    print(f"Full Local Hybrid NER:      {np.mean(total_ner_times)*1000:.2f} ms")
    print("-" * 60)
    print(f"HerBERT jest {(np.mean(herbert_times)/np.mean(regex_times)):.1f}x wolniejszy niz RegEx,")
    print(f"ale dodaje tylko {np.mean(herbert_times)*1000:.2f} ms do calkowitego czasu.")
    print("="*60)

if __name__ == "__main__":
    measure_ner_latency()
