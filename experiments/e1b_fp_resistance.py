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

BIELIK_LOCAL = "qooba/bielik-1.5b-v3.0-instruct:Q8_0"

async def run_fp_test():
    parser = argparse.ArgumentParser(description="Eksperyment 1B – Odporność na False Positives")
    parser.add_argument("--skip-bielik", action="store_true", help="Pomiń lokalny model Bielik")
    args = parser.parse_args()

    print("="*80)
    print("START: EKSPERYMENT 1B - ODPORNOŚĆ NA FALSE POSITIVES (5 konfiguracji)")
    print("="*80)
    
    # Importy wewnatrz, zeby uniknac hangingu
    from src.app.main import bootstrap_app
    from src.app.infrastructure.services.presidio_factory import setup_presidio_analyzer
    from src.app.infrastructure.services.presidio_service import PresidioService
    from src.app.infrastructure.llm.factory import get_local_model, get_cloud_gemini_2_5_flash
    from src.app.infrastructure.llm.langchain_service import LangChainService
    from src.app.use_cases.detection_use_case import DetectionUseCase

    print("[INIT] Bootstrapping components...")
    app_graph = bootstrap_app()
    analyzer = setup_presidio_analyzer()
    presidio_service = PresidioService(analyzer)
    
    # Inicjalizacja Bielik
    detection_uc_local = None
    if not args.skip_bielik:
        try:
            model_local = get_local_model(model_name=BIELIK_LOCAL)
            llm_service_local = LangChainService(local_llm=model_local, cloud_llm=model_local)
            detection_uc_local = DetectionUseCase(llm_service=llm_service_local, privacy_engine=presidio_service)
            print("     ✔ Bielik 1.5 gotowy.")
        except Exception as e:
            print(f"     ✘ Błąd inicjalizacji Bielika: {e}")
    else:
        print("     ⏭ Bielik pominięty (--skip-bielik)")
    
    with open(CORPUS_FILE, "r", encoding="utf-8") as f:
        corpus = json.load(f)
    print(f"[INIT] Korpus załadowany: {len(corpus)} dokumentów.")

    configurations = ["regex", "herbert", "ener", "hybrid_bielik", "hybrid_gemini"]
    if args.skip_bielik:
        configurations.remove("hybrid_bielik")
    
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
            elif name == "herbert":
                # Tylko encje z TransformersRecognizer (HerBERT NER)
                herbert_entities = ["PERSON", "LOCATION", "ORGANIZATION"]
                detailed_herbert = presidio_service.analyze_detailed(text, entities=herbert_entities)
                detected = [ent.value for ent in detailed_herbert if ent.recognizer == "TransformersRecognizer"]
            elif name == "ener":
                detected = presidio_service.get_candidates(text)
            elif name == "hybrid_bielik":
                if not detection_uc_local:
                    print(f"  {name:<15} | SKIPPED (brak modelu)")
                    doc_res[f"{name}_fp"] = "N/A"
                    doc_res[f"{name}_detected"] = []
                    continue
                try:
                    verified_pii, _ = await asyncio.wait_for(
                        detection_uc_local.execute(text, mode="hybrid"),
                        timeout=45.0
                    )
                    detected = list(verified_pii) if verified_pii else []
                except Exception as e:
                    print(f"  [!] Bielik Error: {e}")
                    detected = []
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

