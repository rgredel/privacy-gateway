"""
e4_latency_benchmark.py – Eksperyment 4: Benchmark opóźnienia i transferu.

Mierzy narzut czasowy Privacy Gateway oraz redukcję rozmiaru ładunku
wysyłanego do chmury (Gemini).
Odpowiada na: Pytanie badawcze P4
N = 10 powtórzeń na konfigurację.

Uruchomienie:
    python experiments/e4_latency_benchmark.py
"""

import csv
import os
import statistics
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
RESULTS_CSV = RESULTS_DIR / "results_e4.csv"

N_REPEATS = 10  # Liczba powtórzeń benchmarku per konfiguracja

# Zapytania testowe
TEST_QUERIES = [
    "Jakie są dane kontrahenta z ostatniej faktury?",
    "Z kim powinienem się kontaktować w sprawie zamówienia?",
    "Na jakie konto mam przelać należność za fakturę?",
]


# ══════════════════════════════════════════════════════════════════════════════
# 1. Konfiguracja A – Bezpośredni Gemini (bez Gateway)
# ══════════════════════════════════════════════════════════════════════════════

def run_direct_gemini(xml_context: str, query: str) -> tuple[float, int]:
    """
    Wysyła zapytanie bezpośrednio do Gemini (bez maskowania PII).
    Zwraca (czas_sekundy, rozmiar_payload_bajty).
    """
    from langchain_core.prompts import PromptTemplate
    from llm_factory import get_cloud_llm

    llm = get_cloud_llm()

    prompt = PromptTemplate.from_template(
        "Jesteś asystentem biznesowo-finansowym. "
        "Na podstawie poniższego kontekstu odpowiedz na pytanie.\n\n"
        "KONTEKST:\n{context}\n\n"
        "PYTANIE:\n{query}"
    )

    chain = prompt | llm
    payload = xml_context + "\n" + query
    payload_size = len(payload.encode("utf-8"))

    start = time.perf_counter()
    chain.invoke({"context": xml_context, "query": query})
    elapsed = time.perf_counter() - start

    return elapsed, payload_size


# ══════════════════════════════════════════════════════════════════════════════
# 2. Konfiguracja B – Pełny Privacy Gateway (LangGraph)
# ══════════════════════════════════════════════════════════════════════════════

def run_with_gateway(xml_context: str, query: str) -> tuple[float, int, int]:
    """
    Uruchamia pełny przepływ LangGraph Privacy Gateway.
    Zwraca (czas_sekundy, rozmiar_raw_bajty, rozmiar_masked_bajty).
    """
    from state import GraphState
    from privacy_gateway import build_graph

    app = build_graph()

    initial_state = GraphState(
        raw_xml=xml_context,
        user_query=query,
        detected_pii=[],
        masked_context="",
        masked_query="",
        vault={},
        is_safe=False,
        cloud_response="",
        final_output="",
    )

    raw_payload_size = len((xml_context + "\n" + query).encode("utf-8"))

    start = time.perf_counter()
    final_state = app.invoke(initial_state)
    elapsed = time.perf_counter() - start

    masked_ctx = final_state.get("masked_context", "")
    masked_q = final_state.get("masked_query", "")
    masked_payload_size = len((masked_ctx + "\n" + masked_q).encode("utf-8"))

    return elapsed, raw_payload_size, masked_payload_size


# ══════════════════════════════════════════════════════════════════════════════
# 3. Statystyki pomocnicze
# ══════════════════════════════════════════════════════════════════════════════

def calc_stats(values: list[float]) -> dict:
    """Oblicza podstawowe statystyki opisowe."""
    if not values:
        return {"mean": 0, "std": 0, "median": 0, "min": 0, "max": 0}
    return {
        "mean": statistics.mean(values),
        "std": statistics.stdev(values) if len(values) > 1 else 0.0,
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. Główna pętla benchmarku
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("EKSPERYMENT 4 – Latency Benchmark & Payload Reduction")
    print("=" * 70)

    # Sprawdzenie klucza API
    if "GOOGLE_API_KEY" not in os.environ:
        # Próba załadowania z .env
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("GOOGLE_API_KEY="):
                    os.environ["GOOGLE_API_KEY"] = line.split("=", 1)[1].strip()
                    break
        if "GOOGLE_API_KEY" not in os.environ:
            print("[BŁĄD] Brak zmiennej GOOGLE_API_KEY. Ustaw ją w pliku .env lub środowisku.")
            sys.exit(1)

    # Załaduj XML
    xml_path = PROJECT_ROOT / "fake_data.xml"
    if not xml_path.exists():
        print(f"[BŁĄD] Brak pliku: {xml_path}")
        sys.exit(1)

    xml_context = xml_path.read_text(encoding="utf-8")
    print(f"[E4] Załadowano kontekst XML ({len(xml_context)} bajtów).")
    print(f"[E4] N = {N_REPEATS} powtórzeń per zapytanie per konfiguracja.\n")

    detail_rows = []
    summary_rows = []

    for q_idx, query in enumerate(TEST_QUERIES):
        print(f"\n{'─' * 60}")
        print(f"Zapytanie {q_idx + 1}: \"{query}\"")
        print(f"{'─' * 60}")

        direct_times = []
        direct_payload_sizes = []
        gateway_times = []
        gateway_raw_sizes = []
        gateway_masked_sizes = []

        # ── Konfiguracja A: Direct Gemini ─────────────────────────────
        print(f"\n  [A] Bezpośredni Gemini (bez Gateway):")
        for i in range(N_REPEATS):
            try:
                elapsed, payload_size = run_direct_gemini(xml_context, query)
                direct_times.append(elapsed)
                direct_payload_sizes.append(payload_size)
                print(f"    Powtórzenie {i+1}/{N_REPEATS}: {elapsed*1000:.0f} ms, "
                      f"payload: {payload_size} B")
            except Exception as e:
                print(f"    Powtórzenie {i+1}/{N_REPEATS}: BŁĄD – {e}")

        # ── Konfiguracja B: Z Gateway ─────────────────────────────────
        print(f"\n  [B] Pełny Privacy Gateway (LangGraph):")
        for i in range(N_REPEATS):
            try:
                elapsed, raw_size, masked_size = run_with_gateway(xml_context, query)
                gateway_times.append(elapsed)
                gateway_raw_sizes.append(raw_size)
                gateway_masked_sizes.append(masked_size)
                print(f"    Powtórzenie {i+1}/{N_REPEATS}: {elapsed*1000:.0f} ms, "
                      f"raw: {raw_size} B → masked: {masked_size} B "
                      f"(redukcja: {(1 - masked_size/raw_size)*100:.1f}%)")
            except Exception as e:
                print(f"    Powtórzenie {i+1}/{N_REPEATS}: BŁĄD – {e}")

        # ── Statystyki per zapytanie ──────────────────────────────────
        direct_stats = calc_stats(direct_times)
        gateway_stats = calc_stats(gateway_times)

        overhead_ms = (gateway_stats["mean"] - direct_stats["mean"]) * 1000 if direct_stats["mean"] > 0 else 0
        overhead_pct = ((gateway_stats["mean"] / direct_stats["mean"]) - 1) * 100 if direct_stats["mean"] > 0 else 0

        avg_raw = statistics.mean(gateway_raw_sizes) if gateway_raw_sizes else 0
        avg_masked = statistics.mean(gateway_masked_sizes) if gateway_masked_sizes else 0
        payload_reduction_pct = (1 - avg_masked / avg_raw) * 100 if avg_raw > 0 else 0

        # Detail rows
        for i in range(max(len(direct_times), len(gateway_times))):
            detail_rows.append({
                "query_idx": q_idx,
                "repeat": i + 1,
                "direct_time_ms": round(direct_times[i] * 1000, 1) if i < len(direct_times) else "",
                "direct_payload_B": direct_payload_sizes[i] if i < len(direct_payload_sizes) else "",
                "gateway_time_ms": round(gateway_times[i] * 1000, 1) if i < len(gateway_times) else "",
                "gateway_raw_B": gateway_raw_sizes[i] if i < len(gateway_raw_sizes) else "",
                "gateway_masked_B": gateway_masked_sizes[i] if i < len(gateway_masked_sizes) else "",
            })

        summary_rows.append({
            "query_idx": q_idx,
            "query": query,
            "direct_mean_ms": round(direct_stats["mean"] * 1000, 1),
            "direct_std_ms": round(direct_stats["std"] * 1000, 1),
            "gateway_mean_ms": round(gateway_stats["mean"] * 1000, 1),
            "gateway_std_ms": round(gateway_stats["std"] * 1000, 1),
            "overhead_ms": round(overhead_ms, 1),
            "overhead_pct": round(overhead_pct, 1),
            "avg_raw_payload_B": round(avg_raw),
            "avg_masked_payload_B": round(avg_masked),
            "payload_reduction_pct": round(payload_reduction_pct, 1),
        })

    # ── Podsumowanie ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("WYNIKI ZAGREGOWANE")
    print("=" * 70)

    for s in summary_rows:
        print(f"\n  Zapytanie {s['query_idx'] + 1}: \"{s['query'][:50]}...\"")
        print(f"    Direct Gemini:   średnio {s['direct_mean_ms']:.0f} ± {s['direct_std_ms']:.0f} ms")
        print(f"    Z Gateway:       średnio {s['gateway_mean_ms']:.0f} ± {s['gateway_std_ms']:.0f} ms")
        print(f"    Overhead:        +{s['overhead_ms']:.0f} ms (+{s['overhead_pct']:.1f}%)")
        print(f"    Redukcja payloadu: {s['payload_reduction_pct']:.1f}% "
              f"({s['avg_raw_payload_B']} → {s['avg_masked_payload_B']} B)")

    # Globalne średnie
    all_direct = [s["direct_mean_ms"] for s in summary_rows]
    all_gateway = [s["gateway_mean_ms"] for s in summary_rows]
    all_reduction = [s["payload_reduction_pct"] for s in summary_rows]
    print(f"\n  ── GLOBALNE ŚREDNIE ──")
    print(f"    Direct Gemini:      {statistics.mean(all_direct):.0f} ms")
    print(f"    Z Gateway:          {statistics.mean(all_gateway):.0f} ms")
    print(f"    Redukcja payloadu:  {statistics.mean(all_reduction):.1f}%")

    # ── Zapis CSV ─────────────────────────────────────────────────────────
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # CSV szczegółowy
    detail_csv = RESULTS_DIR / "results_e4_detail.csv"
    if detail_rows:
        with open(detail_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(detail_rows[0].keys()))
            writer.writeheader()
            writer.writerows(detail_rows)

    # CSV podsumowujący
    if summary_rows:
        with open(RESULTS_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
            writer.writeheader()
            writer.writerows(summary_rows)

    print(f"\n[E4] Wyniki szczegółowe → {detail_csv}")
    print(f"[E4] Wyniki sumaryczne → {RESULTS_CSV}")


if __name__ == "__main__":
    main()
