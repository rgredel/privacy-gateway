print("[START] Python is reading the script...")
import json
import csv
import asyncio
import time
import argparse
import sys
from pathlib import Path

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

# --- LOGIKA OBLICZENIOWA ---
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict

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
            if gt_idx not in matched_gt_indices and pii_matches(d_text, gt_ent.get("text", "")):
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
        "per_type": {k: dict(v) for k, v in type_metrics.items()}
    }

def get_utility(orig, masked):
    o_words = len(orig.split())
    if o_words == 0: return 1.0
    m_words = len(masked.split())
    return 1.0 - abs(o_words - m_words) / o_words

def save_checkpoint_detailed(last_index: int, stats: dict, per_type_stats: dict, e1_results: list, e2_results: list, skipped: list):
    data = {"last_index": last_index, "stats": stats, "per_type_stats": per_type_stats, "e1_results": e1_results, "e2_results": e2_results, "skipped_docs": skipped}
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_final_csv(e1_results, e2_results):
    for results, file in [(e1_results, RESULTS_E1_FILE), (e2_results, RESULTS_E2_FILE)]:
        if not results: continue
        with open(file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)

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

    if args.limit: corpus = corpus[:args.limit]

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
            for cfg in configurations: per_type_stats[cfg] = defaultdict(lambda: {"tp": 0, "fn": 0}, cp["per_type_stats"].get(cfg, {}))
            e1_results = cp.get("e1_results", [])
            e2_results = cp.get("e2_results", [])
            skipped_docs = cp.get("skipped_docs", [])
            print(f"🔄 RESUMING from document {start_from}...")
    else:
        if CHECKPOINT_FILE.exists(): CHECKPOINT_FILE.unlink()

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
            detected = []
            utility = 0.0
            if name == "regex":
                detailed = presidio_service.analyze_detailed(text)
                nlp_recs = ["TransformersRecognizer", "CustomSpacyRecognizer", "SpacyRecognizer"]
                detected = list(set([ent.value for ent in detailed if ent.recognizer not in nlp_recs]))
            elif name == "herbert":
                detailed = presidio_service.analyze_detailed(text)
                herbert_labels = ["PERSON", "LOCATION", "ORGANIZATION"]
                detected = list(set([ent.value for ent in detailed if ent.label in herbert_labels]))
            elif name == "ener":
                detected = presidio_service.get_candidates(text)
            else:
                model = LOCAL_MODEL if "bielik" in name else "gemini-2.5-flash"
                max_retries = 3 if "bielik" in name else 1
                success = False
                for attempt in range(max_retries):
                    try:
                        state = await asyncio.wait_for(app_graph.ainvoke({
                            "file_context": text, "user_query": "Analiza danych.",
                            "detection_mode": "hybrid", "local_model": model,
                            "vault": {}, "raw_pii_strings": []
                        }, config={"configurable": {"thread_id": f"e1e2_{name}_{i}"}}), timeout=120.0)
                        detected = state.get("raw_pii_strings", [])
                        utility = get_utility(text, state.get("masked_context", ""))
                        success = True
                        break
                    except Exception as e:
                        print(f" [!] {name} Retry {attempt+1}: {str(e)[:30]}")
                        if attempt < max_retries - 1: await asyncio.sleep(10.0)
                if not success: skip_document = True; break

            m = compute_metrics_detailed(detected, gt)
            doc_results[name] = {"m": m, "utility": utility, "detected": detected}
            if utility == 0.0 and detected:
                masked = text
                for val in sorted(detected, key=len, reverse=True): masked = masked.replace(val, "[MASK]")
                utility = get_utility(text, masked)
            elif not detected and "hybrid" not in name: utility = 1.0
            doc_results[name]["utility"] = utility

        if skip_document: skipped_docs.append(doc_id); continue
        for name in configurations:
            m = doc_results[name]["m"]
            stats[name]["tp"] += m["total"]["tp"]; stats[name]["fp"] += m["total"]["fp"]; stats[name]["fn"] += m["total"]["fn"]
            for label, lm in m["per_type"].items(): per_type_stats[name][label]["tp"] += lm["tp"]; per_type_stats[name][label]["fn"] += lm["fn"]
            row_e1[f"{name}_recall"] = m["total"]["tp"] / (m["total"]["tp"] + m["total"]["fn"]) if (m["total"]["tp"] + m["total"]["fn"]) > 0 else 1.0
            row_e2[f"{name}_utility"] = doc_results[name]["utility"]
            print(f"  {name:<15} | R: {row_e1[f'{name}_recall']:.2f} | U: {row_e2[f'{name}_utility']:.2f}")

        e1_results.append(row_e1); e2_results.append(row_e2)
        save_checkpoint_detailed(i, stats, {k: dict(v) for k, v in per_type_stats.items()}, e1_results, e2_results, skipped_docs)

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
