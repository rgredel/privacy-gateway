import json
import time
import re
import csv
from typing import List, Dict, Any, Optional

from presidio_analyzer import AnalyzerEngine, RecognizerResult, EntityRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from nervaluate import Evaluator
import warnings

# Ignore some transformers warnings for cleaner output
warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# 1. Checksum Validators for Polish IDs
# ---------------------------------------------------------------------------

def validate_pesel(pesel: str) -> bool:
    if not re.match(r'^\d{11}$', pesel):
        return False
    weights = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    checksum = sum(int(pesel[i]) * weights[i] for i in range(10)) % 10
    control = (10 - checksum) % 10
    return control == int(pesel[10])

def validate_nip(nip: str) -> bool:
    nip = nip.replace("-", "").replace(" ", "")
    if not re.match(r'^\d{10}$', nip):
        return False
    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    checksum = sum(int(nip[i]) * weights[i] for i in range(9)) % 11
    return checksum == int(nip[9]) if checksum != 10 else False

def validate_regon(regon: str) -> bool:
    if not re.match(r'^\d{9}$', regon) and not re.match(r'^\d{14}$', regon):
        return False
    weights_9 = [8, 9, 2, 3, 4, 5, 6, 7]
    checksum_9 = sum(int(regon[i]) * weights_9[i] for i in range(8)) % 11
    if checksum_9 == 10: checksum_9 = 0
    if len(regon) == 9:
        return checksum_9 == int(regon[8])
        
    if len(regon) == 14:
        if checksum_9 != int(regon[8]): return False
        weights_14 = [2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8]
        checksum_14 = sum(int(regon[i]) * weights_14[i] for i in range(13)) % 11
        if checksum_14 == 10: checksum_14 = 0
        return checksum_14 == int(regon[13])
    return False

class PolishIdRecognizer(EntityRecognizer):
    """Custom Recognizer for Polish ID Numbers (PESEL, NIP, REGON) with checksum validation."""
    def __init__(self):
        super().__init__(supported_entities=["ID_NUMBER"], supported_language="pl")
        
    def load(self) -> None:
        pass
        
    def analyze(self, text: str, entities: List[str], nlp_artifacts: Any = None) -> List[RecognizerResult]:
        results = []
        
        # PESEL
        for match in re.finditer(r'\b\d{11}\b', text):
            if validate_pesel(match.group()):
                results.append(RecognizerResult(entity_type="ID_NUMBER", start=match.start(), end=match.end(), score=0.9))
                
        # NIP (various formats)
        for match in re.finditer(r'\b(?:\d{3}[- ]?\d{3}[- ]?\d{2}[- ]?\d{2}|\d{10})\b', text):
            if validate_nip(match.group().replace("-", "").replace(" ", "")):
                results.append(RecognizerResult(entity_type="ID_NUMBER", start=match.start(), end=match.end(), score=0.9))
                
        # REGON
        for match in re.finditer(r'\b(?:\d{9}|\d{14})\b', text):
            if validate_regon(match.group()):
                results.append(RecognizerResult(entity_type="ID_NUMBER", start=match.start(), end=match.end(), score=0.9))
                
        return results

# ---------------------------------------------------------------------------
# 2. LLM Judge Setup
# ---------------------------------------------------------------------------

class LLMJudge:
    def __init__(self, model_name: str = "bielik"):
        # We assume Ollama or Langchain is used. 
        # For this script we simulate the call if not fully configured,
        # but integrate the structure for Bielik.
        try:
            from langchain_ollama import OllamaLLM
            self.llm = OllamaLLM(model=model_name, temperature=0.0)
            self.is_mock = False
        except ImportError:
            print("Warning: langchain_ollama not found. Using mock LLM Judge.")
            self.is_mock = True

    def evaluate(self, context: str, entity_text: str, predicted_label: str, confidence: float) -> Dict[str, Any]:
        prompt = f"""System:
Jesteś ekspertem RODO i lingwistyki komputerowej. Twoim zadaniem jest rozstrzygnięcie, czy dany fragment tekstu to faktycznie dana osobowa (PII).

Dane wejściowe:
KONTEKST: "{context}"

PODEJRZANA FRAZA: "{entity_text}"

WSTĘPNA ETYKIETA: "{predicted_label}"

PEWNOŚĆ MODELU: {confidence}

Zadanie:
Przeanalizuj kontekst. Odpowiedz, czy fraza jest daną osobową (np. imieniem konkretnej osoby, a nie nazwą pospolitą jak "janusz biznesu"). Jeśli to numer (PESEL/NIP), sprawdź czy kontekst wskazuje na dokument tożsamości, czy np. numer faktury technicznej.

Wyjście (Format JSON):
{{
"is_pii": true,
"reasoning": "Krótkie uzasadnienie po polsku",
"refined_label": "{predicted_label}",
"final_confidence": 0.95
}}"""
        if self.is_mock:
            # Mock behavior: just accept it to show pipeline flow
            return {"is_pii": True, "reasoning": "Mock accepted", "refined_label": predicted_label, "final_confidence": 0.9}
        
        try:
            response = self.llm.invoke(prompt)
            # Extract JSON block
            json_str = re.search(r'\{.*\}', response, re.DOTALL)
            if json_str:
                return json.loads(json_str.group())
            return {}
        except Exception as e:
            print(f"LLM Error: {e}")
            return {}

def llm_augmented_analyze(analyzer: AnalyzerEngine, judge: LLMJudge, text: str) -> List[RecognizerResult]:
    results = analyzer.analyze(text=text, language="pl")
    refined_results = []
    
    for res in results:
        # Check if confidence is in ambiguous range [0.3, 0.7]
        if 0.3 <= res.score <= 0.7:
            # Context window +/- 5 words
            words_before = text[:res.start].split()[-5:]
            words_after = text[res.end:].split()[:5]
            context_window = " ".join(words_before + [text[res.start:res.end]] + words_after)
            
            entity_text = text[res.start:res.end]
            decision = judge.evaluate(context_window, entity_text, res.entity_type, res.score)
            
            if decision.get("is_pii"):
                res.score = decision.get("final_confidence", res.score)
                res.entity_type = decision.get("refined_label", res.entity_type)
                refined_results.append(res)
        else:
            refined_results.append(res)
            
    return refined_results

# ---------------------------------------------------------------------------
# 3. Evaluator Class
# ---------------------------------------------------------------------------

class PolishPiiEvaluator:
    def __init__(self, texts: List[str], ground_truth: List[List[Dict[str, Any]]]):
        self.texts = texts
        self.ground_truth = ground_truth
        self.results = []

    def evaluate_pipeline(self, name: str, analyze_fn) -> Dict[str, Any]:
        print(f"Evaluating Pipeline: {name}...")
        start_time = time.time()
        
        predictions = []
        total_tokens = 0
        
        for text in self.texts:
            total_tokens += len(text.split())
            results = analyze_fn(text)
            
            # Format to nervaluate expectations
            text_preds = [{"start": res.start, "end": res.end, "label": res.entity_type} for res in results]
            predictions.append(text_preds)
            
        latency = time.time() - start_time
        latency_per_1000_tokens = (latency / max(total_tokens, 1)) * 1000
        
        evaluator = Evaluator(self.ground_truth, predictions, tags=["PERSON", "LOCATION", "ORGANIZATION", "ID_NUMBER"])
        eval_res = evaluator.evaluate()
        metrics = eval_res.get('overall', {})
        metrics_by_tag = eval_res.get('entities', {})
        
        # We focus on strict evaluation for the summary
        strict_metrics = metrics.get('strict')
        if strict_metrics:
            tp = getattr(strict_metrics, 'correct', 0)
            fp = getattr(strict_metrics, 'actual', 0) - tp
            fn = getattr(strict_metrics, 'possible', 0) - tp
            precision = getattr(strict_metrics, 'precision', 0)
            recall = getattr(strict_metrics, 'recall', 0)
            f1 = getattr(strict_metrics, 'f1', 0)
        else:
            tp = fp = fn = precision = recall = f1 = 0

        # Convert metrics_by_tag objects to dicts for JSON serialization
        serializable_metrics_by_tag = {}
        for tag, tag_metrics in metrics_by_tag.items():
            serializable_metrics_by_tag[tag] = {}
            for metric_type, result_obj in tag_metrics.items():
                if hasattr(result_obj, '__dict__'):
                    serializable_metrics_by_tag[tag][metric_type] = vars(result_obj)
                else:
                    serializable_metrics_by_tag[tag][metric_type] = result_obj
        
        result = {
            "pipeline": name,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "false_positives": fp,
            "false_negatives": fn,
            "latency_per_1000_tokens": latency_per_1000_tokens,
            "metrics_by_tag": serializable_metrics_by_tag
        }
        
        self.results.append(result)
        return result

    def export_results(self, json_path: str = "pii_benchmark_results.json", csv_path: str = "pii_benchmark_results.csv"):
        # Save JSON
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=4, ensure_ascii=False)
            
        # Save CSV
        if self.results:
            keys = ["pipeline", "precision", "recall", "f1", "false_positives", "false_negatives", "latency_per_1000_tokens"]
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                for res in self.results:
                    writer.writerow({k: res[k] for k in keys})
        print(f"Results exported to {json_path} and {csv_path}")

# ---------------------------------------------------------------------------
# 4. Main Execution Setup
# ---------------------------------------------------------------------------

def load_corpus() -> tuple[List[str], List[List[Dict[str, Any]]]]:
    corpus_path = "experiments/corpus/corpus.json"
    try:
        with open(corpus_path, "r", encoding="utf-8") as f:
            corpus = json.load(f)
    except Exception as e:
        print(f"Failed to load corpus: {e}")
        return [], []

    texts = []
    ground_truth = []
    
    for doc in corpus:
        text = doc.get("text", "")
        piis = doc.get("pii", [])
        texts.append(text)
        
        doc_gt = []
        for pii_str in piis:
            if any(c.isdigit() for c in pii_str):
                label = "ID_NUMBER"
            elif any(city in pii_str for city in ["Kraków", "Gdańsk", "Warszawa"]):
                label = "LOCATION"
            elif any(org in pii_str for org in ["Biuro", "Usługi", "Kancelaria"]):
                label = "ORGANIZATION"
            else:
                label = "PERSON"
                
            start_idx = text.find(pii_str)
            if start_idx != -1:
                doc_gt.append({
                    "start": start_idx,
                    "end": start_idx + len(pii_str),
                    "label": label
                })
        ground_truth.append(doc_gt)
        
    return texts, ground_truth

def run_benchmark():
    texts, ground_truth = load_corpus()
    if not texts:
        print("No test data found.")
        return

    evaluator = PolishPiiEvaluator(texts, ground_truth)

    # ---------------------------------------------------------
    # Pipeline A: spaCy Baseline
    # ---------------------------------------------------------
    spacy_config = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "pl", "model_name": "pl_core_news_lg"}],
        "ner_model_configuration": {
            "model_to_presidio_entity_mapping": {
                "persName": "PERSON",
                "placeName": "LOCATION",
                "orgName": "ORGANIZATION"
            }
        }
    }
    provider_a = NlpEngineProvider(nlp_configuration=spacy_config)
    engine_a = provider_a.create_engine()
    analyzer_a = AnalyzerEngine(nlp_engine=engine_a, supported_languages=["pl"])
    
    evaluator.evaluate_pipeline("Pipeline A (spaCy)", lambda t: analyzer_a.analyze(text=t, language="pl"))

    # ---------------------------------------------------------
    # Pipeline B: Transformer SOTA
    # ---------------------------------------------------------
    # Config for TransformersNlpEngine using aggregation_strategy="max"
    transformer_config = {
        "nlp_engine_name": "transformers",
        "models": [
            {
                "lang_code": "pl",
                "model_name": {
                    "spacy": "pl_core_news_lg", 
                    "transformers": "pczarnik/herbert-base-ner"
                }
            }
        ],
        "ner_model_configuration": {
            "labels_to_ignore": ["O"],
            "aggregation_strategy": "simple",
            "stride": 16,
            "alignment_mode": "expand",
            "model_to_presidio_entity_mapping": {
                "PER": "PERSON",
                "LOC": "LOCATION",
                "ORG": "ORGANIZATION"
            }
        }
    }
    
    try:
        provider_b = NlpEngineProvider(nlp_configuration=transformer_config)
        engine_b = provider_b.create_engine()
        analyzer_b = AnalyzerEngine(nlp_engine=engine_b, supported_languages=["pl"])
        evaluator.evaluate_pipeline("Pipeline B (Transformers)", lambda t: analyzer_b.analyze(text=t, language="pl"))
    except Exception as e:
        print(f"Failed to load Pipeline B: {e}")
        analyzer_b = None

    if analyzer_b:
        # ---------------------------------------------------------
        # Pipeline C: Logic-Enhanced
        # ---------------------------------------------------------
        # Add custom recognizer to pipeline B's analyzer
        id_recognizer = PolishIdRecognizer()
        analyzer_b.registry.add_recognizer(id_recognizer)
        
        evaluator.evaluate_pipeline("Pipeline C (Logic-Enhanced)", lambda t: analyzer_b.analyze(text=t, language="pl"))

        # ---------------------------------------------------------
        # Pipeline D: LLM-Augmented
        # ---------------------------------------------------------
        judge = LLMJudge(model_name="bielik") # Configured for Bielik
        evaluator.evaluate_pipeline("Pipeline D (LLM-Augmented)", lambda t: llm_augmented_analyze(analyzer_b, judge, t))

    # Export results
    evaluator.export_results("src/app/experiments/pii_benchmark_results.json", "src/app/experiments/pii_benchmark_results.csv")

if __name__ == "__main__":
    print("Rozpoczynanie benchmarku PII...")
    run_benchmark()
