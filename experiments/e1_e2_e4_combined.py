"""
e1_e2_e4_combined.py – Połączona ewaluacja eksperymentów E1, E2 i E4.

Procesuje dokument po dokumencie i dla każdej konfiguracji:
1. Mierzy czas wykonania (latencję dla E4).
2. Pobiera wykryte encje PII.
3. Oblicza metryki dopasowania PII (TP, FP, FN dla E1).
4. Oblicza metryki prywatności i użyteczności (E2).

Zapisuje pliki wyników CSV o tradycyjnych nazwach:
- results_e1.csv, results_e1_per_type.csv
- results_e2_comparison.csv
- results_e4_comparison.csv
"""

import csv
import json
import sys
import asyncio
import re
import time
import argparse
import os
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Wymuszenie UTF-8 na Windowsie
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ustawienie ścieżek
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.app.core.config import settings
from src.app.domain.entities import PIIEntity, RecognizedEntity
from src.app.infrastructure.llm.factory import get_local_model, get_cloud_gemini_2_5_flash
from src.app.infrastructure.llm.langchain_service import LangChainService
from src.app.use_cases.detection_use_case import DetectionUseCase
from src.app.infrastructure.services.presidio_factory import setup_presidio_analyzer
from src.app.infrastructure.services.presidio_service import PresidioService

# Ścieżki do plików wyników i checkpointów
CORPUS_PATH = PROJECT_ROOT / "experiments" / "corpus" / "benchmark_corpus.json"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
RESULTS_E1_CSV = RESULTS_DIR / "results_e1.csv"
RESULTS_E1_PER_TYPE_CSV = RESULTS_DIR / "results_e1_per_type.csv"
RESULTS_E1_CONFUSION_JSON = RESULTS_DIR / "results_e1_confusion.json"
RESULTS_E2_CSV = RESULTS_DIR / "results_e2_comparison.csv"
RESULTS_E4_CSV = RESULTS_DIR / "results_e4_comparison.csv"
RESULTS_E4_SUMMARY_CSV = RESULTS_DIR / "results_e4_summary.csv"
RESULTS_DETECTIONS_COMPARISON_JSON = RESULTS_DIR / "results_detections_comparison.json"
CHECKPOINT_FILE = RESULTS_DIR / "checkpoint_combined.json"

BIELIK_LOCAL = "qooba/bielik-1.5b-v3.0-instruct:Q8_0"

# Mapa etykiet detektora na format Ground Truth
MAP_DETECTOR_TO_GT = {
    "PERSON": "PER",
    "PER": "PER",
    "LOCATION": "LOC",
    "LOC": "LOC",
    "PL_PESEL": "PESEL",
    "PESEL": "PESEL",
    "PL_NIP": "NIP",
    "NIP": "NIP",
    "PL_REGON": "REGON",
    "REGON": "REGON",
    "PL_IBAN": "ACCT",
    "ACCT": "ACCT",
    "INV": "INV"
}

ALL_GT_LABELS = ["PESEL", "REGON", "NIP", "PER", "ACCT", "INV", "LOC"]

# ══════════════════════════════════════════════════════════════════════════════
# 1. Pomocnicze funkcje normalizacji i tekstowe
# ══════════════════════════════════════════════════════════════════════════════

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
    if not isinstance(s, str):
        return ""
    return strip_polish_diacritics(s.strip().lower())

def pii_matches(detected: str, truth: str) -> bool:
    d = normalize(detected)
    t = normalize(truth)
    if not d or not t:
        return False
    return d == t or d in t or t in d

def tokenize(text: str) -> List[str]:
    return re.findall(r'\b\w+\b', text)

# ══════════════════════════════════════════════════════════════════════════════
# 2. Obliczanie metryk
# ══════════════════════════════════════════════════════════════════════════════

def compute_metrics_detailed(detected_list: List[Tuple[str, str]], gt_entities: List[Dict]) -> Dict[str, Any]:
    # Normalizacja Ground Truth
    gt_list = []
    for ent in gt_entities:
        raw_label = ent.get('label', 'UNKNOWN')
        unified = MAP_DETECTOR_TO_GT.get(raw_label, raw_label)
        value = ent.get('text', '')
        gt_list.append((value, unified))
        
    # Normalizacja wykrytych encji
    pred_list = []
    for value, raw_label in detected_list:
        unified = MAP_DETECTOR_TO_GT.get(raw_label, raw_label)
        if unified in ALL_GT_LABELS:
            pred_list.append((value, unified))
        
    gt_matched = [False] * len(gt_list)
    pred_matched = [False] * len(pred_list)
    
    tp_by_class = defaultdict(int)
    fp_by_class = defaultdict(int)
    fn_by_class = defaultdict(int)
    confusion = defaultdict(int)
    
    # Przebieg 1: Zgodność tekstu oraz klasy (True Positive)
    for i_pred, (pred_val, pred_label) in enumerate(pred_list):
        for i_gt, (gt_val, gt_label) in enumerate(gt_list):
            if gt_matched[i_gt] or pred_matched[i_pred]:
                continue
            if pred_label == gt_label and pii_matches(pred_val, gt_val):
                tp_by_class[gt_label] += 1
                confusion[(gt_label, pred_label)] += 1
                gt_matched[i_gt] = True
                pred_matched[i_pred] = True
                
    # Przebieg 2: Zgodność tekstu przy niezgodności klasy (mismatch klasy -> FP i FN)
    for i_pred, (pred_val, pred_label) in enumerate(pred_list):
        if pred_matched[i_pred]:
            continue
        for i_gt, (gt_val, gt_label) in enumerate(gt_list):
            if gt_matched[i_gt]:
                continue
            if pii_matches(pred_val, gt_val):
                fp_by_class[pred_label] += 1
                fn_by_class[gt_label] += 1
                confusion[(gt_label, pred_label)] += 1
                gt_matched[i_gt] = True
                pred_matched[i_pred] = True
                break
                
    # Niewykryte Ground Truth (False Negatives)
    for i_gt, (gt_val, gt_label) in enumerate(gt_list):
        if not gt_matched[i_gt]:
            fn_by_class[gt_label] += 1
            confusion[(gt_label, "None")] += 1
            
    # Błędnie wykryte encje (False Positives)
    for i_pred, (pred_val, pred_label) in enumerate(pred_list):
        if not pred_matched[i_pred]:
            fp_by_class[pred_label] += 1
            confusion[("None", pred_label)] += 1
            
    total_tp = sum(tp_by_class.values())
    total_fp = sum(fp_by_class.values())
    total_fn = sum(fn_by_class.values())
    
    type_metrics = {}
    for label in ALL_GT_LABELS:
        type_metrics[label] = {
            "tp": tp_by_class[label],
            "fp": fp_by_class[label],
            "fn": fn_by_class[label]
        }
        
    return {
        "total": {"tp": total_tp, "fp": total_fp, "fn": total_fn},
        "per_type": type_metrics,
        "confusion": {f"{k[0]}->{k[1]}": v for k, v in confusion.items()}
    }

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

# ══════════════════════════════════════════════════════════════════════════════
# 3. Metody detekcji i pomiaru latencji
# ══════════════════════════════════════════════════════════════════════════════

async def run_hybrid_detection(
    detection_uc: Optional[DetectionUseCase],
    text: str,
    detailed_entities: List[RecognizedEntity]
) -> List[Tuple[str, str]]:
    if not detection_uc:
        return []
    verified_pii, _ = await detection_uc.execute(text, mode="hybrid")
    val_to_label = {ent.value: ent.label for ent in detailed_entities}
    
    result = []
    for val in verified_pii:
        label = val_to_label.get(val)
        if not label:
            # Fallback label via LLM
            labeled_entities = await detection_uc.llm_service.label_pii([val], model_name=detection_uc.llm_service.local_llm.model)
            label = labeled_entities[0].label if labeled_entities else "UNKNOWN"
        result.append((val, label))
    return list(set(result))

def print_confusion_matrix(config_name: str, confusion: Dict[str, int]):
    print(f"\n--- Macierz Pomyłek dla: {config_name} (Wiersze = Ground Truth, Kolumny = Wykryte) ---")
    GT_LABELS = ["PESEL", "REGON", "NIP", "PER", "ACCT", "INV", "LOC", "None"]
    
    # Odczytanie spłaszczonych kluczy
    restored_confusion = {}
    all_pred_labels = set()
    for k_str, val in confusion.items():
        parts = k_str.split("->")
        if len(parts) == 2:
            gt, pred = parts[0], parts[1]
            restored_confusion[(gt, pred)] = val
            all_pred_labels.add(pred)
            
    cols = [c for c in GT_LABELS if c != "None"] + sorted(list(all_pred_labels - set(GT_LABELS))) + ["None"]
    
    # Nagłówek
    print(f"{'GT / Pred':<12}", end="")
    for col in cols:
        print(f" | {col[:7]:>7}", end="")
    print()
    print("-" * (12 + len(cols) * 10))
    
    for row in GT_LABELS:
        print(f"{row:<12}", end="")
        for col in cols:
            val = restored_confusion.get((row, col), 0)
            print(f" | {val:>7}", end="")
        print()
    print("-" * (12 + len(cols) * 10) + "\n")

# Bootstrap dla przedziałów ufności E1
def compute_bootstrap_ci(doc_results: List[Dict[str, int]], n_resamples: int = 10000, alpha: float = 0.05) -> Dict[str, Tuple[float, float]]:
    n_docs = len(doc_results)
    if n_docs == 0:
        return {
            'precision': (0.0, 0.0),
            'recall': (0.0, 0.0),
            'f1': (0.0, 0.0)
        }

    tps = np.array([r['tp'] for r in doc_results], dtype=np.float64)
    fps = np.array([r['fp'] for r in doc_results], dtype=np.float64)
    fns = np.array([r['fn'] for r in doc_results], dtype=np.float64)

    rng = np.random.default_rng(seed=42)
    boots_prec = np.empty(n_resamples)
    boots_rec = np.empty(n_resamples)
    boots_f1 = np.empty(n_resamples)

    eps = 1e-12
    for i in range(n_resamples):
        idx = rng.choice(n_docs, size=n_docs, replace=True)
        tp_sum = tps[idx].sum()
        fp_sum = fps[idx].sum()
        fn_sum = fns[idx].sum()
        
        p = tp_sum / (tp_sum + fp_sum + eps)
        r = tp_sum / (tp_sum + fn_sum + eps)
        f1 = 2 * p * r / (p + r + eps)
        
        boots_prec[i] = p
        boots_rec[i] = r
        boots_f1[i] = f1

    lower_q = (alpha / 2) * 100
    upper_q = (1 - alpha / 2) * 100
    
    return {
        'precision': (float(np.percentile(boots_prec, lower_q)), float(np.percentile(boots_prec, upper_q))),
        'recall': (float(np.percentile(boots_rec, lower_q)), float(np.percentile(boots_rec, upper_q))),
        'f1': (float(np.percentile(boots_f1, lower_q)), float(np.percentile(boots_f1, upper_q)))
    }

# ══════════════════════════════════════════════════════════════════════════════
# 4. Główna pętla
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="Zoptymalizowany, połączony eksperyment E1, E2 i E4")
    parser.add_argument("--limit", type=int, default=None, help="Limit dokumentów do ewaluacji")
    parser.add_argument("--resume", action="store_true", help="Wznów ewaluację z pliku checkpoint")
    parser.add_argument("--skip-bielik", action="store_true", help="Pomiń lokalny model Bielik")
    args = parser.parse_args()

    # Zdefiniowane konfiguracje
    configs = ["RegEx only", "HerBERT only", "HerBERT + RegEx", "Hybrid (Bielik 1.5)", "Hybrid (Gemini 2.5)"]
    if args.skip_bielik:
        configs.remove("Hybrid (Bielik 1.5)")

    # Nazwy kluczy dla E4
    e4_mapping = {
        "RegEx only": "regex",
        "HerBERT only": "herbert",
        "HerBERT + RegEx": "ener",
        "Hybrid (Bielik 1.5)": "hybrid_bielik",
        "Hybrid (Gemini 2.5)": "hybrid_gemini"
    }

    start_from = 0
    saved_doc_results = []
    skipped_docs = []

    if args.resume and CHECKPOINT_FILE.exists():
        print(f"🔄 Wczytywanie punktu kontrolnego z {CHECKPOINT_FILE.name}...")
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                cp = json.load(f)
                start_from = cp["last_index"] + 1
                saved_doc_results = cp.get("results", [])
                skipped_docs = cp.get("skipped_docs", [])
                print(f"     ✔ Wznowiono od dokumentu o indeksie {start_from} (przetworzono {len(saved_doc_results)}).")
        except Exception as e:
            print(f"     ✘ Nie udało się wczytać checkpointu: {e}. Start od zera.")
            start_from = 0
    elif CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()

    # Wczytanie korpusu
    if not CORPUS_PATH.exists():
        print(f"Błąd: Nie znaleziono korpusu {CORPUS_PATH}")
        sys.exit(1)

    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    if args.limit:
        corpus = corpus[:args.limit]

    print(f"Załadowano {len(corpus)} dokumentów do ewaluacji.")

    # Inicjalizacja Presidio i LLM
    print("[INIT] Przygotowanie Presidio...")
    analyzer = setup_presidio_analyzer()
    privacy_engine = PresidioService(analyzer)

    print("[INIT] Inicjalizacja modeli LLM...")
    detection_uc_local = None
    model_local = None
    if "Hybrid (Bielik 1.5)" in configs:
        try:
            model_local = get_local_model(model_name=BIELIK_LOCAL)
            llm_service_local = LangChainService(local_llm=model_local, cloud_llm=model_local)
            detection_uc_local = DetectionUseCase(llm_service=llm_service_local, privacy_engine=privacy_engine)
            print("     ✔ Bielik 1.5 gotowy.")
        except Exception as e:
            print(f"     ✘ Błąd inicjalizacji Bielika: {e}")

    detection_uc_cloud = None
    model_cloud = None
    try:
        model_cloud = get_cloud_gemini_2_5_flash()
        llm_service_cloud = LangChainService(local_llm=model_cloud, cloud_llm=model_cloud)
        detection_uc_cloud = DetectionUseCase(llm_service=llm_service_cloud, privacy_engine=privacy_engine)
        print("     ✔ Gemini 2.5 gotowy.")
    except Exception as e:
        print(f"     ✘ Błąd inicjalizacji Gemini: {e}")

    # Pętla główna
    for i in range(start_from, len(corpus)):
        doc = corpus[i]
        doc_id = doc.get("doc_id", i)
        text = doc["text"]
        gt = doc.get("entities", [])

        print(f"\n📄 [{i+1}/{len(corpus)}] ID: {doc_id} (Długość: {len(text)} znaków, GT: {len(gt)})")
        
        doc_res = {"doc_id": doc_id}
        doc_skipped = False

        # ─── 0. Pre-run Presidio w celu pobrania pełnych encji (wymagane przez Hybrid) ───
        start_detailed = time.perf_counter()
        detailed = privacy_engine.analyze_detailed(text)
        detailed_latency = time.perf_counter() - start_detailed

        for cfg in configs:
            print(f"    -> {cfg:<22}...", end="", flush=True)
            detected = []
            latency = 0.0

            try:
                if cfg == "RegEx only":
                    start_t = time.perf_counter()
                    nlp_recs = ["TransformersRecognizer", "CustomSpacyRecognizer", "SpacyRecognizer"]
                    # Filtrujemy tylko regex-owe rozpoznawacze
                    recognizers = [r for r in privacy_engine.analyzer.registry.get_recognizers(language="pl", all_fields=True) if r.name not in nlp_recs]
                    results = []
                    for r in recognizers:
                        res = r.analyze(text, entities=r.supported_entities)
                        if res:
                            results.extend(res)
                    detected = [(ent.value if hasattr(ent, 'value') else text[ent.start:ent.end], ent.entity_type) for ent in results]
                    latency = time.perf_counter() - start_t

                elif cfg == "HerBERT only":
                    start_t = time.perf_counter()
                    herbert_entities = ["PERSON", "LOCATION", "ORGANIZATION"]
                    detailed_herbert = privacy_engine.analyze_detailed(text, entities=herbert_entities)
                    detected = [(ent.value, ent.label) for ent in detailed_herbert if ent.recognizer == "TransformersRecognizer"]
                    latency = time.perf_counter() - start_t

                elif cfg == "HerBERT + RegEx":
                    # Używamy całego Presidio (Regex + Herbert)
                    detected = [(ent.value, ent.label) for ent in detailed]
                    latency = detailed_latency

                elif cfg == "Hybrid (Bielik 1.5)":
                    if not detection_uc_local:
                        print(" SKIPPED (Brak modelu)")
                        continue
                    max_retries = 3
                    success = False
                    start_t = time.perf_counter()
                    for attempt in range(max_retries):
                        try:
                            detected = await asyncio.wait_for(
                                run_hybrid_detection(detection_uc_local, text, detailed),
                                timeout=45.0
                            )
                            success = True
                            break
                        except Exception as e:
                            print(f"\n        [!] Bielik retry {attempt+1}: {e}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(10.0)
                    latency = time.perf_counter() - start_t
                    if not success:
                        print(" FAILED")
                        doc_skipped = True
                        break

                elif cfg == "Hybrid (Gemini 2.5)":
                    if not detection_uc_cloud:
                        print(" SKIPPED (Brak API)")
                        continue
                    max_retries = 3
                    success = False
                    start_t = time.perf_counter()
                    for attempt in range(max_retries):
                        try:
                            detected = await asyncio.wait_for(
                                run_hybrid_detection(detection_uc_cloud, text, detailed),
                                timeout=45.0
                            )
                            success = True
                            break
                        except Exception as e:
                            print(f"\n        [!] Gemini retry {attempt+1}: {e}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(10.0)
                    latency = time.perf_counter() - start_t
                    if not success:
                        print(" FAILED")
                        doc_skipped = True
                        break

                print(f" DONE ({latency:.3f}s, wykryto {len(detected)})")

                # Obliczenie metryk E1 per dokument
                e1_m = compute_metrics_detailed(detected, gt)

                # Obliczenie metryk E2 per dokument
                pii_vals = [d[0] for d in detected]
                privacy_score = calculate_privacy_score(pii_vals, gt)
                pii_entities = [PIIEntity(value=d[0], label=d[1]) for d in detected]
                utility_score = calculate_utility_score(text, pii_entities, privacy_engine)

                # Zapis do doc_res
                doc_res[cfg] = {
                    "latency": latency,
                    "detected": detected,
                    "e1_metrics": {
                        "tp": e1_m["total"]["tp"],
                        "fp": e1_m["total"]["fp"],
                        "fn": e1_m["total"]["fn"],
                        "per_type": e1_m["per_type"],
                        "confusion": e1_m["confusion"]
                    },
                    "privacy": privacy_score,
                    "utility": utility_score
                }

            except Exception as e:
                print(f" ERROR: {e}")
                doc_skipped = True
                break

        if doc_skipped:
            print(f"⚠️ Pomijam dokument {doc_id} ze względu na błędy.")
            skipped_docs.append(doc_id)
            continue

        saved_doc_results.append(doc_res)

        # Zapis checkpointu
        checkpoint_data = {
            "last_index": i,
            "results": saved_doc_results,
            "skipped_docs": skipped_docs
        }
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

    # ══════════════════════════════════════════════════════════════════════════════
    # 5. Agregacja i zapisywanie wyników końcowych
    # ══════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("🏁 EKSPERYMENTY ZAKOŃCZONE – AGREGACJA WYNIKÓW")
    print("=" * 90)

    # ─── AGREGACJA E1 ───
    summary_rows_e1 = []
    per_type_rows_e1 = []
    confusion_matrices = {}

    for cfg in configs:
        doc_metrics_list = []
        accumulated_tp = 0
        accumulated_fp = 0
        accumulated_fn = 0
        
        per_type_accumulated = {label: {"tp": 0, "fp": 0, "fn": 0} for label in ALL_GT_LABELS}
        merged_confusion = defaultdict(int)

        for doc_res in saved_doc_results:
            if cfg not in doc_res:
                continue
            m = doc_res[cfg]["e1_metrics"]
            doc_metrics_list.append({
                "tp": m["tp"],
                "fp": m["fp"],
                "fn": m["fn"]
            })
            accumulated_tp += m["tp"]
            accumulated_fp += m["fp"]
            accumulated_fn += m["fn"]

            # Per klasa
            for label in ALL_GT_LABELS:
                lm = m["per_type"].get(label, {"tp": 0, "fp": 0, "fn": 0})
                per_type_accumulated[label]["tp"] += lm["tp"]
                per_type_accumulated[label]["fp"] += lm["fp"]
                per_type_accumulated[label]["fn"] += lm["fn"]

            # Confusion Matrix
            for k_str, val in m["confusion"].items():
                merged_confusion[k_str] += val

        confusion_matrices[cfg] = dict(merged_confusion)

        # Bootstrap CIs
        ci = compute_bootstrap_ci(doc_metrics_list, n_resamples=10000)

        eps = 1e-12
        p = accumulated_tp / (accumulated_tp + accumulated_fp + eps)
        r = accumulated_tp / (accumulated_tp + accumulated_fn + eps)
        f1 = 2 * p * r / (p + r + eps)

        summary_rows_e1.append({
            "model": cfg,
            "precision": p,
            "precision_ci_low": ci['precision'][0],
            "precision_ci_high": ci['precision'][1],
            "recall": r,
            "recall_ci_low": ci['recall'][0],
            "recall_ci_high": ci['recall'][1],
            "f1": f1,
            "f1_ci_low": ci['f1'][0],
            "f1_ci_high": ci['f1'][1],
            "tp": accumulated_tp,
            "fp": accumulated_fp,
            "fn": accumulated_fn
        })

        # Zapis per-klasa
        for label in ALL_GT_LABELS:
            lm = per_type_accumulated[label]
            tp_c = lm["tp"]
            fp_c = lm["fp"]
            fn_c = lm["fn"]
            
            p_c = tp_c / (tp_c + fp_c) if (tp_c + fp_c) > 0 else 0.0
            r_c = tp_c / (tp_c + fn_c) if (tp_c + fn_c) > 0 else 0.0
            f1_c = 2 * p_c * r_c / (p_c + r_c) if (p_c + r_c) > 0 else 0.0
            fnr_c = fn_c / (tp_c + fn_c) if (tp_c + fn_c) > 0 else 0.0

            per_type_rows_e1.append({
                "model": cfg,
                "type": label,
                "precision": p_c,
                "recall": r_c,
                "f1": f1_c,
                "fnr": fnr_c,
                "tp": tp_c,
                "fp": fp_c,
                "fn": fn_c
            })

    # Zapis CSV E1
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_E1_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary_rows_e1[0].keys())
        writer.writeheader()
        writer.writerows(summary_rows_e1)

    with open(RESULTS_E1_PER_TYPE_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=per_type_rows_e1[0].keys())
        writer.writeheader()
        writer.writerows(per_type_rows_e1)

    # Drukowanie macierzy pomyłek dla diagnostyki
    for cfg in configs:
        print_confusion_matrix(cfg, confusion_matrices[cfg])

    # Zapis confusion matrices do pliku JSON (dla tabel LaTeX)
    with open(RESULTS_E1_CONFUSION_JSON, "w", encoding="utf-8") as f:
        json.dump(confusion_matrices, f, ensure_ascii=False, indent=2)
    print(f"  - Macierze pomyłek: {RESULTS_E1_CONFUSION_JSON.name}")

    # ─── AGREGACJA E2 ───
    summary_rows_e2 = []
    for cfg in configs:
        scores_p = []
        scores_u = []
        for doc_res in saved_doc_results:
            if cfg in doc_res:
                scores_p.append(doc_res[cfg]["privacy"])
                scores_u.append(doc_res[cfg]["utility"])
        
        avg_p = float(np.mean(scores_p)) if scores_p else 1.0
        avg_u = float(np.mean(scores_u)) if scores_u else 1.0
        summary_rows_e2.append({
            "model": cfg,
            "avg_privacy": avg_p,
            "avg_utility": avg_u,
            "doc_count": len(scores_p)
        })

    with open(RESULTS_E2_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary_rows_e2[0].keys())
        writer.writeheader()
        writer.writerows(summary_rows_e2)

    # ─── AGREGACJA E4 ───
    # Zapiszmy wyniki szczegółowe latencji (jeden wiersz na dokument)
    # Kolumny: doc_id, regex, herbert, ener, hybrid_gemini, hybrid_bielik
    summary_rows_e4 = []
    for doc_res in saved_doc_results:
        row = {"doc_id": doc_res["doc_id"]}
        for cfg in configs:
            col_name = e4_mapping[cfg]
            if cfg in doc_res:
                row[col_name] = doc_res[cfg]["latency"]
            else:
                row[col_name] = ""
        summary_rows_e4.append(row)

    with open(RESULTS_E4_CSV, "w", encoding="utf-8", newline="") as f:
        # Piszemy z nagłówkami e4
        headers = ["doc_id"] + [e4_mapping[cfg] for cfg in configs]
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(summary_rows_e4)

    # ─── AGREGACJA E4 SUMMARY (P50, P95, Pamięć) ───
    e4_summary_rows = []
    for cfg in configs:
        times = []
        for doc_res in saved_doc_results:
            if cfg in doc_res and doc_res[cfg]["latency"]:
                times.append(doc_res[cfg]["latency"])
        if times:
            p50 = float(np.percentile(times, 50))
            p95 = float(np.percentile(times, 95))
        else:
            p50 = None
            p95 = None

        # Pomiar pamięci – odczyt peak RSS procesu
        mem_mb = None
        if HAS_PSUTIL:
            try:
                process = psutil.Process(os.getpid())
                mem_mb = round(process.memory_info().rss / (1024 * 1024), 1)
            except Exception:
                pass

        e4_summary_rows.append({
            "model": cfg,
            "p50_s": f"{p50:.3f}" if p50 is not None else "N/A",
            "p95_s": f"{p95:.3f}" if p95 is not None else "N/A",
            "avg_s": f"{float(np.mean(times)):.3f}" if times else "N/A",
            "min_s": f"{float(np.min(times)):.3f}" if times else "N/A",
            "max_s": f"{float(np.max(times)):.3f}" if times else "N/A",
            "memory_mb": mem_mb if mem_mb is not None else "N/A",
            "n_samples": len(times)
        })

    with open(RESULTS_E4_SUMMARY_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=e4_summary_rows[0].keys())
        writer.writeheader()
        writer.writerows(e4_summary_rows)

    # Drukowanie tabelki E4 summary
    print("\n--- Podsumowanie E4 (Latency & Memory) ---")
    print(f"{'Model':<25} | {'P50 [s]':>8} | {'P95 [s]':>8} | {'Avg [s]':>8} | {'Mem [MB]':>9} | N")
    print("-" * 80)
    for row in e4_summary_rows:
        print(f"{row['model']:<25} | {row['p50_s']:>8} | {row['p95_s']:>8} | {row['avg_s']:>8} | {str(row['memory_mb']):>9} | {row['n_samples']}")

    # ─── AGREGACJA PORÓWNANIA DETEKCJI (Ground Truth vs Wykryte) ───
    corpus_by_id = {doc.get("doc_id", idx): doc for idx, doc in enumerate(corpus)}
    detections_comparison = []
    for doc_res in saved_doc_results:
        doc_id = doc_res["doc_id"]
        doc_data = corpus_by_id.get(doc_id)
        doc_text = doc_data["text"] if doc_data else ""
        gt_entities = doc_data.get("entities", []) if doc_data else []
        
        comparison_entry = {
            "doc_id": doc_id,
            "text": doc_text,
            "ground_truth": [
                {
                    "text": ent.get("text", ""),
                    "label": ent.get("label", ""),
                    "unified_label": MAP_DETECTOR_TO_GT.get(ent.get("label", ""), ent.get("label", ""))
                }
                for ent in gt_entities
            ],
            "detections": {
                cfg: [
                    {
                        "text": val,
                        "label": lbl,
                        "unified_label": MAP_DETECTOR_TO_GT.get(lbl, lbl)
                    }
                    for val, lbl in doc_res[cfg]["detected"]
                ]
                for cfg in configs if cfg in doc_res
            }
        }
        detections_comparison.append(comparison_entry)
        
    with open(RESULTS_DETECTIONS_COMPARISON_JSON, "w", encoding="utf-8") as f:
        json.dump(detections_comparison, f, ensure_ascii=False, indent=2)

    # Czyszczenie checkpointu po udanym zakończeniu
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()

    print("\n✅ Wszystkie pliki wynikowe zostały zapisane pomyślnie w:")
    print(f"  - E1: {RESULTS_E1_CSV.name}, {RESULTS_E1_PER_TYPE_CSV.name}, {RESULTS_E1_CONFUSION_JSON.name}")
    print(f"  - E2: {RESULTS_E2_CSV.name}")
    print(f"  - E4: {RESULTS_E4_CSV.name}, {RESULTS_E4_SUMMARY_CSV.name}")
    print(f"  - Porównanie detekcji: {RESULTS_DETECTIONS_COMPARISON_JSON.name}")
    print("=" * 90)

if __name__ == "__main__":
    asyncio.run(main())
