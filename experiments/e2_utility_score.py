import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

# Wymuszenie UTF-8
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CORPUS_PATH = PROJECT_ROOT / "experiments" / "corpus" / "corpus.json"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
RESULTS_CSV = RESULTS_DIR / "results_e2_comparison.csv"

def word_entropy(text: str) -> float:
    words = text.lower().split()
    if not words: return 0.0
    counts = Counter(words)
    total = len(words)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())

def compute_bertscore(originals: list[str], masked_texts: list[str]):
    from bert_score import score
    P, R, F1 = score(
        cands=masked_texts,
        refs=originals,
        lang="pl",
        model_type="bert-base-multilingual-cased",
        verbose=False,
    )
    return [{"f1": f.item()} for f in F1]

def run_masking_scenario(text: str, pii_list: list[str], use_labeling: bool):
    """Wykonuje maskowanie w jednym z dwóch trybów."""
    from agents.masking import masking_agent
    from agents.labeling import labeling_agent
    
    state = {
        "raw_xml": text,
        "user_query": "",
        "detected_pii": pii_list,
        "pii_entities": [],
        "masked_context": "",
        "masked_query": "",
        "vault": {}
    }
    
    if use_labeling:
        label_res = labeling_agent(state)
        state.update(label_res)
    
    mask_res = masking_agent(state)
    return mask_res["masked_context"]

def main():
    print("=" * 70)
    print("EKSPERYMENT 2 – Porównanie użyteczności: Generyczne vs Semantyczne")
    print("=" * 70)

    with open(CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)

    docs_with_pii = [d for d in corpus if len(d["pii"]) > 0]
    print(f"[E2] Analiza {len(docs_with_pii)} dokumentów.\n")

    originals = []
    masked_generic = []
    masked_semantic = []

    for i, doc in enumerate(docs_with_pii):
        print(f"[E2] Przetwarzanie dokumentu {i+1}/{len(docs_with_pii)} (ID: {doc['doc_id']})...")
        text = doc["text"]
        originals.append(text)
        
        # Scenariusz A: Generyczny
        print(f"  - Generowanie maskowania generycznego...")
        masked_generic.append(run_masking_scenario(text, doc["pii"], use_labeling=False))
        
        # Scenariusz B: Semantyczny
        print(f"  - Generowanie maskowania semantycznego (LLM Labeling)...")
        masked_semantic.append(run_masking_scenario(text, doc["pii"], use_labeling=True))

    print("[E2] Obliczanie BERTScore dla obu scenariuszy...")
    res_generic = compute_bertscore(originals, masked_generic)
    res_semantic = compute_bertscore(originals, masked_semantic)

    rows = []
    for i, doc in enumerate(docs_with_pii):
        f1_gen = res_generic[i]["f1"]
        f1_sem = res_semantic[i]["f1"]
        
        rows.append({
            "doc_id": doc["doc_id"],
            "category": doc["category"],
            "f1_generic": round(f1_gen, 4),
            "f1_semantic": round(f1_sem, 4),
            "improvement": round((f1_sem - f1_gen) * 100, 2),
            "degradation_semantic_pct": round((1.0 - f1_sem) * 100, 2)
        })

    # Podsumowanie
    avg_gen = sum(r["f1_generic"] for r in rows) / len(rows)
    avg_sem = sum(r["f1_semantic"] for r in rows) / len(rows)
    avg_impr = sum(r["improvement"] for r in rows) / len(rows)
    avg_degr_sem = sum(r["degradation_semantic_pct"] for r in rows) / len(rows)

    print("\n" + "=" * 70)
    print("WYNIKI PORÓWNAWCZE")
    print("=" * 70)
    print(f"  Średni BERTScore (Generyczny): {avg_gen:.4f}")
    print(f"  Średni BERTScore (Semantyczny): {avg_sem:.4f}")
    print(f"  Średnia poprawa dzięki typom:  {avg_impr:+.2f}%")
    print(f"  Degradacja semantyczna:        {avg_degr_sem:.2f}%  {'✅ PASS' if avg_degr_sem < 15 else '❌ FAIL'}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n[E2] Wyniki porównawcze zapisane → {RESULTS_CSV}")

if __name__ == "__main__":
    main()
