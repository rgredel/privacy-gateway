import json
import csv
import asyncio
import time
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict

# --- KONFIGURACJA ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Wymuszenie UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

CORPUS_FILE = PROJECT_ROOT / "experiments/corpus/fp_test_corpus.json"
RESULTS_FILE = PROJECT_ROOT / "experiments/results/results_fp_resistance.json"

async def run_fp_test():
    print("="*80)
    print("START: EKSPERYMENT 1B - ODPORNOŚĆ NA FALSE POSITIVES")
    print("="*80)
    
    # Importy wewnatrz, zeby uniknac hangingu
    from src.app.main import bootstrap_app
    from src.app.infrastructure.services.presidio_factory import setup_presidio_analyzer
    from src.app.infrastructure.services.presidio_service import PresidioService

    print("[INIT] Bootstrapping components...")
    app_graph = bootstrap_app()
    analyzer = setup_presidio_analyzer()
    presidio_service = PresidioService(analyzer)
    
    with open(CORPUS_FILE, "r", encoding="utf-8") as f:
        corpus = json.load(f)
    print(f"[INIT] Korpus załadowany: {len(corpus)} dokumentów.")

    configurations = ["regex", "ener", "hybrid_gemini"]
    # Tu skupiamy sie na FP (False Positives)
    # Poniewaz w korpusie 'entities' jest puste, kazde 'detected' to FP.
    results = {config: {"fp_count": 0, "total_entities_detected": 0} for config in configurations}
    doc_details = []

    for i, doc in enumerate(corpus):
        text = doc["text"]
        doc_id = doc.get("doc_id", i)
        print(f"\n📄 [{i+1}/{len(corpus)}] ID: {doc_id}")
        
        doc_res = {"doc_id": doc_id, "text": text}
        
        for name in configurations:
            detected = []
            if name == "regex":
                detailed = presidio_service.analyze_detailed(text)
                nlp_recs = ["TransformersRecognizer", "CustomSpacyRecognizer", "SpacyRecognizer"]
                detected = [ent.value for ent in detailed if ent.recognizer not in nlp_recs]
            elif name == "ener":
                detected = presidio_service.get_candidates(text)
            elif name == "hybrid_gemini":
                try:
                    state = await app_graph.ainvoke({
                        "file_context": text, "user_query": "Analiza.",
                        "detection_mode": "hybrid", "cloud_model": "gemini-2.5-flash",
                        "vault": {}, "raw_pii_strings": []
                    }, config={"configurable": {"thread_id": f"fp_test_{doc_id}"}})
                    detected = state.get("raw_pii_strings", [])
                except Exception as e:
                    print(f" [!] Gemini Error: {e}")
                    detected = []
            
            # W tym korpusie kazde wykrycie to FP
            fp_count = len(set(detected))
            results[name]["fp_count"] += fp_count
            doc_res[f"{name}_fp"] = fp_count
            doc_res[f"{name}_detected"] = detected
            print(f"  {name:<15} | FP: {fp_count}")

        doc_details.append(doc_res)

    # Finalne statystyki
    print("\n" + "="*80)
    print("WYNIKI KOŃCOWE (FALSE POSITIVE RESISTANCE)")
    print("="*80)
    for name in configurations:
        print(f"Config: {name:<15} | Total FP: {results[name]['fp_count']}")
    
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"summary": results, "details": doc_details}, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Raport zapisany w: {RESULTS_FILE}")

if __name__ == "__main__":
    asyncio.run(run_fp_test())
