"""
e1_pii_detection.py – Eksperyment 1: Ewaluacja skuteczności detekcji PII.

Zgodnie z Rozdziałem 6 pracy magisterskiej oraz zaleceniami promotora.
Ulepszona wersja:
1. Zliczanie rozkładu klas w korpusie na starcie.
2. Naprawione filtrowanie recognizerów NLP (właściwa filtracja po ent.recognizer).
3. Dwufazowe dopasowanie (TP, FP, FN, macierze pomyłek z wartościami poza przekątną).
4. Obliczanie przedziałów ufności bootstrapowych (10 000 powtórzeń) dla Precision, Recall i F1.
5. Pełne tabele per-klasa i macierze pomyłek dla wszystkich badanych modeli.
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
import numpy as np

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
from src.app.infrastructure.llm.factory import get_model, get_local_model, get_cloud_gemini_2_5_flash
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

# Słownik unifikujący etykiety detektorów i Ground Truth
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

# ══════════════════════════════════════════════════════════════════════════════
# 1. Narzędzia detekcji i pomocnicze
# ══════════════════════════════════════════════════════════════════════════════

def print_and_get_corpus_distribution(corpus: List[Dict]) -> Dict[str, int]:
    counts = defaultdict(int)
    for doc in corpus:
        for ent in doc.get("entities", []):
            counts[ent["label"]] += 1
            
    print("=" * 60)
    print("📊 ROZKŁAD KLAS W KORPUSIE TESTOWYM")
    print("-" * 60)
    print(f"{'Klasa PII':<20} | {'Liczba wystąpień':<15}")
    print("-" * 60)
    for label, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        print(f"{label:<20} | {count:<15}")
    print("-" * 60)
    print(f"{'SUMA':<20} | {sum(counts.values()):<15}")
    print("=" * 60 + "\n")
    return dict(counts)

def detect_regex_only(presidio_service: PresidioService, text: str) -> List[Tuple[str, str]]:
    detailed = presidio_service.analyze_detailed(text)
    nlp_recognizers = ["TransformersRecognizer", "CustomSpacyRecognizer", "SpacyRecognizer"]
    regex_entities = [(ent.value, ent.label) for ent in detailed if ent.recognizer not in nlp_recognizers]
    return list(set(regex_entities))

def detect_herbert_only(presidio_service: PresidioService, text: str) -> List[Tuple[str, str]]:
    detailed = presidio_service.analyze_detailed(text)
    return list(set([(ent.value, ent.label) for ent in detailed if ent.recognizer == "TransformersRecognizer"]))

def detect_ensemble(presidio_service: PresidioService, text: str) -> List[Tuple[str, str]]:
    detailed = presidio_service.analyze_detailed(text)
    return list(set([(ent.value, ent.label) for ent in detailed]))

async def detect_hybrid(detection_uc: Optional[DetectionUseCase], presidio_service: PresidioService, text: str) -> List[Tuple[str, str]]:
    if not detection_uc:
        return []
    # Wywołanie potoku hybrydowego
    verified_pii, _ = await detection_uc.execute(text, mode="hybrid")
    detailed = presidio_service.analyze_detailed(text)
    
    val_to_label = {}
    for ent in detailed:
        val_to_label[ent.value] = ent.label
        
    result = []
    for val in verified_pii:
        label = val_to_label.get(val)
        if not label:
            # Fallback: ponowne zaetykietowanie przez LLM
            labeled_entities = await detection_uc.llm_service.label_pii([val], model_name=detection_uc.llm_service.local_llm.model)
            if labeled_entities:
                label = labeled_entities[0].label
            else:
                label = "UNKNOWN"
        result.append((val, label))
    return list(set(result))

# ══════════════════════════════════════════════════════════════════════════════
# 2. Ewaluacja, Bootstrap i Checkpointy
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
    if not isinstance(s, str): return ""
    return strip_polish_diacritics(s.strip().lower())

def pii_matches(detected: str, truth: str) -> bool:
    d = normalize(detected)
    t = normalize(truth)
    if not d or not t: return False
    return d == t or d in t or t in d

def compute_metrics_detailed(detected_list: List[Tuple[str, str]], gt_entities: List[Dict]) -> Dict[str, Any]:
    ALL_GT_LABELS = ["PESEL", "REGON", "NIP", "PER", "ACCT", "INV", "LOC"]
    
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
        "confusion": dict(confusion)
    }

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

def print_confusion_matrix(config_name: str, confusion: Dict[Tuple[str, str], int]):
    print(f"\n--- Macierz Pomyłek dla: {config_name} (Wiersze = Ground Truth, Kolumny = Wykryte) ---")
    
    GT_LABELS = ["PESEL", "REGON", "NIP", "PER", "ACCT", "INV", "LOC", "None"]
    
    all_pred_labels = set()
    for (gt, pred) in confusion.keys():
        all_pred_labels.add(pred)
        
    cols = [c for c in GT_LABELS if c != "None"] + sorted(list(all_pred_labels - set(GT_LABELS))) + ["None"]
    rows = GT_LABELS
    
    # Nagłówek
    print(f"{'GT / Pred':<12}", end="")
    for col in cols:
        print(f" | {col[:7]:>7}", end="")
    print()
    print("-" * (12 + len(cols) * 10))
    
    for row in rows:
        print(f"{row:<12}", end="")
        for col in cols:
            val = confusion.get((row, col), 0)
            print(f" | {val:>7}", end="")
        print()
    print("-" * (12 + len(cols) * 10))

def save_checkpoint(last_index: int, stats: dict, per_type_stats: dict, confusion_matrices: dict, doc_metrics: dict, skipped_docs: list):
    serialized_confusion = {}
    for config, matrix in confusion_matrices.items():
        serialized_confusion[config] = {f"{r},{c}": val for (r, c), val in matrix.items()}
        
    checkpoint = {
        "last_index": last_index,
        "stats": stats,
        "per_type_stats": {cfg: {lbl: dict(v) for lbl, v in labels.items()} for cfg, labels in per_type_stats.items()},
        "confusion_matrices": serialized_confusion,
        "doc_metrics": doc_metrics,
        "skipped_docs": skipped_docs
    }
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)

def load_checkpoint():
    if not CHECKPOINT_FILE.exists():
        return None
    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    parsed_confusion = {}
    for config, matrix in data.get("confusion_matrices", {}).items():
        parsed_confusion[config] = defaultdict(int)
        for k, val in matrix.items():
            parts = k.split(",")
            r = parts[0]
            c = parts[1]
            parsed_confusion[config][(r, c)] = val
            
    data["confusion_matrices"] = parsed_confusion
    
    pts = {}
    for config, label_data in data["per_type_stats"].items():
        pts[config] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
        for lbl, counts in label_data.items():
            pts[config][lbl] = counts
    data["per_type_stats"] = pts
    
    return data

# ══════════════════════════════════════════════════════════════════════════════
# 3. Główna pętla eksperymentu
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="Eksperyment E1 – Ewaluacja detekcji PII")
    parser.add_argument("--limit", type=int, default=None, help="Limit liczby dokumentów")
    parser.add_argument("--resume", action="store_true", help="Wznów od ostatniego checkpointu")
    parser.add_argument("--skip-bielik", action="store_true", help="Pomiń lokalny model Bielik")
    args = parser.parse_args()

    configurations = ["RegEx only", "HerBERT only", "HerBERT + RegEx", "Hybrid (Bielik 1.5)", "Hybrid (Gemini 2.5)"]
    if args.skip_bielik:
        configurations.remove("Hybrid (Bielik 1.5)")
        
    stats = {config: {"tp": 0, "fp": 0, "fn": 0} for config in configurations}
    per_type_stats = {config: defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0}) for config in configurations}
    confusion_matrices = {config: defaultdict(int) for config in configurations}
    doc_metrics = {config: [] for config in configurations}
    skipped_docs = []
    start_from = 0

    if args.resume:
        cp = load_checkpoint()
        if cp:
            print(f"[E1] Wznawianie od dokumentu {cp['last_index'] + 1}...")
            start_from = cp["last_index"] + 1
            stats = cp["stats"]
            per_type_stats = cp["per_type_stats"]
            confusion_matrices = cp["confusion_matrices"]
            doc_metrics = cp["doc_metrics"]
            skipped_docs = cp["skipped_docs"]
            # Jeśli wznawiamy ze skip-bielik, odfiltruj go ze słowników
            for cfg in list(stats.keys()):
                if cfg not in configurations:
                    stats.pop(cfg, None)
                    per_type_stats.pop(cfg, None)
                    confusion_matrices.pop(cfg, None)
                    doc_metrics.pop(cfg, None)
        else:
            print("[E1] Brak checkpointu do wznowienia. Start od zera.")
    else:
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
    
    # 1. Zliczanie liczności klas w całym korpusie
    print_and_get_corpus_distribution(corpus)
    
    if args.limit:
        corpus = corpus[:args.limit]
        
    print(f"[E1] Załadowano {len(corpus)} dokumentów do przetworzenia.\n")

    # ── Inicjalizacja komponentów ──────────────────────────────────────────
    analyzer = setup_presidio_analyzer()
    privacy_engine = PresidioService(analyzer)
    
    print("[E1] Przygotowanie modeli LLM...")
    detection_uc_local = None
    if "Hybrid (Bielik 1.5)" in configurations:
        try:
            model_local = get_local_model(model_name=BIELIK_LOCAL)
            llm_service_local = LangChainService(local_llm=model_local, cloud_llm=model_local)
            detection_uc_local = DetectionUseCase(llm_service=llm_service_local, privacy_engine=privacy_engine)
            print(f"     ✔ Bielik 1.5 (Local) gotowy.")
        except Exception as e:
            print(f"     ✘ Błąd Bielik Local: {e}")
            detection_uc_local = None

    detection_uc_cloud = None
    try:
        model_cloud = get_cloud_gemini_2_5_flash()
        llm_service_cloud = LangChainService(local_llm=model_cloud, cloud_llm=model_cloud)
        detection_uc_cloud = DetectionUseCase(llm_service=llm_service_cloud, privacy_engine=privacy_engine)
        print(f"     ✔ Gemini 2.5 Flash (Cloud) gotowy.")
    except Exception as e:
        print(f"     ✘ Błąd Gemini: {e}")
        detection_uc_cloud = None

    # Przetwarzanie dokumentów
    for i in range(start_from, len(corpus)):
        doc = corpus[i]
        doc_id = doc["doc_id"]
        text = doc["text"]
        gt_entities = doc.get("entities", [])
        
        print(f"[{i+1}/{len(corpus)}] Doc {doc_id} - GT: {len(gt_entities)}")

        # Wykrywanie dla poszczególnych wariantów
        detected_variants = {}
        
        # --- 1. RegEx only ---
        detected_variants["RegEx only"] = detect_regex_only(privacy_engine, text)
        
        # --- 2. HerBERT only ---
        detected_variants["HerBERT only"] = detect_herbert_only(privacy_engine, text)
        
        # --- 3. HerBERT + RegEx ---
        detected_variants["HerBERT + RegEx"] = detect_ensemble(privacy_engine, text)
        
        # --- 4. Hybrid (Bielik 1.5) ---
        if "Hybrid (Bielik 1.5)" in configurations:
            if detection_uc_local:
                max_retries = 3
                failed_bielik = False
                for attempt in range(max_retries):
                    try:
                        detected_variants["Hybrid (Bielik 1.5)"] = await asyncio.wait_for(
                            detect_hybrid(detection_uc_local, privacy_engine, text),
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
            else:
                detected_variants["Hybrid (Bielik 1.5)"] = []

        # --- 5. Hybrid (Gemini 2.5) ---
        if "Hybrid (Gemini 2.5)" in configurations:
            if detection_uc_cloud:
                try:
                    detected_variants["Hybrid (Gemini 2.5)"] = await detect_hybrid(detection_uc_cloud, privacy_engine, text)
                except Exception as e:
                    print(f"     [!] Błąd Gemini na dokumencie {doc_id}: {e}. POMIJAM DOKUMENT.")
                    skipped_docs.append(doc_id)
                    continue
            else:
                detected_variants["Hybrid (Gemini 2.5)"] = []

        await asyncio.sleep(1.0)

        # Obliczanie i akumulacja metryk per dokument
        for config in configurations:
            detected = detected_variants.get(config, [])
            m = compute_metrics_detailed(detected, gt_entities)
            
            # Globalne per wariant i dokument (do bootstrapu)
            doc_metrics[config].append(m["total"])
            
            # Sumaryczne statystyki
            stats[config]["tp"] += m["total"]["tp"]
            stats[config]["fp"] += m["total"]["fp"]
            stats[config]["fn"] += m["total"]["fn"]
            
            # Statystyki per klasa
            for label, lm in m["per_type"].items():
                per_type_stats[config][label]["tp"] += lm["tp"]
                per_type_stats[config][label]["fp"] += lm["fp"]
                per_type_stats[config][label]["fn"] += lm["fn"]
                
            # Macierz pomyłek
            for (row, col), count in m["confusion"].items():
                confusion_matrices[config][(row, col)] += count

        # Checkpoint co 50 dokumentów
        if (i + 1) % 50 == 0:
            print(f"\n[CHECKPOINT] Zapisywanie postępu (dok: {i+1})...")
            save_checkpoint(i, stats, per_type_stats, confusion_matrices, doc_metrics, skipped_docs)

    # Obliczanie bootstrapu i przedziałów ufności na poziomie globalnym
    print("\n" + "=" * 105)
    print("📈 GLOBALNY RAPORT KOŃCOWY (z przedziałami ufności 95% Bootstrap)")
    print("=" * 105)
    print(f"{'Konfiguracja':<22} | {'Precision [95% CI]':<25} | {'Recall [95% CI]':<25} | {'F1-score [95% CI]':<25}")
    print("-" * 105)

    summary_rows = []
    eps = 1e-12

    for config in configurations:
        tp = stats[config]["tp"]
        fp = stats[config]["fp"]
        fn = stats[config]["fn"]
        
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        
        ci = compute_bootstrap_ci(doc_metrics[config], n_resamples=10000)
        
        p_ci_str = f"{p:.4f} [{ci['precision'][0]:.4f}, {ci['precision'][1]:.4f}]"
        r_ci_str = f"{r:.4f} [{ci['recall'][0]:.4f}, {ci['recall'][1]:.4f}]"
        f1_ci_str = f"{f1:.4f} [{ci['f1'][0]:.4f}, {ci['f1'][1]:.4f}]"
        
        print(f"{config:<22} | {p_ci_str:<25} | {r_ci_str:<25} | {f1_ci_str:<25}")
        
        summary_rows.append({
            "model": config,
            "precision": p,
            "precision_ci_low": ci['precision'][0],
            "precision_ci_high": ci['precision'][1],
            "recall": r,
            "recall_ci_low": ci['recall'][0],
            "recall_ci_high": ci['recall'][1],
            "f1": f1,
            "f1_ci_low": ci['f1'][0],
            "f1_ci_high": ci['f1'][1],
            "tp": tp,
            "fp": fp,
            "fn": fn
        })

    # Zapis sumarycznych wyników do CSV
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
        writer.writeheader()
        writer.writerows(summary_rows)

    # Raportowanie per klasa dla wszystkich modeli
    per_type_rows = []
    ALL_GT_LABELS = ["PESEL", "REGON", "NIP", "PER", "ACCT", "INV", "LOC"]
    
    for config in configurations:
        print("\n" + "=" * 80)
        print(f"📊 SZCZEGÓŁOWE STATYSTYKI KLAS DLA: {config.upper()}")
        print("-" * 80)
        print(f"{'Klasa PII':<12} | {'Precision':<10} | {'Recall':<10} | {'F1-score':<10} | {'FNR (Miss)':<10} | {'TP':<5} | {'FP':<5} | {'FN':<5}")
        print("-" * 80)
        
        for label in ALL_GT_LABELS:
            m = per_type_stats[config][label]
            tp_c = m["tp"]
            fp_c = m["fp"]
            fn_c = m["fn"]
            
            p_c = tp_c / (tp_c + fp_c) if (tp_c + fp_c) > 0 else 0.0
            r_c = tp_c / (tp_c + fn_c) if (tp_c + fn_c) > 0 else 0.0
            f1_c = 2 * p_c * r_c / (p_c + r_c) if (p_c + r_c) > 0 else 0.0
            fnr_c = fn_c / (tp_c + fn_c) if (tp_c + fn_c) > 0 else 0.0
            
            print(f"{label:<12} | {p_c:.4f}     | {r_c:.4f}     | {f1_c:.4f}     | {fnr_c:.4f}     | {tp_c:<5} | {fp_c:<5} | {fn_c:<5}")
            
            per_type_rows.append({
                "model": config,
                "type": label,
                "precision": p_c,
                "recall": r_c,
                "f1": f1_c,
                "fnr": fnr_c,
                "tp": tp_c,
                "fp": fp_c,
                "fn": fn_c
            })
            
        # Wyświetlanie macierzy pomyłek
        print_confusion_matrix(config, confusion_matrices[config])

    # Zapis szczegółowych wyników do CSV
    with open(RESULTS_PER_TYPE_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=per_type_rows[0].keys())
        writer.writeheader()
        writer.writerows(per_type_rows)

    print(f"\n[E1] Wszystkie wyniki zostały zapisane w {RESULTS_DIR}")
    if skipped_docs:
        print(f"[!] UWAGA: Pominięto {len(skipped_docs)} dokumentów: {skipped_docs}")
    print("=" * 105)

if __name__ == "__main__":
    asyncio.run(main())
