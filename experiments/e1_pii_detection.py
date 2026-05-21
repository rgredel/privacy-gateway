"""
e1_pii_detection.py – Eksperyment 1: Ewaluacja skuteczności detekcji PII.

Zgodnie z Rozdziałem 6.4.1 pracy magisterskiej oraz prośbą użytkownika.
Badane podejścia:
1. RegEx only (Presidio-based, filtered to patterns)
2. HerBERT only (Pure NER)
3. HerBERT + RegEx (Ensemble NER)
4. Hybrid (Ens + Bielik 1.5 - Local)
5. Hybrid (Ens + Gemini 2.5 - Cloud)

Uruchomienie:
    python experiments/e1_pii_detection.py [--limit N] [--resume]
"""

import csv
import json
import sys
import asyncio
import re
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple, Optional
from collections import defaultdict

# Wymuszenie UTF-8 na konsoli Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format='%(message)s')
# Wyłączenie logów HTTP z bibliotek zewnętrznych
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# ── Importy z projektu głównego ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.app.core.config import settings
from src.app.infrastructure.llm.factory import get_model, get_local_model, get_replicate_model, get_cloud_gemini_2_5_flash
from src.app.infrastructure.llm.langchain_service import LangChainService
from src.app.use_cases.detection_use_case import DetectionUseCase
from src.app.infrastructure.services.presidio_factory import setup_presidio_analyzer
from src.app.infrastructure.services.presidio_service import PresidioService

# Konfiguracja ścieżek
CORPUS_PATH = PROJECT_ROOT / "experiments" / "corpus" / "benchmark_corpus.json"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
RESULTS_CSV = RESULTS_DIR / "results_e1.csv"
RESULTS_PER_TYPE_CSV = RESULTS_DIR / "results_e1_per_type.csv"
CHECKPOINT_FILE = RESULTS_DIR / "checkpoint_e1.json"

# Modele
BIELIK_LOCAL = "qooba/bielik-1.5b-v3.0-instruct:Q8_0"

# ══════════════════════════════════════════════════════════════════════════════
# 1. Narzędzia detekcji
# ══════════════════════════════════════════════════════════════════════════════

def detect_regex_only(presidio_service: PresidioService, text: str) -> List[str]:
    detailed = presidio_service.analyze_detailed(text)
    nlp_recognizers = ["TransformersRecognizer", "CustomSpacyRecognizer", "SpacyRecognizer"]
    regex_entities = [ent.value for ent in detailed if ent.recognizer not in nlp_recognizers]
    return list(set(regex_entities))

def detect_herbert_only(presidio_service: PresidioService, text: str) -> List[str]:
    detailed = presidio_service.analyze_detailed(text)
    herbert_labels = ["PERSON", "LOCATION", "ORGANIZATION"]
    return list(set([ent.value for ent in detailed if ent.label in herbert_labels]))

# ══════════════════════════════════════════════════════════════════════════════
# 2. Narzędzia ewaluacji i Checkpointy
# ══════════════════════════════════════════════════════════════════════════════

def normalize(s: str) -> str:
    if not isinstance(s, str): return ""
    return s.strip().lower()

def pii_matches(detected: str, truth: str) -> bool:
    d = normalize(detected)
    t = normalize(truth)
    if not d or not t: return False
    return d == t or d in t or t in d

def compute_metrics_detailed(detected_list: List[str], gt_entities: List[Dict]) -> Dict[str, Any]:
    type_metrics = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    matched_gt_indices = set()
    matched_det_indices = set()

    for d_idx, d_text in enumerate(detected_list):
        for gt_idx, gt_ent in enumerate(gt_entities):
            if gt_idx not in matched_gt_indices and pii_matches(d_text, gt_ent["text"]):
                label = gt_ent["label"]
                type_metrics[label]["tp"] += 1
                matched_gt_indices.add(gt_idx)
                matched_det_indices.add(d_idx)
                break
    
    for gt_idx, gt_ent in enumerate(gt_entities):
        if gt_idx not in matched_gt_indices:
            label = gt_ent["label"]
            type_metrics[label]["fn"] += 1
            
    fp_count = len(detected_list) - len(matched_det_indices)
    total_tp = sum(m["tp"] for m in type_metrics.values())
    total_fn = sum(m["fn"] for m in type_metrics.values())
    
    return {
        "total": {"tp": total_tp, "fp": fp_count, "fn": total_fn},
        "per_type": type_metrics
    }

def save_checkpoint(last_index: int, stats: dict, per_type_stats: dict, skipped_docs: list):
    checkpoint = {
        "last_index": last_index,
        "stats": stats,
        "per_type_stats": {k: dict(v) for k, v in per_type_stats.items()},
        "skipped_docs": skipped_docs
    }
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)

def load_checkpoint():
    if not CHECKPOINT_FILE.exists():
        return None
    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        # Convert dict back to defaultdict
        pts = {}
        for config, label_data in data["per_type_stats"].items():
            pts[config] = defaultdict(lambda: {"tp": 0, "fn": 0}, label_data)
        data["per_type_stats"] = pts
        return data

# ══════════════════════════════════════════════════════════════════════════════
# 3. Główna pętla eksperymentu
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="Eksperyment E1 – Ewaluacja detekcji PII")
    parser.add_argument("--limit", type=int, default=None, help="Limit liczby dokumentów")
    parser.add_argument("--resume", action="store_true", help="Wznów od ostatniego checkpointu")
    args = parser.parse_args()

    # Inicjalizacja bazowa
    configurations = ["RegEx only", "HerBERT only", "HerBERT + RegEx", "Hybrid (Bielik 1.5)", "Hybrid (Gemini 2.5)"]
    stats = {config: {"tp": 0, "fp": 0, "fn": 0} for config in configurations}
    per_type_stats = {config: defaultdict(lambda: {"tp": 0, "fn": 0}) for config in configurations}
    skipped_docs = []
    start_from = 0

    if args.resume:
        cp = load_checkpoint()
        if cp:
            print(f"[E1] Wznawianie od dokumentu {cp['last_index'] + 1}...")
            start_from = cp["last_index"] + 1
            stats = cp["stats"]
            per_type_stats = cp["per_type_stats"]
            skipped_docs = cp["skipped_docs"]
        else:
            print("[E1] Brak checkpointu do wznowienia. Start od zera.")
    else:
        # Jeśli nie wznawiamy, usuwamy stary checkpoint (jeśli istnieje)
        if CHECKPOINT_FILE.exists():
            print("[E1] Usunięto stary checkpoint.")
            CHECKPOINT_FILE.unlink()

    print("=" * 95)
    print("🔬 EKSPERYMENT E1 – Ewaluacja skuteczności detekcji PII")
    print(f"   Limit dokumentów: {args.limit if args.limit else 'Brak (pełny korpus)'}")
    print("=" * 95)

    if not CORPUS_PATH.exists():
        print(f"[BŁĄD] Brak korpusu: {CORPUS_PATH}")
        sys.exit(1)

    with open(CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)
    
    if args.limit:
        corpus = corpus[:args.limit]
        
    print(f"[E1] Załadowano {len(corpus)} dokumentów do przetworzenia.\n")

    # ── Inicjalizacja komponentów ──────────────────────────────────────────
    analyzer = setup_presidio_analyzer()
    privacy_engine = PresidioService(analyzer)
    
    print("[E1] Przygotowanie modeli LLM...")
    try:
        model_local = get_local_model(model_name=BIELIK_LOCAL)
        llm_service_local = LangChainService(local_llm=model_local, cloud_llm=model_local)
        detection_uc_local = DetectionUseCase(llm_service=llm_service_local, privacy_engine=privacy_engine)
        print(f"     ✔ Bielik 1.5 (Local) gotowy.")
    except Exception as e:
        print(f"     ✘ Błąd Bielik Local: {e}")
        detection_uc_local = None

    try:
        model_cloud = get_cloud_gemini_2_5_flash()
        llm_service_cloud = LangChainService(local_llm=model_cloud, cloud_llm=model_cloud)
        detection_uc_cloud = DetectionUseCase(llm_service=llm_service_cloud, privacy_engine=privacy_engine)
        print(f"     ✔ Gemini 2.5 Flash (Cloud) gotowy.")
    except Exception as e:
        print(f"     ✘ Błąd Gemini: {e}")
        detection_uc_cloud = None

    # Przetwarzanie
    for i in range(start_from, len(corpus)):
        doc = corpus[i]
        doc_id = doc["doc_id"]
        text = doc["text"]
        gt_entities = doc.get("entities", [])
        
        print(f"[{i+1}/{len(corpus)}] Doc {doc_id} - GT: {len(gt_entities)}")

        # --- 1. RegEx only ---
        re_detected = detect_regex_only(privacy_engine, text)
        
        # --- 2. HerBERT only ---
        hr_detected = detect_herbert_only(privacy_engine, text)
        
        # --- 3. HerBERT + RegEx ---
        ens_detected = privacy_engine.get_candidates(text)
        
        # --- 4. Hybrid (Bielik 1.5) ---
        hb15_detected = []
        if detection_uc_local:
            max_retries = 3
            failed_bielik = False
            for attempt in range(max_retries):
                try:
                    hb15_detected, _ = await asyncio.wait_for(
                        detection_uc_local.execute(text, mode="hybrid"),
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
                skipped_docs.append(doc_id)
                continue

        # --- 5. Hybrid (Gemini 2.5) ---
        if detection_uc_cloud:
            try:
                hbgm_detected, _ = await detection_uc_cloud.execute(text, mode="hybrid")
            except Exception as e:
                print(f"     [!] Błąd Gemini na dokumencie {doc_id}: {e}. POMIJAM DOKUMENT.")
                skipped_docs.append(doc_id)
                continue
        else:
            hbgm_detected = []

        await asyncio.sleep(2.0)

        # Obliczanie metryk
        results = {
            "RegEx only": compute_metrics_detailed(re_detected, gt_entities),
            "HerBERT only": compute_metrics_detailed(hr_detected, gt_entities),
            "HerBERT + RegEx": compute_metrics_detailed(ens_detected, gt_entities),
            "Hybrid (Bielik 1.5)": compute_metrics_detailed(hb15_detected, gt_entities),
            "Hybrid (Gemini 2.5)": compute_metrics_detailed(hbgm_detected, gt_entities)
        }

        for config, m in results.items():
            stats[config]["tp"] += m["total"]["tp"]
            stats[config]["fp"] += m["total"]["fp"]
            stats[config]["fn"] += m["total"]["fn"]
            for label, lm in m["per_type"].items():
                per_type_stats[config][label]["tp"] += lm["tp"]
                per_type_stats[config][label]["fn"] += lm["fn"]

        # Checkpoint co 50 dokumentów
        if (i + 1) % 50 == 0:
            print(f"\n[CHECKPOINT] Zapisywanie postępu (dok: {i+1})...")
            save_checkpoint(i, stats, per_type_stats, skipped_docs)

    # ── Raportowanie wyników ──────────────────────────────────────────────
    print("\n" + "=" * 95)
    print(f"{'Konfiguracja':<25} | {'Precision':<10} | {'Recall':<10} | {'F1-score':<10}")
    print("-" * 95)

    summary_rows = []
    for config in configurations:
        tp, fp, fn = stats[config]["tp"], stats[config]["fp"], stats[config]["fn"]
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        print(f"{config:<25} | {p:.4f}     | {r:.4f}     | {f1:.4f}")
        summary_rows.append({"model": config, "precision": p, "recall": r, "f1": f1, "tp": tp, "fp": fp, "fn": fn})

    # Zapis
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
        writer.writeheader()
        writer.writerows(summary_rows)
        
    per_type_rows = []
    for label, m in sorted(per_type_stats["Hybrid (Gemini 2.5)"].items()):
        recall = m["tp"] / (m["tp"] + m["fn"]) if (m["tp"] + m["fn"]) > 0 else 0.0
        per_type_rows.append({"type": label, "tp": m["tp"], "fn": m["fn"], "recall": recall})

    with open(RESULTS_PER_TYPE_CSV, "w", encoding="utf-8", newline="") as f:
        if per_type_rows:
            writer = csv.DictWriter(f, fieldnames=per_type_rows[0].keys())
            writer.writeheader()
            writer.writerows(per_type_rows)
        
    print(f"\n[E1] Wyniki zapisane w {RESULTS_DIR}")
    if skipped_docs:
        print(f"[!] UWAGA: Pominięto {len(skipped_docs)} dokumentów: {skipped_docs}")
    print("=" * 95)

if __name__ == "__main__":
    asyncio.run(main())
