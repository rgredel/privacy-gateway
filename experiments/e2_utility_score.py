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

import asyncio

def run_masking_scenario(text: str, pii_list: list[str], mode: str):
    """Wykonuje maskowanie w jednym z trzech trybów."""
    from src.app.core.config import settings
    from src.app.infrastructure.llm.factory import get_local_model, get_cloud_gemini_2_5_flash
    from src.app.infrastructure.llm.langchain_service import LangChainService
    from src.app.use_cases.labeling_use_case import LabelingUseCase
    from src.app.infrastructure.services.presidio_service import PresidioService
    
    local_llm = get_local_model(model_name=settings.local_model_default)
    cloud_llm = get_cloud_gemini_2_5_flash(model_name=settings.cloud_model_default)
    llm_service = LangChainService(local_llm=local_llm, cloud_llm=cloud_llm)
    privacy_engine = PresidioService(analyzer=None)
    
    labeling_uc = LabelingUseCase(llm_service=llm_service)
    
    # Krok 1: Etykietowanie
    if mode in ["semantic", "native"]:
        # Używamy LLM do etykietowania
        entities_pydantic = asyncio.run(labeling_uc.execute(pii_list))
        # Konwersja na dict dla maskowania
        labeled_entities = [{"value": e.value, "label": e.label} for e in entities_pydantic]
    else: # generic
        labeled_entities = [{"value": val, "label": "PII"} for val in pii_list]
        
    # Krok 2: Maskowanie
    if mode == "native":
        # Native: używamy bezpośrednio Presidio Anonymizer
        from presidio_anonymizer.entities import RecognizerResult
        # Tworzymy fałszywe wyniki RecognizerResult z etykiet na potrzeby Anonymizera
        results = []
        for e in labeled_entities:
            start = text.find(e["value"])
            if start != -1:
                results.append(RecognizerResult(
                    entity_type=e["label"], 
                    start=start, 
                    end=start+len(e["value"]), 
                    score=1.0
                ))
        anonymized_result = privacy_engine.anonymizer.anonymize(text=text, analyzer_results=results)
        masked_text = anonymized_result.text
    else:
        # Semantic & Generic: używamy własnej logiki podmieniania tekstowego (z PrivacyEngine)
        masked_text, _ = privacy_engine.mask_text(text, labeled_entities)
        
    return masked_text

def main():
    print("=" * 70)
    print("EKSPERYMENT 2 – Porównanie użyteczności: Generyczne vs Semantyczne vs Native")
    print("=" * 70)

    with open(CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)

    docs_with_pii = [d for d in corpus if len(d["pii"]) > 0]
    print(f"[E2] Analiza {len(docs_with_pii)} dokumentów.\n")

    originals = []
    masked_generic = []
    masked_semantic = []
    masked_native = []

    for i, doc in enumerate(docs_with_pii):
        print(f"[E2] Przetwarzanie dokumentu {i+1}/{len(docs_with_pii)} (ID: {doc['doc_id']})...")
        text = doc["text"]
        originals.append(text)
        
        # Scenariusz A: Generyczny
        print(f"  - Generowanie maskowania generycznego...")
        masked_generic.append(run_masking_scenario(text, doc["pii"], mode="generic"))
        
        # Scenariusz B: Semantyczny
        print(f"  - Generowanie maskowania semantycznego (LLM Labeling)...")
        masked_semantic.append(run_masking_scenario(text, doc["pii"], mode="semantic"))
        
        # Scenariusz C: Native (AnonymizerEngine)
        print(f"  - Generowanie maskowania natywnego (Presidio Transformation)...")
        masked_native.append(run_masking_scenario(text, doc["pii"], mode="native"))

    print("[E2] Obliczanie BERTScore dla wszystkich scenariuszy...")
    res_generic = compute_bertscore(originals, masked_generic)
    res_semantic = compute_bertscore(originals, masked_semantic)
    res_native = compute_bertscore(originals, masked_native)

    rows = []
    for i, doc in enumerate(docs_with_pii):
        f1_gen = res_generic[i]["f1"]
        f1_sem = res_semantic[i]["f1"]
        f1_nat = res_native[i]["f1"]
        
        rows.append({
            "doc_id": doc["doc_id"],
            "category": doc["category"],
            "f1_generic": round(f1_gen, 4),
            "f1_semantic": round(f1_sem, 4),
            "f1_native": round(f1_nat, 4),
            "improvement_sem": round((f1_sem - f1_gen) * 100, 2),
            "improvement_nat": round((f1_nat - f1_gen) * 100, 2)
        })

    # Podsumowanie
    avg_gen = sum(r["f1_generic"] for r in rows) / len(rows)
    avg_sem = sum(r["f1_semantic"] for r in rows) / len(rows)
    avg_nat = sum(r["f1_native"] for r in rows) / len(rows)

    print("\n" + "=" * 70)
    print("WYNIKI PORÓWNAWCZE")
    print("=" * 70)
    print(f"  Średni BERTScore (Generyczny): {avg_gen:.4f}")
    print(f"  Średni BERTScore (Semantyczny): {avg_sem:.4f}")
    print(f"  Średni BERTScore (Native):     {avg_nat:.4f}")
    print(f"  Poprawa (Semantyczny vs Gen): {avg_sem - avg_gen:+.4f}")
    print(f"  Poprawa (Native vs Gen):      {avg_nat - avg_gen:+.4f}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n[E2] Wyniki porównawcze zapisane → {RESULTS_CSV}")

if __name__ == "__main__":
    main()
