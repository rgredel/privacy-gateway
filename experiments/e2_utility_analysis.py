"""
e2_utility_analysis.py – Eksperyment 2: Analiza kompromisu prywatność-użyteczność.

Zgodnie z Rozdziałem 6.2.2 pracy magisterskiej.
Badamy kompromis:
1. Privacy Score: % poprawnie zamaskowanych PII (Recall).
2. Utility Score: % zachowanych słów w tekście zamaskowanym (Word Count Preservation).

Wersja z poprawioną definicją użyteczności (Token-based Word Count Preservation).
"""

import csv
import json
import sys
import asyncio
import re
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict

# Wymuszenie UTF-8 na konsoli Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format='%(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# ── Importy z projektu głównego ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.app.core.config import settings
from src.app.domain.entities import RecognizedEntity, PIIEntity
from src.app.infrastructure.llm.factory import get_local_model, get_cloud_gemini_2_5_flash
from src.app.infrastructure.llm.langchain_service import LangChainService
from src.app.use_cases.detection_use_case import DetectionUseCase
from src.app.infrastructure.services.presidio_factory import setup_presidio_analyzer
from src.app.infrastructure.services.presidio_service import PresidioService

# Konfiguracja ścieżek
CORPUS_PATH = PROJECT_ROOT / "experiments" / "corpus" / "benchmark_corpus.json"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
RESULTS_E2_CSV = RESULTS_DIR / "results_e2_comparison.csv"
CHECKPOINT_E2 = RESULTS_DIR / "checkpoint_e2.json"

BIELIK_LOCAL = "qooba/bielik-1.5b-v3.0-instruct:Q8_0"

# ══════════════════════════════════════════════════════════════════════════════
# 1. Narzędzia analityczne
# ══════════════════════════════════════════════════════════════════════════════

def tokenize(text: str) -> List[str]:
    """Prosta tokenizacja na słowa i liczby."""
    return re.findall(r'\b\w+\b', text)

def strip_polish_diacritics(s: str) -> str:
    if not isinstance(s, str):
        return ""
    diacritics_map = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
        'Ą': 'a', 'Ć': 'c', 'Ę': 'e', 'Ł': 'l', 'Ń': 'n', 'Ó': 'o', 'Ś': 's', 'Ź': 'z', 'Ż': 'z'
    }
    for char, replacement in diacritics_map.items():
        s = s.replace(char, replacement)
    return s

def normalize(s: str) -> str:
    if not isinstance(s, str): return ""
    return strip_polish_diacritics(s.strip().lower())

def pii_matches(detected: str, truth: str) -> bool:
    d = normalize(detected)
    t = normalize(truth)
    if not d or not t: return False
    return d == t or d in t or t in d

def calculate_privacy_score(detected_pii_vals: List[str], gt_entities: List[Dict]) -> float:
    gt_texts = [e["text"] for e in gt_entities]
    if not gt_texts:
        return 1.0
    
    tp = 0
    matched_gt = set()
    for d in detected_pii_vals:
        for i, gt_t in enumerate(gt_texts):
            if i not in matched_gt and pii_matches(d, gt_t):
                tp += 1
                matched_gt.add(i)
                break
    return tp / len(gt_texts)

def calculate_utility_score(text: str, pii_entities: List[PIIEntity], privacy_engine: PresidioService) -> float:
    tokens_original = tokenize(text)
    if not tokens_original:
        return 1.0
    
    masked_text, _ = privacy_engine.mask_text(text, pii_entities)
    tokens_masked = tokenize(masked_text)
    
    return len(tokens_masked) / len(tokens_original)

async def run_hybrid_pii(
    detection_uc: Optional[DetectionUseCase], 
    llm_service: LangChainService, 
    model: Any, 
    detailed: List[RecognizedEntity], 
    text: str
) -> List[PIIEntity]:
    if not detection_uc:
        return []
    # Wywołanie potoku hybrydowego
    verified_pii, _ = await detection_uc.execute(text, mode="hybrid")
    val_to_label = {ent.value: ent.label for ent in detailed}
    
    hy_entities = []
    for val in verified_pii:
        label = val_to_label.get(val)
        if not label:
            labeled_entities = await llm_service.label_pii([val], model_name=model.model)
            label = labeled_entities[0].label if labeled_entities else "UNKNOWN"
        hy_entities.append(PIIEntity(value=val, label=label))
    return hy_entities

# ══════════════════════════════════════════════════════════════════════════════
# 2. Checkpointy
# ══════════════════════════════════════════════════════════════════════════════

def save_checkpoint(last_index: int, results_data: dict):
    checkpoint = {"last_index": last_index, "results_data": results_data}
    with open(CHECKPOINT_E2, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)

def load_checkpoint():
    if not CHECKPOINT_E2.exists(): return None
    with open(CHECKPOINT_E2, "r", encoding="utf-8") as f:
        return json.load(f)

# ══════════════════════════════════════════════════════════════════════════════
# 3. Główna pętla
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="Eksperyment E2 – Privacy vs Utility")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-bielik", action="store_true", help="Pomiń lokalny model Bielik")
    args = parser.parse_args()

    configs = ["RegEx only", "HerBERT only", "HerBERT + RegEx", "Hybrid (Bielik 1.5)", "Hybrid (Gemini 2.5)"]
    if args.skip_bielik:
        configs.remove("Hybrid (Bielik 1.5)")

    metrics = {c: {"privacy_sum": 0.0, "utility_sum": 0.0, "count": 0} for c in configs}
    start_from = 0

    if args.resume:
        cp = load_checkpoint()
        if cp:
            start_from = cp["last_index"] + 1
            metrics = cp["results_data"]
            # Mapowanie starej nazwy na nową
            if "Hybrid (Gemini)" in metrics:
                metrics["Hybrid (Gemini 2.5)"] = metrics.pop("Hybrid (Gemini)")
            
            # Usunięcie Bielika ze słownika jeśli przekazano flagę --skip-bielik
            if args.skip_bielik and "Hybrid (Bielik 1.5)" in metrics:
                metrics.pop("Hybrid (Bielik 1.5)", None)
                
            print(f"[E2] Wznawianie od {start_from}...")
    elif CHECKPOINT_E2.exists():
        CHECKPOINT_E2.unlink()

    with open(CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)
    if args.limit: corpus = corpus[:args.limit]

    analyzer = setup_presidio_analyzer()
    privacy_engine = PresidioService(analyzer)
    
    # Inicjalizacja modeli LLM
    detection_uc_local = None
    llm_service_local = None
    model_local = None
    if "Hybrid (Bielik 1.5)" in configs:
        try:
            print("[E2] Inicjalizacja Bielik 1.5...")
            model_local = get_local_model(model_name=BIELIK_LOCAL)
            llm_service_local = LangChainService(local_llm=model_local, cloud_llm=model_local)
            detection_uc_local = DetectionUseCase(llm_service=llm_service_local, privacy_engine=privacy_engine)
            print(f"     ✔ Bielik 1.5 (Local) gotowy.")
        except Exception as e:
            print(f"     ✘ Błąd Bielik Local: {e}")
            detection_uc_local = None

    detection_uc_cloud = None
    llm_service_cloud = None
    model_cloud = None
    try:
        print("[E2] Inicjalizacja Gemini 2.5...")
        model_cloud = get_cloud_gemini_2_5_flash()
        llm_service_cloud = LangChainService(local_llm=model_cloud, cloud_llm=model_cloud)
        detection_uc_cloud = DetectionUseCase(llm_service=llm_service_cloud, privacy_engine=privacy_engine)
        print(f"     ✔ Gemini 2.5 Flash (Cloud) gotowy.")
    except Exception as e:
        print(f"     ✘ Błąd Gemini: {e}")
        detection_uc_cloud = None

    # Zapewnienie istnienia kluczy w słowniku metrics
    for name in configs:
        if name not in metrics:
            metrics[name] = {"privacy_sum": 0.0, "utility_sum": 0.0, "count": 0}

    # Dynamiczny backfill brakujących danych w punkcie kontrolnym
    missing_configs = [cfg for cfg in configs if metrics[cfg]["count"] < start_from]
    if missing_configs and start_from > 0:
        print(f"[E2] Wykryto brakujące dane dla konfiguracji: {missing_configs}")
        print(f"[E2] Rozpoczynam uzupełnianie danych (backfill) dla dokumentów 0 do {start_from - 1}...")
        
        for j in range(start_from):
            doc = corpus[j]
            text = doc["text"]
            gt = doc.get("entities", [])
            
            detailed = privacy_engine.analyze_detailed(text)
            nlp_recognizers = ["TransformersRecognizer", "CustomSpacyRecognizer", "SpacyRecognizer"]
            
            for config_name in missing_configs:
                entities = []
                if config_name == "RegEx only":
                    entities = [PIIEntity(value=e.value, label=e.label) for e in detailed if e.recognizer not in nlp_recognizers]
                elif config_name == "HerBERT only":
                    entities = [PIIEntity(value=e.value, label=e.label) for e in detailed if e.recognizer == "TransformersRecognizer"]
                elif config_name == "HerBERT + RegEx":
                    entities = [PIIEntity(value=e.value, label=e.label) for e in detailed]
                elif config_name == "Hybrid (Bielik 1.5)":
                    if detection_uc_local:
                        max_retries = 3
                        failed_bielik = False
                        for attempt in range(max_retries):
                            try:
                                entities = await asyncio.wait_for(
                                    run_hybrid_pii(detection_uc_local, llm_service_local, model_local, detailed, text),
                                    timeout=45.0
                                )
                                failed_bielik = False
                                break
                            except (asyncio.TimeoutError, Exception) as e:
                                if attempt < max_retries - 1:
                                    print(f"     [!] Problem z Bielik 1.5 w backfillu (Próba {attempt+1}/{max_retries}). Retry za 10s...")
                                    await asyncio.sleep(10.0)
                                else:
                                    print(f"     [!] Bielik 1.5 zawiódł w backfillu na dokumencie {doc['doc_id']}. Puste encje.")
                                    failed_bielik = True
                        if failed_bielik:
                            entities = []
                elif config_name == "Hybrid (Gemini 2.5)":
                    if detection_uc_cloud:
                        try:
                            entities = await run_hybrid_pii(detection_uc_cloud, llm_service_cloud, model_cloud, detailed, text)
                        except Exception as e:
                            print(f"     [!] Błąd Gemini 2.5 w backfillu na dokumencie {doc['doc_id']}: {e}. Puste encje.")
                            entities = []
                
                privacy_score = calculate_privacy_score([e.value for e in entities], gt)
                utility_score = calculate_utility_score(text, entities, privacy_engine)
                
                metrics[config_name]["privacy_sum"] += privacy_score
                metrics[config_name]["utility_sum"] += utility_score
                metrics[config_name]["count"] += 1
                
            if (j + 1) % 50 == 0:
                print(f"  - Uzupełniono {j + 1}/{start_from} dokumentów...")
        
        print(f"[E2] Zakończono uzupełnianie danych (backfill).")

    print("=" * 95)
    print("🔬 EKSPERYMENT E2 – Privacy vs Utility (Word Count Preservation)")
    print("=" * 95)

    for i in range(start_from, len(corpus)):
        doc = corpus[i]
        doc_id = doc["doc_id"]
        text = doc["text"]
        gt = doc.get("entities", [])
        
        print(f"[{i+1}/{len(corpus)}] Doc {doc_id}...")

        # Detekcja szczegółowa z Presidio
        detailed = privacy_engine.analyze_detailed(text)
        nlp_recognizers = ["TransformersRecognizer", "CustomSpacyRecognizer", "SpacyRecognizer"]
        
        detected_variants = {}
        
        # 1. RegEx only
        if "RegEx only" in configs:
            detected_variants["RegEx only"] = [PIIEntity(value=e.value, label=e.label) for e in detailed if e.recognizer not in nlp_recognizers]
        
        # 2. HerBERT only
        if "HerBERT only" in configs:
            detected_variants["HerBERT only"] = [PIIEntity(value=e.value, label=e.label) for e in detailed if e.recognizer == "TransformersRecognizer"]
            
        # 3. HerBERT + RegEx
        if "HerBERT + RegEx" in configs:
            detected_variants["HerBERT + RegEx"] = [PIIEntity(value=e.value, label=e.label) for e in detailed]
            
        # 4. Hybrid (Bielik 1.5)
        if "Hybrid (Bielik 1.5)" in configs:
            if detection_uc_local:
                max_retries = 3
                failed_bielik = False
                for attempt in range(max_retries):
                    try:
                        detected_variants["Hybrid (Bielik 1.5)"] = await asyncio.wait_for(
                            run_hybrid_pii(detection_uc_local, llm_service_local, model_local, detailed, text),
                            timeout=45.0
                        )
                        failed_bielik = False
                        break
                    except (asyncio.TimeoutError, Exception) as e:
                        if attempt < max_retries - 1:
                            print(f"     [!] Problem z Bielik 1.5 (Próba {attempt+1}/{max_retries}). Retry za 10s...")
                            await asyncio.sleep(10.0)
                        else:
                            print(f"     [!] Bielik 1.5 zawiódł na dokumencie {doc_id}. POMIJAM DOKUMENT.")
                            failed_bielik = True
                if failed_bielik:
                    continue
            else:
                detected_variants["Hybrid (Bielik 1.5)"] = []

        # 5. Hybrid (Gemini 2.5)
        if "Hybrid (Gemini 2.5)" in configs:
            if detection_uc_cloud:
                try:
                    detected_variants["Hybrid (Gemini 2.5)"] = await run_hybrid_pii(detection_uc_cloud, llm_service_cloud, model_cloud, detailed, text)
                except Exception as e:
                    print(f"     [!] Błąd Gemini na dokumencie {doc_id}: {e}. POMIJAM DOKUMENT.")
                    continue
            else:
                detected_variants["Hybrid (Gemini 2.5)"] = []

        # Aktualizacja metryk
        for name in configs:
            entities = detected_variants.get(name, [])
            pii_vals = [e.value for e in entities]
            privacy_score = calculate_privacy_score(pii_vals, gt)
            utility_score = calculate_utility_score(text, entities, privacy_engine)
            
            metrics[name]["privacy_sum"] += privacy_score
            metrics[name]["utility_sum"] += utility_score
            metrics[name]["count"] += 1

        if (i + 1) % 50 == 0:
            save_checkpoint(i, metrics)

    # Raportowanie
    print("\n" + "-" * 95)
    print(f"{'Konfiguracja':<25} | {'Privacy (Recall)':<20} | {'Utility (Word Count Preservation)':<35}")
    print("-" * 95)

    csv_rows = []
    for name in configs:
        count = metrics[name]["count"]
        avg_p = metrics[name]["privacy_sum"] / count if count > 0 else 0
        avg_u = metrics[name]["utility_sum"] / count if count > 0 else 0
        print(f"{name:<25} | {avg_p:.4f}              | {avg_u:.4f}")
        csv_rows.append({"model": name, "avg_privacy": avg_p, "avg_utility": avg_u, "doc_count": count})

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_E2_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_rows[0].keys())
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\n[E2] Wyniki zapisane w {RESULTS_E2_CSV}")
    print("=" * 95)

if __name__ == "__main__":
    asyncio.run(main())
