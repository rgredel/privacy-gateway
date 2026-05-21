import asyncio
import time
import json
import csv
import numpy as np
import sys
from pathlib import Path

# Dodanie katalogu głównego projektu do sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
# Wyłączenie logów HTTP
logging.getLogger("httpx").setLevel(logging.WARNING)

from src.app.main import bootstrap_app
from src.app.core.config import settings

# Konfiguracja
BASE_DIR = Path(__file__).parent.parent
CORPUS_FILE = BASE_DIR / "experiments/corpus/benchmark_corpus.json"
RESULTS_FILE = BASE_DIR / "experiments/results/results_e4_comparison.csv"

from src.app.domain.entities import GraphState

from src.app.domain.entities import GraphState
from src.app.infrastructure.services.presidio_factory import setup_presidio_analyzer
from src.app.infrastructure.services.presidio_service import PresidioService

async def measure_latency(app_graph, query, context, mode="ner-only", model=None):
    """Mierzy czas wykonania potoku dla zadanej konfiguracji GraphState"""
    initial_state = GraphState(
        file_context=context,
        user_query=query,
        local_model=model if model else settings.local_model_default,
        cloud_model=settings.cloud_model_default,
        detection_mode=mode,
        guardrail_threshold=settings.default_guardrail_threshold,
        enable_guardrail=True,
        show_debug=False
    )

    config = {"configurable": {"thread_id": f"perf_{mode}_{int(time.time()*1000)}"}}

    try:
        start_invoke = time.perf_counter()
        await app_graph.ainvoke(initial_state, config=config)
        end_invoke = time.perf_counter()
        return end_invoke - start_invoke
    except Exception as e:
        print(f"    [!] Blad ({mode}): {e}")
        return None

def measure_presidio_latency(presidio_service, text, variant="ener"):
    """Mierzy czas wykonania samej detekcji Presidio dla różnych wariantów"""
    start = time.perf_counter()
    if variant == "regex":
        detailed = presidio_service.analyze_detailed(text)
        nlp_recs = ["TransformersRecognizer", "CustomSpacyRecognizer", "SpacyRecognizer"]
        _ = [ent.value for ent in detailed if ent.recognizer not in nlp_recs]
    elif variant == "herbert":
        detailed = presidio_service.analyze_detailed(text)
        herbert_labels = ["PERSON", "LOCATION", "ORGANIZATION"]
        _ = [ent.value for ent in detailed if ent.label in herbert_labels]
    else: # ener
        _ = presidio_service.get_candidates(text)
    
    return time.perf_counter() - start

async def main():
    print("="*60)
    print("START: EKSPERYMENT E4 - KOMPLEKSOWE POROWNANIE LATENCJI")
    print("="*60)
    
    app_graph = bootstrap_app()
    analyzer = setup_presidio_analyzer()
    presidio_service = PresidioService(analyzer)
    
    with open(CORPUS_FILE, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    # Testujemy na 5 dokumentach dla lepszej statystyki
    test_docs = corpus[:5]
    results = []
    
    configs = ["regex", "herbert", "ener", "hybrid_gemini", "hybrid_bielik"]

    print(f"Testowanie na {len(test_docs)} dokumentach dla {len(configs)} konfiguracji...")

    for i, doc in enumerate(test_docs):
        query = "Przeanalizuj ten dokument i podaj mi kwoty netto."
        context = doc['text']
        doc_id = doc.get('doc_id', i)
        
        print(f"\n[DOC {i+1}/{len(test_docs)}] ID: {doc_id}")
        doc_res = {"doc_id": doc_id}
        
        for cfg in configs:
            print(f"    -> Mierzę {cfg:<15}...", end="", flush=True)
            t = 0.0
            if cfg == "regex":
                t = measure_presidio_latency(presidio_service, context, "regex")
            elif cfg == "herbert":
                t = measure_presidio_latency(presidio_service, context, "herbert")
            elif cfg == "ener":
                t = measure_presidio_latency(presidio_service, context, "ener")
            elif cfg == "hybrid_gemini":
                t = await measure_latency(app_graph, query, context, mode="hybrid", model="gemini-2.5-flash")
            elif cfg == "hybrid_bielik":
                t = await measure_latency(app_graph, query, context, mode="hybrid", model="qooba/bielik-1.5b-v3.0-instruct:Q8_0")
            
            if t:
                print(f" DONE ({t:.3f}s)")
                doc_res[cfg] = t
            else:
                print(" FAILED")
                doc_res[cfg] = None
        
        results.append(doc_res)

    # Statystyki i Raport
    print("\n" + "="*80)
    print(f"{'Konfiguracja':<20} | {'Srednia':<10} | {'Mediana':<10} | {'Min':<10} | {'Max':<10}")
    print("-" * 80)
    
    for cfg in configs:
        times = [r[cfg] for r in results if r[cfg] is not None]
        if times:
            print(f"{cfg:<20} | {np.mean(times):.3f}s | {np.median(times):.3f}s | {np.min(times):.3f}s | {np.max(times):.3f}s")
        else:
            print(f"{cfg:<20} | N/A")
    print("="*80)

    # Zapis
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    
    print(f"Wyniki zapisano w: {RESULTS_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
