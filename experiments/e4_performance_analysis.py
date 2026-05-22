import asyncio
import time
import json
import csv
import numpy as np
import sys
import argparse
from pathlib import Path

# Wymuszenie UTF-8 na Windowsie
try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    import io
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

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
        nlp_recs = ["TransformersRecognizer", "CustomSpacyRecognizer", "SpacyRecognizer"]
        recognizers = [r for r in presidio_service.analyzer.registry.get_recognizers(language="pl", all_fields=True) if r.name not in nlp_recs]
        results = []
        for r in recognizers:
            res = r.analyze(text, entities=r.supported_entities)
            if res:
                results.extend(res)
        _ = [ent.value if hasattr(ent, 'value') else text[ent.start:ent.end] for ent in results]
    elif variant == "herbert":
        herbert_entities = ["PERSON", "LOCATION", "ORGANIZATION"]
        detailed = presidio_service.analyze_detailed(text, entities=herbert_entities)
        herbert_labels = ["PERSON", "LOCATION", "ORGANIZATION"]
        _ = [ent.value for ent in detailed if ent.label in herbert_labels]
    else: # ener
        _ = presidio_service.get_candidates(text)
    
    return time.perf_counter() - start

async def main():
    parser = argparse.ArgumentParser(description="Eksperyment E4 – Latency Benchmark")
    parser.add_argument("--limit", type=int, default=50, help="Liczba dokumentów do testowania")
    parser.add_argument("--skip-bielik", action="store_true", help="Pomiń lokalny model Bielik")
    args = parser.parse_args()

    print("="*60)
    print("START: EKSPERYMENT E4 - KOMPLEKSOWE POROWNANIE LATENCJI")
    print("="*60)
    
    app_graph = bootstrap_app()
    analyzer = setup_presidio_analyzer()
    presidio_service = PresidioService(analyzer)
    
    with open(CORPUS_FILE, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    # Testujemy na wybranej liczbie dokumentów (domyślnie 50)
    test_docs = corpus[:args.limit]
    results = []
    
    all_configs = ["regex", "herbert", "ener", "hybrid_gemini", "hybrid_bielik"]
    configs = [cfg for cfg in all_configs if not (args.skip_bielik and cfg == "hybrid_bielik")]

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
    print("\n" + "="*103)
    header = f"{'Konfiguracja':<20} | {'Srednia':<10} | {'Mediana':<10} | {'P95':<10} | {'Min':<10} | {'Max':<10} | {'Throughput':<15}"
    print(header)
    print("-" * 103)
    
    for cfg in configs:
        times = [r[cfg] for r in results if r[cfg] is not None]
        if times:
            mean_val = np.mean(times)
            median_val = np.median(times)
            p95_val = np.percentile(times, 95)
            min_val = np.min(times)
            max_val = np.max(times)
            throughput_val = 1.0 / mean_val if mean_val > 0 else 0.0
            print(f"{cfg:<20} | {mean_val:<10.3f} | {median_val:<10.3f} | {p95_val:<10.3f} | {min_val:<10.3f} | {max_val:<10.3f} | {throughput_val:<15.2f}")
        else:
            print(f"{cfg:<20} | N/A")
    print("="*103)

    # Zapis
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(results[0].keys())
    with open(RESULTS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    print(f"Wyniki zapisano w: {RESULTS_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
