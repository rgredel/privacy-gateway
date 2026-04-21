"""
e1_pii_detection.py – Eksperyment 1: Ewaluacja skuteczności detekcji PII.

Porównuje F1-score bramki Privacy Gateway (Bielik v3 via Ollama)
z klasycznym NER (Microsoft Presidio + spaCy PL) na nieustrukturyzowanym
tekście naturalnym.

Odpowiada na: Pytanie badawcze P1
Kryterium sukcesu: F1(Gateway) ≥ 0.55 i F1(Gateway) > F1(Presidio)

Uruchomienie:
    python experiments/e1_pii_detection.py
"""

import csv
import json
import sys
from pathlib import Path

# Wymuszenie UTF-8 na konsoli Windows (cp1250 nie obsługuje ✅/→/═)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Importy z projektu głównego ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CORPUS_PATH = PROJECT_ROOT / "experiments" / "corpus" / "corpus.json"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
RESULTS_CSV = RESULTS_DIR / "results_e1.csv"


# ══════════════════════════════════════════════════════════════════════════════
# 1. Narzędzia dopasowania PII (matching)
# ══════════════════════════════════════════════════════════════════════════════

def normalize(s: str) -> str:
    return s.strip().lower()


def pii_matches(detected: str, truth: str) -> bool:
    """Dopasowanie: exact match lub zawieranie (jeden jest podciągiem drugiego)."""
    d = normalize(detected)
    t = normalize(truth)
    if not d or not t:
        return False
    return d == t or d in t or t in d


def compute_metrics(detected: list[str], ground_truth: list[str]) -> dict:
    """Oblicza TP, FP, FN, Precision, Recall, F1 dla jednego dokumentu."""
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

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


# ══════════════════════════════════════════════════════════════════════════════
# 2. Baseline NER – Microsoft Presidio z polskim modelem spaCy
# ══════════════════════════════════════════════════════════════════════════════

def run_presidio(analyzer, text: str) -> list[str]:
    """Uruchamia Presidio z modułu agents i zwraca listę wykrytych PII."""
    from agents.presidio_engine import get_pii_candidates
    return get_pii_candidates(text, analyzer)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Privacy Gateway – detekcja Bielik oraz Hybrydowa
# ══════════════════════════════════════════════════════════════════════════════

def run_gateway_detection(text: str) -> list[str]:
    """Wywołuje detection_agent (LLM-only)."""
    from agents.detection import detection_agent
    state = {
        "raw_xml": text,
        "user_query": "",
        "raw_pii_strings": [],
        "labeled_pii_entities": [],
        "masked_context": "",
        "masked_query": "",
        "vault": {},
        "is_safe": False,
        "cloud_response": "",
        "final_output": "",
        "error_status": ""
    }
    result = detection_agent(state)
    detected = result.get("raw_pii_strings", [])
    print(f"    [Gateway] Wykryte: {detected}")
    return detected

def run_hybrid_detection(text: str) -> list[str]:
    """Wywołuje hybrid_detection_agent (Presidio -> LLM)."""
    from agents.detection import hybrid_detection_agent
    state = {
        "raw_xml": text,
        "user_query": "",
        "raw_pii_strings": [],
        "labeled_pii_entities": [],
        "masked_context": "",
        "masked_query": "",
        "vault": {},
        "is_safe": False,
        "cloud_response": "",
        "final_output": "",
        "error_status": ""
    }
    result = hybrid_detection_agent(state)
    detected = result.get("raw_pii_strings", [])
    print(f"    [Hybrid] Wykryte: {detected}")
    return detected


# ══════════════════════════════════════════════════════════════════════════════
# 4. Główna pętla eksperymentu
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("EKSPERYMENT 1 – Ewaluacja skuteczności detekcji PII (F1-score)")
    print("=" * 70)

    # Wczytanie korpusu
    if not CORPUS_PATH.exists():
        print(f"[BŁĄD] Brak korpusu: {CORPUS_PATH}")
        print("       Uruchom najpierw: python experiments/corpus/generate_corpus.py")
        sys.exit(1)

    with open(CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)
    print(f"[E1] Załadowano {len(corpus)} dokumentów z korpusu.\n")

    # ── Presidio ──────────────────────────────────────────────────────────
    # ── Presidio ──────────────────────────────────────────────────────────
    print("[E1] Konfiguracja Presidio (NER engine)...")
    from agents.presidio_engine import setup_presidio_analyzer
    try:
        analyzer = setup_presidio_analyzer()
        presidio_available = analyzer is not None
        if presidio_available:
            print("     ✔ Presidio gotowe.\n")
        else:
            raise Exception("setup_presidio_analyzer returned None")
    except Exception as e:
        print(f"     ✘ Presidio niedostępne: {e}")
        print("     → Presidio pominięte.\n")
        presidio_available = False

    # ── Wyniki ────────────────────────────────────────────────────────────
    rows = []
    gateway_totals = {"tp": 0, "fp": 0, "fn": 0}
    presidio_totals = {"tp": 0, "fp": 0, "fn": 0}
    hybrid_totals = {"tp": 0, "fp": 0, "fn": 0}

    for doc in corpus:
        doc_id = doc["doc_id"]
        text = doc["text"]
        gt = doc["pii"]

        print(f"  Dokument {doc_id} [{doc['category']}] – {len(gt)} PII w ground truth")
        print(f"    [GT] Expected: {gt}")

        # 1. Gateway (Bielik only)
        try:
            gw_detected = run_gateway_detection(text)
        except Exception as e:
            print(f"    [BŁĄD Gateway] {e}")
            gw_detected = []
        gw_metrics = compute_metrics(gw_detected, gt)
        for k in ["tp", "fp", "fn"]: gateway_totals[k] += gw_metrics[k]

        # 2. Presidio (NER only)
        if presidio_available:
            try:
                pr_detected = run_presidio(analyzer, text)
                print(f"    [Presidio] Wykryte: {pr_detected}")
            except Exception as e:
                print(f"    [BŁĄD Presidio] {e}")
                pr_detected = []
        else:
            pr_detected = []
        pr_metrics = compute_metrics(pr_detected, gt)
        for k in ["tp", "fp", "fn"]: presidio_totals[k] += pr_metrics[k]

        # 3. Hybrid (Sequential)
        try:
            hb_detected = run_hybrid_detection(text)
        except Exception as e:
            print(f"    [BŁĄD Hybrid] {e}")
            hb_detected = []
        hb_metrics = compute_metrics(hb_detected, gt)
        for k in ["tp", "fp", "fn"]: hybrid_totals[k] += hb_metrics[k]

        print(f"    Gateway: F1={gw_metrics['f1']:.3f} | Presidio: F1={pr_metrics['f1']:.3f} | Hybrid: F1={hb_metrics['f1']:.3f}")

        rows.append({
            "doc_id": doc_id,
            "category": doc["category"],
            "gt_count": len(gt),
            "gw_f1": round(gw_metrics["f1"], 4),
            "pr_f1": round(pr_metrics["f1"], 4),
            "hb_f1": round(hb_metrics["f1"], 4),
            "gw_tp": gw_metrics["tp"], "gw_fp": gw_metrics["fp"], "gw_fn": gw_metrics["fn"],
            "pr_tp": pr_metrics["tp"], "pr_fp": pr_metrics["fp"], "pr_fn": pr_metrics["fn"],
            "hb_tp": hb_metrics["tp"], "hb_fp": hb_metrics["fp"], "hb_fn": hb_metrics["fn"],
        })

    # ── Metryki mikro-uśrednione ─────────────────────────────────────────
    print("\n" + "=" * 70)
    print("WYNIKI ZAGREGOWANE (mikro-uśrednienie)")
    print("=" * 70)

    for label, totals in [("Gateway (Bielik)", gateway_totals), ("Presidio (NER)", presidio_totals), ("Hybrid (Seq)", hybrid_totals)]:
        tp, fp, fn = totals["tp"], totals["fp"], totals["fn"]
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        print(f"  {label}:")
        print(f"    Precision = {p:.4f}")
        print(f"    Recall    = {r:.4f}")
        print(f"    F1-score  = {f1:.4f}   {'✅ PASS' if f1 >= 0.55 else '❌ FAIL'} (próg ≥ 0.55)")

        rows.append({
            "doc_id": f"MICRO_{label}",
            "category": "aggregate",
            "gw_f1": round(f1, 4) if "Gateway" in label else "",
            "pr_f1": round(f1, 4) if "Presidio" in label else "",
            "hb_f1": round(f1, 4) if "Hybrid" in label else "",
        })

    # ── Zapis CSV ─────────────────────────────────────────────────────────
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(RESULTS_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[E1] Wyniki zapisane → {RESULTS_CSV}")


if __name__ == "__main__":
    main()
