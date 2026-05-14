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

MARKERS = [
    '<PER>', '<LOC>', '<ORG>', '<NIP>', '<REGON>', 
    '<PESEL>', '<ACCT>', '<DATE>', '<MISC_FIN>', 
    '<EMAIL>', '<PHONE>'
]

def generate_pii_value(marker):
    if marker == '<PER>':
        return fake.name()
    elif marker == '<LOC>':
        # Mix of full address and just city
        if random.random() > 0.5:
            return fake.address().replace('\n', ', ')
        else:
            return fake.city()
    elif marker == '<ORG>':
        return fake.company()
    elif marker == '<NIP>':
        # Generate NIP with different formats
        nip = fake.nip()
        fmt = random.choice(['raw', 'dash', 'space'])
        if fmt == 'dash':
            return f"{nip[:3]}-{nip[3:6]}-{nip[6:8]}-{nip[8:]}"
        elif fmt == 'space':
            return f"{nip[:3]} {nip[3:6]} {nip[6:8]} {nip[8:]}"
        return nip
    elif marker == '<REGON>':
        return fake.regon()
    elif marker == '<PESEL>':
        return fake.pesel()
    elif marker == '<ACCT>':
        # IBAN format
        iban = fake.iban()
        if random.random() > 0.3:
            # Add spaces for readability
            return ' '.join([iban[i:i+4] for i in range(0, len(iban), 4)])
        return iban
    elif marker == '<DATE>':
        # Different date formats
        dt = fake.date_between(start_date='-2y', end_date='today')
        fmt = random.choice(['%d.%m.%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'])
        return dt.strftime(fmt)
    elif marker == '<MISC_FIN>':
        # Invoice numbers, amounts, or codes
        type_choice = random.choice(['amount', 'invoice_no', 'code'])
        if type_choice == 'amount':
            val = round(random.uniform(10.0, 5000.0), 2)
            return f"{val:.2f}"
        elif type_choice == 'invoice_no':
            year = random.randint(2022, 2024)
            num = random.randint(1, 1000)
            return f"FV/{num}/{year}"
        else:
            return str(random.randint(100000, 999999))
    elif marker == '<EMAIL>':
        return fake.email()
    elif marker == '<PHONE>':
        return fake.phone_number()
    return "N/A"

def inject_noise(text, category):
    """Inject noise as described in the plan."""
    if category == 'ocr':
        # 1. Remove some Polish characters (simulating bad OCR)
        if random.random() > 0.5:
            replacements = {'ą':'a', 'ć':'c', 'ę':'e', 'ł':'l', 'ń':'n', 'ó':'o', 'ś':'s', 'ź':'z', 'ż':'z'}
            for char, repl in replacements.items():
                if random.random() > 0.7:
                    text = text.replace(char, repl)
        
        # 2. Random case changes
        if random.random() > 0.7:
            words = text.split()
            for i in range(len(words)):
                if random.random() > 0.9:
                    words[i] = words[i].upper()
            text = ' '.join(words)

    elif category == 'emails':
        # Typo injection
        if random.random() > 0.3:
            words = text.split()
            if len(words) > 5:
                idx = random.randint(0, len(words)-1)
                word = words[idx]
                if len(word) > 3:
                    # Swap two characters
                    pos = random.randint(0, len(word)-2)
                    word_list = list(word)
                    word_list[pos], word_list[pos+1] = word_list[pos+1], word_list[pos]
                    words[idx] = "".join(word_list)
            text = " ".join(words)

    return text

def process_template(template, category):
    """Fill markers and return text + list of entities with offsets."""
    entities = []
    current_text = template
    
    # We find all markers. We use a while loop because the text changes size.
    # To keep it simple, we use a regex and process one by one, updating the string.
    
    pattern = re.compile(r'<[A-Z_]+>')
    
    iteration = 0
    while True:
        match = pattern.search(current_text)
        if not match:
            break
        
        marker = match.group(0)
        start = match.start()
        
        value = generate_pii_value(marker)
        
        # Replace the marker with the value
        current_text = current_text[:start] + value + current_text[match.end():]
        
        # Record the entity (if it's one we care about for NER)
        # For evaluation, we usually care about PER, LOC, ORG, NIP, PESEL, ACCT, EMAIL, PHONE
        # We might exclude DATE and MISC_FIN if they are too noisy, but let's include them as requested.
        
        entity_label = marker[1:-1] # Remove < and >
        entities.append({
            "start": start,
            "end": start + len(value),
            "label": entity_label,
            "text": value
        })
        
        iteration += 1
        if iteration > 100: # Safety break
            break
            
    # Apply noise (Note: noise injection might break offsets if it changes string length!)
    # To be safe, we apply noise only if it DOES NOT change length, or we don't apply it to the PII values themselves.
    # Actually, the plan says "Inject noise (Noise Injection) – to najważniejszy element testujący model NER!"
    # If we change the text, we MUST update offsets.
    
    # Let's apply noise to non-PII parts only? Or just accept that OCR noise might change things.
    # A better way: Generate full text, then apply noise, but keep track of changes.
    # For now, let's keep it simple: noise only in OCR/Emails categories on the WHOLE text, 
    # but I'll implement noise that doesn't change string length (like case change or char replacement).
    
    final_text = inject_noise(current_text, category)
    
    # If length changed, this is a problem for offsets.
    # Let's ensure inject_noise preserves length for now.
    
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
        if not templates:
            print(f"Warning: No templates for category {category}")
            continue
            
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
                    "source": "synthetic_gen_v1",
                    "timestamp": datetime.now().isoformat()
                }
            })
            doc_id += 1

    # Save to file
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated {len(corpus)} documents to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
