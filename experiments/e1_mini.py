import json
import sys
from pathlib import Path

# Fix encoding for Windows console
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
CORPUS_PATH = PROJECT_ROOT / "experiments" / "corpus" / "corpus.json"

def normalize(s: str) -> str:
    return s.strip().lower()

def pii_matches(detected: str, truth: str) -> bool:
    d = normalize(detected)
    t = normalize(truth)
    if not d or not t: return False
    return d == t or d in t or t in d

def compute_metrics(detected: list[str], ground_truth: list[str]) -> dict:
    matched_gt = set()
    matched_det = set()
    for i, d in enumerate(detected):
        for j, gt in enumerate(ground_truth):
            if j not in matched_gt and pii_matches(d, gt):
                matched_det.add(i)
                matched_gt.add(j)
                break
    tp = len(matched_gt)
    fp = len(detected) - len(matched_det)
    fn = len(ground_truth) - len(matched_gt)
    return {"tp": tp, "fp": fp, "fn": fn}

def main():
    print("=== E1 MINI: HYBRID PROMPT OPTIMIZATION ===")
    with open(CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)
    
    from agents.detection import hybrid_detection_agent
    
    tp_total, fp_total, fn_total = 0, 0, 0
    
    for doc in corpus:
        text = doc["text"]
        gt = doc["pii"]
        
        state = {
            "raw_xml": text, "user_query": "",
            "raw_pii_strings": [], "labeled_pii_entities": [],
            "masked_context": "", "masked_query": "", "vault": {},
            "is_safe": False, "cloud_response": "", "final_output": "", "error_status": ""
        }
        
        result = hybrid_detection_agent(state)
        detected = result.get("raw_pii_strings", [])
        
        print(f"Doc {doc['doc_id']} [GT: {len(gt)}]: {gt}")
        print(f"  -> Detected: {detected}")
        
        metrics = compute_metrics(detected, gt)
        tp_total += metrics["tp"]
        fp_total += metrics["fp"]
        fn_total += metrics["fn"]
        
    p = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else 0.0
    r = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    
    print("=" * 40)
    print(f"Precision: {p:.4f}")
    print(f"Recall:    {r:.4f}")
    print(f"F1-score:  {f1:.4f}")
    print("=" * 40)

if __name__ == "__main__":
    main()
