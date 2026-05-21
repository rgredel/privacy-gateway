import json
import random
import re
import os
from faker import Faker
from datetime import datetime

# Initialize Faker with Polish locale
fake = Faker('pl_PL')

# Configuration
TEMPLATES_FILE = 'scripts/data_gen/templates.json'
OUTPUT_FILE = 'experiments/corpus/benchmark_corpus.json'
TOTAL_DOCS = 300
PROPORTIONS = {
    'ocr': 120,
    'transfers': 75,
    'contracts': 60,
    'emails': 45
}

# New methodology markers
MARKERS = [
    '<PER>', '<LOC>', '<ORG>', '<NIP>', '<REGON>', 
    '<PESEL>', '<ACCT>', '<DATE>', '<MISC_FIN>', 
    '<EMAIL>', '<PHONE>', '<INV>'
]

def generate_pii_value(marker):
    """Generates a value for a marker and decides if it's PII in this context."""
    is_pii = True
    
    if marker == '<PER>':
        val = fake.name()
        # JDG: Sole Proprietorship context (30% chance)
        if random.random() > 0.7:
            prefix = random.choice(["PUH ", "Usługi ", "FHU ", "Kancelaria ", "Biuro ", "Firma "])
            val = f"{prefix}{val}"
        return val, True
        
    elif marker == '<LOC>':
        # Mix of full address and just city
        if random.random() > 0.4:
            # Full address is PII
            return fake.address().replace('\n', ', '), True
        else:
            # Just city/country name (Not PII according to new methodology)
            return fake.city(), False
            
    elif marker == '<ORG>':
        # Large companies (Sp. z o.o., S.A.) are NO LONGER PII in the new methodology
        return fake.company(), False
        
    elif marker == '<NIP>':
        nip = fake.nip()
        fmt = random.choice(['raw', 'dash', 'space'])
        if fmt == 'dash': val = f"{nip[:3]}-{nip[3:6]}-{nip[6:8]}-{nip[8:]}"
        elif fmt == 'space': val = f"{nip[:3]} {nip[3:6]} {nip[6:8]} {nip[8:]}"
        else: val = nip
        return val, True
        
    elif marker == '<REGON>':
        return fake.regon(), True
        
    elif marker == '<PESEL>':
        return fake.pesel(), True
        
    elif marker == '<ACCT>':
        iban = fake.iban()
        if random.random() > 0.3:
            val = ' '.join([iban[i:i+4] for i in range(0, len(iban), 4)])
        else: val = iban
        return val, True
        
    elif marker == '<DATE>':
        dt = fake.date_between(start_date='-2y', end_date='today')
        fmt = random.choice(['%d.%m.%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'])
        # DATE is NO LONGER PII in E2/Final methodology
        return dt.strftime(fmt), False
        
    elif marker == '<MISC_FIN>':
        # Amounts
        val = round(random.uniform(10.0, 15000.0), 2)
        # MISC_FIN (Amounts) is NO LONGER PII
        return f"{val:.2f}", False
        
    elif marker == '<INV>':
        # Invoice numbers are PII
        year = random.randint(2022, 2024)
        num = random.randint(1, 1500)
        prefix = random.choice(["FV", "FA", "RCH", "NR"])
        return f"{prefix}/{num}/{year}", True
        
    elif marker == '<EMAIL>':
        return fake.email(), True
        
    elif marker == '<PHONE>':
        return fake.phone_number(), True
        
    return "N/A", False

def inject_noise(text, category):
    if category == 'ocr':
        if random.random() > 0.5:
            replacements = {'ą':'a', 'ć':'c', 'ę':'e', 'ł':'l', 'ń':'n', 'ó':'o', 'ś':'s', 'ź':'z', 'ż':'z'}
            for char, repl in replacements.items():
                if random.random() > 0.8:
                    text = text.replace(char, repl)
    return text

def process_template(template, category):
    entities = []
    current_text = template
    pattern = re.compile(r'<[A-Z_]+>')
    
    iteration = 0
    while True:
        match = pattern.search(current_text)
        if not match: break
        
        marker = match.group(0)
        start = match.start()
        
        value, is_pii = generate_pii_value(marker)
        current_text = current_text[:start] + value + current_text[match.end():]
        
        if is_pii:
            entity_label = marker[1:-1]
            entities.append({
                "start": start,
                "end": start + len(value),
                "label": entity_label,
                "text": value
            })
        iteration += 1
        if iteration > 150: break
            
    final_text = inject_noise(current_text, category)
    return final_text, entities

def main():
    if not os.path.exists(TEMPLATES_FILE):
        print(f"Error: {TEMPLATES_FILE} not found.")
        return

    with open(TEMPLATES_FILE, 'r', encoding='utf-8') as f:
        templates_data = json.load(f)

    corpus = []
    doc_id = 0

    for category, count in PROPORTIONS.items():
        templates = templates_data.get(category, [])
        if not templates: continue
            
        print(f"Generating {count} documents for category: {category}")
        for _ in range(count):
            template = random.choice(templates)
            text, entities = process_template(template, category)
            
            corpus.append({
                "doc_id": doc_id,
                "text": text,
                "entities": entities,
                "category": category,
                "metadata": {
                    "methodology": "2026_v2_no_dates_no_amounts",
                    "timestamp": datetime.now().isoformat()
                }
            })
            doc_id += 1

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated {len(corpus)} documents with NEW methodology to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
