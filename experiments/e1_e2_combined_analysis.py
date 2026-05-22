import json
import csv
import asyncio
import time
import argparse
import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict

print("[START] Python is reading the script...")
print("[START] Basic imports done. Setting up paths...")
# Dodanie katalogu glownego projektu do sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Wymuszenie UTF-8 na konsoli Windows dla bezpieczenstwa
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass 

# Modele
LOCAL_MODEL = "qooba/bielik-1.5b-v3.0-instruct:Q8_0"
BASE_DIR = Path(__file__).parent.parent
CORPUS_FILE = BASE_DIR / "experiments/corpus/benchmark_corpus.json"
RESULTS_E1_FILE = BASE_DIR / "experiments/results/results_e1_detection.csv"
RESULTS_E2_FILE = BASE_DIR / "experiments/results/results_e2_utility.csv"
CHECKPOINT_FILE = BASE_DIR / "experiments/results/checkpoint_e1e2_all.json"

# --- MAPOWANIE DETEKTOR -> GT (zgodne z e1_pii_detection.py) ---
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

# --- POMOCNICZE ---
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

def pii_matches_text(detected_value: str, gt_text: str) -> bool:
    d = normalize(detected_value)
    t = normalize(gt_text)
    if not d or not t: return False
    return d == t or d in t or t in d

def tokenize(text: str) -> List[str]:
    return re.findall(r'\b\w+\b', text)

def get_utility(orig: str, masked: str) -> float:
    o_words = len(tokenize(orig))
    if o_words == 0:
        return 1.0
    m_words = len(tokenize(masked))
    return m_words / o_words

def map_label(detector_label: str) -> str:
    """Zwraca etykietę GT odpowiadającą etykiecie detektora."""
    return MAP_DETECTOR_TO_GT.get(detector_label, "UNKNOWN")

# --- METRYKI DWA PRZEJŚCIA (zgodne z e1_pii_detection.py) ---
def compute_metrics_detailed(
    detected_list: List[Tuple[str, str]],   # (value, raw_label)
    gt_entities: List[Dict]
) -> Dict[str, Any]:
    ALL_GT_LABELS = ["PESEL", "REGON", "NIP", "PER", "ACCT", "INV", "LOC"]
    
    # Normalizacja Ground Truth
    gt_list = []
    for ent in gt_entities:
        raw_label = ent.get('label', 'UNKNOWN')
        unified = map_label(raw_label)
        value = ent.get('text', '')
        gt_list.append((value, unified))
        
    # Normalizacja wykrytych encji (tylko te z ALL_GT_LABELS)
    pred_list = []
    for value, raw_label in detected_list:
        unified = map_label(raw_label)
        if unified in ALL_GT_LABELS:
            pred_list.append((value, unified))
            
    gt_matched = [False] * len(gt_list)
    pred_matched = [False] * len(pred_list)
    
    tp_by_class = defaultdict(int)
    fp_by_class = defaultdict(int)
    fn_by_class = defaultdict(int)
    confusion = defaultdict(int)
    
    # Pass 1: dopasowanie tekstu i labelu (True Positive)
    for i_pred, (pred_val, pred_label) in enumerate(pred_list):
        for i_gt, (gt_val, gt_label) in enumerate(gt_list):
            if gt_matched[i_gt] or pred_matched[i_pred]:
                continue
            if pred_label == gt_label and pii_matches_text(pred_val, gt_val):
                tp_by_class[gt_label] += 1
                confusion[(gt_label, pred_label)] += 1
                gt_matched[i_gt] = True
                pred_matched[i_pred] = True
                
    # Pass 2: dopasowanie tekstu, różne klasy (mismatch klasy -> FP i FN)
    for i_pred, (pred_val, pred_label) in enumerate(pred_list):
        if pred_matched[i_pred]:
            continue
        for i_gt, (gt_val, gt_label) in enumerate(gt_list):
            if gt_matched[i_gt]:
                continue
            if pii_matches_text(pred_val, gt_val):
                fp_by_class[pred_label] += 1
                fn_by_class[gt_label] += 1
                confusion[(gt_label, pred_label)] += 1
                gt_matched[i_gt] = True
                pred_matched[i_pred] = True
                break
                
    # Niesparowane GT -> FN
    for i_gt, (gt_val, gt_label) in enumerate(gt_list):
        if not gt_matched[i_gt]:
            fn_by_class[gt_label] += 1
            confusion[(gt_label, "None")] += 1
            
    # Niesparowane wykryte -> FP
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
        "per_type": type_metrics
    }

# --- POMOCE DO ZAPISU ---
def save_checkpoint_detailed(last_index: int, stats: dict, per_type_stats: dict,
                             e1_results: list, e2_results: list, skipped: list):
    data = {
        "last_index": last_index,
        "stats": stats,
        "per_type_stats": per_type_stats,
        "e1_results": e1_results,
        "e2_results": e2_results,
        "skipped_docs": skipped
    }
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_final_csv(e1_results, e2_results):
    for results, file in [(e1_results, RESULTS_E1_FILE), (e2_results, RESULTS_E2_FILE)]:
        if not results:
            continue
        with open(file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)

# --- GŁÓWNY EKSPERYMENT ---
async def run_experiment():
    parser = argparse.ArgumentParser(description="E1+E2 Comprehensive Analyzer")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    print("="*80)
    print("START: FULL EXPERIMENT E1 + E2 (DIAGNOSTIC BOOT)")
    print("="*80)
    
    print("[INIT] Importing heavy NLP modules...", end="", flush=True)
    from src.app.main import bootstrap_app
    from src.app.infrastructure.services.presidio_factory import setup_presidio_analyzer
    from src.app.infrastructure.services.presidio_service import PresidioService
    print(" DONE.")
    
    print("[INIT] Bootstrapping App Graph...", end="", flush=True)
    app_graph = bootstrap_app()
    print(" DONE.")
    
    print("[INIT] Setting up Presidio Analyzer...", end="", flush=True)
    analyzer = setup_presidio_analyzer()
    presidio_service = PresidioService(analyzer)
    print(" DONE.")
    
    print("[INIT] Loading Benchmark Corpus...", end="", flush=True)
    with open(CORPUS_FILE, "r", encoding="utf-8") as f:
        corpus = json.load(f)
    print(f" DONE. (Loaded {len(corpus)} docs)")

    if args.limit:
        corpus = corpus[:args.limit]

    configurations = ["regex", "herbert", "ener", "hybrid_bielik", "hybrid_gemini"]
    stats = {config: {"tp": 0, "fp": 0, "fn": 0} for config in configurations}
    per_type_stats = {config: defaultdict(lambda: {"tp": 0, "fn": 0}) for config in configurations}
    e1_results = []
    e2_results = []
    skipped_docs = []
    start_from = 0

    if args.resume and CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            cp = json.load(f)
            start_from = cp["last_index"] + 1
            stats = cp["stats"]
            for cfg in configurations:
                per_type_stats[cfg] = defaultdict(
                    lambda: {"tp": 0, "fn": 0}, cp["per_type_stats"].get(cfg, {})
                )
            e1_results = cp.get("e1_results", [])
            e2_results = cp.get("e2_results", [])
            skipped_docs = cp.get("skipped_docs", [])
            print(f"🔄 RESUMING from document {start_from}...")
    else:
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()

    for i in range(start_from, len(corpus)):
        doc = corpus[i]
        text = doc["text"]
        gt = doc.get("entities", [])
        doc_id = doc.get("doc_id", i)
        print(f"\n📄 [{i+1}/{len(corpus)}] ID: {doc_id}")
        doc_results = {}
        skip_document = False
        row_e1 = {"doc_id": doc_id}
        row_e2 = {"doc_id": doc_id}

        for name in configurations:
            t0 = time.time()
            detected: List[Tuple[str, str]] = []   # (value, raw_label)
            utility = 0.0

            if name == "regex":
                detailed = presidio_service.analyze_detailed(text)
                # rozpoznawacze wykluczone: TransformersRecognizer, CustomSpacyRecognizer, SpacyRecognizer
                detected = [
                    (ent.value, ent.label)
                    for ent in detailed
                    if ent.recognizer not in ["TransformersRecognizer", "CustomSpacyRecognizer", "SpacyRecognizer"]
                ]

            elif name == "herbert":
                detailed = presidio_service.analyze_detailed(text)
                def allowed_recognizer(ent):
                    return ent.recognizer in ["TransformersRecognizer"]   # tylko ten
                detected = [
                    (ent.value, ent.label)
                    for ent in detailed
                    if allowed_recognizer(ent)
                ]

            elif name == "ener":
                detailed = presidio_service.analyze_detailed(text)
                # wszystkie encje jako (value, label)
                detected = [(ent.value, ent.label) for ent in detailed]

            else:   # hybrid_bielik lub hybrid_gemini
                model = LOCAL_MODEL if "bielik" in name else "gemini-2.5-flash"
                max_retries = 3 if "bielik" in name else 1
                success = False
                for attempt in range(max_retries):
                    try:
                        state = await asyncio.wait_for(
                            app_graph.ainvoke(
                                {
                                    "file_context": text,
                                    "user_query": "Analiza danych.",
                                    "detection_mode": "hybrid",
                                    "local_model": model,
                                    "vault": {},
                                    "raw_pii_strings": []
                                },
                                config={"configurable": {"thread_id": f"e1e2_{name}_{i}"}}
                             ),
                            timeout=120.0
                        )
                        raw_pii_strings: List[str] = state.get("raw_pii_strings", [])
                        labeled_pii_entities = state.get("labeled_pii_entities", [])
                        # Mapa z wartości -> etykieta (jeśli dostępna)
                        label_map = {}
                        for ent in labeled_pii_entities:
                            if isinstance(ent, dict):
                                val = ent.get("value", "")
                                lab = ent.get("label", "UNKNOWN")
                            else:   # obiekt z atrybutami
                                val = ent.value if hasattr(ent, 'value') else ""
                                lab = ent.label if hasattr(ent, 'label') else "UNKNOWN"
                            if val:
                                label_map[val] = lab
                        detected = []
                        for val in raw_pii_strings:
                            if val in label_map:
                                detected.append((val, label_map[val]))
                            else:
                                # fallback: próba z Presidio
                                fallback_detail = presidio_service.analyze_detailed(text)
                                found_label = "UNKNOWN"
                                for ent in fallback_detail:
                                    if ent.value == val:
                                        found_label = ent.label
                                        break
                                detected.append((val, found_label))
                        utility = get_utility(text, state.get("masked_context", ""))
                        success = True
                        break
                    except Exception as e:
                        print(f" [!] {name} Retry {attempt+1}: {str(e)[:30]}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(10.0)
                if not success:
                    skip_document = True
                    break

            # Oblicz metryki
            m = compute_metrics_detailed(detected, gt)
            doc_results[name] = {"m": m, "utility": utility, "detected": detected}

            # Jeśli utility == 0.0 a coś wykryto, obliczamy ręcznie
            if utility == 0.0 and detected:
                masked = text
                # sortujemy po długości wartości malejąco
                for val, _ in sorted(detected, key=lambda x: len(x[0]), reverse=True):
                    masked = masked.replace(val, "[MASK]")
                utility = get_utility(text, masked)
            doc_results[name]["utility"] = utility

        if skip_document:
            skipped_docs.append(doc_id)
            continue

        for name in configurations:
            m = doc_results[name]["m"]
            stats[name]["tp"] += m["total"]["tp"]
            stats[name]["fp"] += m["total"]["fp"]
            stats[name]["fn"] += m["total"]["fn"]
            for label, lm in m["per_type"].items():
                per_type_stats[name][label]["tp"] += lm["tp"]
                per_type_stats[name][label]["fn"] += lm["fn"]
            tp_ = m["total"]["tp"]
            fn_ = m["total"]["fn"]
            recall = tp_ / (tp_ + fn_) if (tp_ + fn_) > 0 else 1.0
            row_e1[f"{name}_recall"] = recall
            row_e2[f"{name}_utility"] = doc_results[name]["utility"]
            print(f"  {name:<15} | R: {recall:.2f} | U: {doc_results[name]['utility']:.2f}")

        e1_results.append(row_e1)
        e2_results.append(row_e2)
        save_checkpoint_detailed(
            i, stats,
            {k: dict(v) for k, v in per_type_stats.items()},
            e1_results, e2_results, skipped_docs
        )

    save_final_csv(e1_results, e2_results)
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_report_path = BASE_DIR / f"experiments/results/results_e1e2_all_{timestamp}.json"
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.rename(final_report_path)
        print(f"\n✅ FINISH: Report saved to {final_report_path.name}")
    else:
        print("\n✅ FINISH: Saved to CSV.")

if __name__ == "__main__":
    asyncio.run(run_experiment())
