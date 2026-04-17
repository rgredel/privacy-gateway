"""
e2_utility_score.py – Eksperyment 2: Analiza spadku użyteczności informacyjnej.

Mierzy degradację BERTScore i entropii dokumentu po maskowaniu PII.
Odpowiada na: Pytanie badawcze P2
Kryterium sukcesu: średni spadek BERTScore < 15%

Uruchomienie:
    python experiments/e2_utility_score.py
"""

import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CORPUS_PATH = PROJECT_ROOT / "experiments" / "corpus" / "corpus.json"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
RESULTS_CSV = RESULTS_DIR / "results_e2.csv"


# ══════════════════════════════════════════════════════════════════════════════
# 1. Metryki użyteczności
# ══════════════════════════════════════════════════════════════════════════════

def word_entropy(text: str) -> float:
    """Entropia unigramów słownych (bity)."""
    words = text.lower().split()
    if not words:
        return 0.0
    counts = Counter(words)
    total = len(words)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def compute_bertscore(originals: list[str], masked_texts: list[str]) -> list[dict]:
    """Oblicza BERTScore (Precision, Recall, F1) dla par oryginalny/zamaskowany."""
    from bert_score import score

    P, R, F1 = score(
        cands=masked_texts,
        refs=originals,
        lang="pl",
        model_type="allegro/herbert-base-cased",
        verbose=True,
    )
    results = []
    for i in range(len(originals)):
        results.append({
            "bert_precision": P[i].item(),
            "bert_recall": R[i].item(),
            "bert_f1": F1[i].item(),
        })
    return results


# ══════════════════════════════════════════════════════════════════════════════
# 2. Maskowanie dokumentów
# ══════════════════════════════════════════════════════════════════════════════

def mask_document(text: str, pii_list: list[str]) -> tuple[str, dict]:
    """
    Maskuje PII w tekście (symulacja masking_agent).
    Zwraca (zamaskowany_tekst, vault).
    """
    from agents.masking import masking_agent

    state = {
        "raw_xml": text,
        "user_query": "",
        "detected_pii": pii_list,
        "masked_context": "",
        "masked_query": "",
        "vault": {},
        "is_safe": False,
        "cloud_response": "",
        "final_output": "",
    }
    result = masking_agent(state)
    return result["masked_context"], result["vault"]


# ══════════════════════════════════════════════════════════════════════════════
# 3. Główna pętla eksperymentu
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("EKSPERYMENT 2 – Analiza spadku użyteczności (Utility Score)")
    print("=" * 70)

    if not CORPUS_PATH.exists():
        print(f"[BŁĄD] Brak korpusu: {CORPUS_PATH}")
        print("       Uruchom najpierw: python experiments/corpus/generate_corpus.py")
        sys.exit(1)

    with open(CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)

    # Filtruj dokumenty z PII (czyste pomijamy – brak sensu mierzyć degradację)
    docs_with_pii = [d for d in corpus if len(d["pii"]) > 0]
    print(f"[E2] Załadowano {len(docs_with_pii)} dokumentów z PII.\n")

    # ── Maskowanie ────────────────────────────────────────────────────────
    originals = []
    masked_texts = []
    rows = []

    for doc in docs_with_pii:
        text = doc["text"]
        masked, vault = mask_document(text, doc["pii"])

        originals.append(text)
        masked_texts.append(masked)

        # Entropia
        ent_orig = word_entropy(text)
        ent_masked = word_entropy(masked)
        ent_loss_pct = abs(ent_orig - ent_masked) / ent_orig * 100 if ent_orig > 0 else 0.0

        # Prosty wskaźnik: procent znaków zmienionych
        char_diff = sum(1 for a, b in zip(text, masked) if a != b) + abs(len(text) - len(masked))
        char_change_pct = char_diff / len(text) * 100 if len(text) > 0 else 0.0

        rows.append({
            "doc_id": doc["doc_id"],
            "category": doc["category"],
            "pii_count": len(doc["pii"]),
            "original_len": len(text),
            "masked_len": len(masked),
            "vault_size": len(vault),
            "entropy_original": round(ent_orig, 4),
            "entropy_masked": round(ent_masked, 4),
            "entropy_loss_pct": round(ent_loss_pct, 2),
            "char_change_pct": round(char_change_pct, 2),
            # BERTScore wypełnione niżej
            "bert_precision": None,
            "bert_recall": None,
            "bert_f1": None,
            "bert_degradation_pct": None,
        })

        print(f"  Doc {doc['doc_id']} [{doc['category']}]: "
              f"Entropy loss={ent_loss_pct:.1f}%, Char Δ={char_change_pct:.1f}%")

    # ── BERTScore ─────────────────────────────────────────────────────────
    print("\n[E2] Obliczanie BERTScore (allegro/herbert-base-cased)...")
    try:
        bert_results = compute_bertscore(originals, masked_texts)
        bert_available = True
    except Exception as e:
        print(f"  ✘ BERTScore niedostępne: {e}")
        print("  → Zainstaluj: pip install bert-score")
        bert_results = [{"bert_precision": 0, "bert_recall": 0, "bert_f1": 0}] * len(rows)
        bert_available = False

    for i, br in enumerate(bert_results):
        rows[i]["bert_precision"] = round(br["bert_precision"], 4)
        rows[i]["bert_recall"] = round(br["bert_recall"], 4)
        rows[i]["bert_f1"] = round(br["bert_f1"], 4)
        rows[i]["bert_degradation_pct"] = round((1.0 - br["bert_f1"]) * 100, 2)

    # ── Podsumowanie ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("WYNIKI ZAGREGOWANE")
    print("=" * 70)

    avg_bert_f1 = sum(r["bert_f1"] for r in rows) / len(rows) if rows else 0
    avg_degradation = sum(r["bert_degradation_pct"] for r in rows) / len(rows) if rows else 0
    avg_entropy_loss = sum(r["entropy_loss_pct"] for r in rows) / len(rows) if rows else 0
    avg_char_change = sum(r["char_change_pct"] for r in rows) / len(rows) if rows else 0

    print(f"  Średni BERTScore F1:           {avg_bert_f1:.4f}")
    print(f"  Średnia degradacja BERTScore:  {avg_degradation:.2f}%  "
          f"{'✅ PASS' if avg_degradation < 15 else '❌ FAIL'} (próg < 15%)")
    print(f"  Średnia utrata entropii:       {avg_entropy_loss:.2f}%")
    print(f"  Średnia zmiana znaków:         {avg_char_change:.2f}%")

    # ── Zapis CSV ─────────────────────────────────────────────────────────
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(RESULTS_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[E2] Wyniki zapisane → {RESULTS_CSV}")


if __name__ == "__main__":
    main()
