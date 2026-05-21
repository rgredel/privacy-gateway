"""
e2_utility_analysis.py – Eksperyment 2: Analiza kompromisu prywatność-użyteczność.

Zgodnie z Rozdziałem 6.2.2 pracy magisterskiej.
Badamy kompromis:
1. Privacy Score: % poprawnie zamaskowanych PII (Recall).
2. Utility Score: % zachowanych słów/danych niebędących PII (1 - False Positive Rate).

Wersja z poprawioną definicją użyteczności (Token-based Utility).
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

# ── Importy z projektu głównego ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.app.core.config import settings
from src.app.infrastructure.llm.factory import get_cloud_gemini_2_5_flash
from src.app.infrastructure.llm.langchain_service import LangChainService
from src.app.use_cases.detection_use_case import DetectionUseCase
from src.app.infrastructure.services.presidio_factory import setup_presidio_analyzer
from src.app.infrastructure.services.presidio_service import PresidioService

# Konfiguracja ścieżek
CORPUS_PATH = PROJECT_ROOT / "experiments" / "corpus" / "benchmark_corpus.json"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
RESULTS_E2_CSV = RESULTS_DIR / "results_e2_comparison.csv"
CHECKPOINT_E2 = RESULTS_DIR / "checkpoint_e2.json"

# ══════════════════════════════════════════════════════════════════════════════
# 1. Narzędzia analityczne
# ══════════════════════════════════════════════════════════════════════════════

def tokenize(text: str) -> List[str]:
    """Prosta tokenizacja na słowa i liczby."""
    return re.findall(r'\b\w+\b', text)

def get_metrics_v2(detected_pii: List[str], gt_entities: List[Dict], text: str) -> Dict[str, float]:
    """Oblicza Privacy Score (Recall) i Utility Score (1 - FP rate)."""
    
    # --- Privacy Score (Recall) ---
    gt_texts = [e["text"].strip().lower() for e in gt_entities]
    if not gt_texts:
        privacy_score = 1.0
    else:
        tp = 0
        matched_gt = set()
        for d in detected_pii:
            d_norm = d.strip().lower()
            for i, gt_t in enumerate(gt_texts):
                if i not in matched_gt and (d_norm == gt_t or d_norm in gt_t or gt_t in d_norm):
                    tp += 1
                    matched_gt.add(i)
                    break
        privacy_score = tp / len(gt_texts)

    # --- Utility Score (Preservation of Non-PII) ---
    # Definicja: Utility = 1 - (Liczba False Positives / Liczba wszystkich słów nie-PII)
    
    # Znajdź wszystkie słowa w tekście
    all_tokens = tokenize(text)
    if not all_tokens: return {"privacy": privacy_score, "utility": 1.0}
    
    # Zidentyfikuj które słowa są częścią PII w Ground Truth
    pii_words_gt = set()
    for gt in gt_entities:
        for word in tokenize(gt["text"]):
            pii_words_gt.add(word.lower())
            
    # Policz słowa które NIE są PII (nasza baza użyteczności)
    non_pii_tokens = [t for t in all_tokens if t.lower() not in pii_words_gt]
    if not non_pii_tokens:
        utility_score = 1.0 # Brak danych nie-PII do stracenia
    else:
        # Policz False Positives (to co wykryliśmy, a nie jest w GT)
        fp_count = 0
        for d in detected_pii:
            is_fp = True
            d_norm = d.strip().lower()
            for gt_t in gt_texts:
                if d_norm == gt_t or d_norm in gt_t or gt_t in d_norm:
                    is_fp = False
                    break
            if is_fp:
                # Każde słowo w FP liczymy jako stratę użyteczności
                fp_count += len(tokenize(d))
        
        # Utility = 1 - (FP / Liczba nie-PII)
        # Ograniczamy do [0, 1]
        loss = fp_count / len(all_tokens) # Relatywna strata w stosunku do całego tekstu
        utility_score = max(0.0, 1.0 - loss)

    return {
        "privacy": privacy_score,
        "utility": utility_score
    }

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
    args = parser.parse_args()

    # Inicjalizacja
    configs = ["RegEx only", "HerBERT only", "Hybrid (Gemini)"]
    metrics = {c: {"privacy_sum": 0.0, "utility_sum": 0.0, "count": 0} for c in configs}
    start_from = 0

    if args.resume:
        cp = load_checkpoint()
        if cp:
            start_from = cp["last_index"] + 1
            metrics = cp["results_data"]
            print(f"[E2] Wznawianie od {start_from}...")
    elif CHECKPOINT_E2.exists():
        CHECKPOINT_E2.unlink()

    # Ładowanie danych
    with open(CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)
    if args.limit: corpus = corpus[:args.limit]

    # Komponenty
    analyzer = setup_presidio_analyzer()
    privacy_engine = PresidioService(analyzer)
    
    model_gemini = get_cloud_gemini_2_5_flash()
    llm_service = LangChainService(local_llm=model_gemini, cloud_llm=model_gemini)
    detection_uc = DetectionUseCase(llm_service=llm_service, privacy_engine=privacy_engine)

    print("=" * 95)
    print("🔬 EKSPERYMENT E2 – Privacy vs Utility (Token-Based Analysis)")
    print("=" * 95)

    # Przetwarzanie
    for i in range(start_from, len(corpus)):
        doc = corpus[i]
        text = doc["text"]
        gt = doc.get("entities", [])
        
        print(f"[{i+1}/{len(corpus)}] Doc {doc['doc_id']}...")

        # Wykrywanie
        detailed = privacy_engine.analyze_detailed(text)
        
        # Rozdzielamy po etykietach (Labels) - to jest najpewniejsza metoda
        ner_labels = ["PERSON", "LOCATION", "ORGANIZATION"]
        
        # 1. RegEx only: Wszystko co NIE jest z modelu NER
        re_pii = [e.value for e in detailed if e.label not in ner_labels]
        
        # 2. HerBERT only: Tylko etykiety NER
        hr_pii = [e.value for e in detailed if e.label in ner_labels]
        
        # 3. Hybrid (Gemini)
        try:
            hy_pii, _ = await detection_uc.execute(text, mode="hybrid")
        except Exception as e:
            print(f"     [!] Błąd Gemini: {e}. Pomijam dokument.")
            continue

        variants = {
            "RegEx only": re_pii,
            "HerBERT only": hr_pii,
            "Hybrid (Gemini)": hy_pii
        }

        for name, pii_found in variants.items():
            m = get_metrics_v2(pii_found, gt, text)
            metrics[name]["privacy_sum"] += m["privacy"]
            metrics[name]["utility_sum"] += m["utility"]
            metrics[name]["count"] += 1

        if (i + 1) % 50 == 0:
            save_checkpoint(i, metrics)

    # Raport
    print("\n" + "-" * 95)
    print(f"{'Konfiguracja':<20} | {'Privacy (Recall)':<20} | {'Utility (Preservation)':<20}")
    print("-" * 95)

    csv_rows = []
    for name in configs:
        count = metrics[name]["count"]
        avg_p = metrics[name]["privacy_sum"] / count if count > 0 else 0
        avg_u = metrics[name]["utility_sum"] / count if count > 0 else 0
        print(f"{name:<20} | {avg_p:.4f}              | {avg_u:.4f}")
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
