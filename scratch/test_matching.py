import json
import urllib.parse

with open('scheme_cleaner/data/cleaned/cleaned_schemes.json', 'r', encoding='utf-8') as f:
    schemes = json.load(f)

test_inputs = [
    {"scheme": "Gruha Lakshmi Scheme", "id": "2"},
    {"scheme": "Lakshmi scheme", "id": None},
    {"scheme": "lakshmi", "id": None},
    {"scheme": "Yuva Nidhi Scheme", "id": "3"},
    {"scheme": "yuva nidhi", "id": None},
    {"scheme": "Gruha Jyoti Scheme", "id": "49"},
    {"scheme": "Shakti Scheme", "id": "51"},
    {"scheme": "Ganga Kalyana Scheme", "id": "52"},
    {"scheme": "Farmer Vidya Nidhi", "id": "53"},
    {"scheme": "CMEGP", "id": "54"},
    {"scheme": "Arivu", "id": "55"},
]

def match_scheme(scheme_param, id_param):
    if id_param:
        for s in schemes:
            if str(s.get('id')) == str(id_param) or str(s.get('scheme_id')) == str(id_param):
                return s
    if scheme_param:
        norm = scheme_param.lower().strip()
        for s in schemes:
            name = s.get('scheme_name', '').lower()
            if norm in name or name in norm:
                return s
        # Keyword matching
        for s in schemes:
            words = [w for w in norm.split() if len(w) > 3 and w not in ['scheme']]
            if any(w in s.get('scheme_name', '').lower() for w in words):
                return s
    return schemes[1] # Gruha Lakshmi default

print("Testing Scheme Matching:")
for t in test_inputs:
    matched = match_scheme(t['scheme'], t['id'])
    print(f"Input: {t} -> Matched: ID {matched.get('id')} - {matched.get('scheme_name')}")
