import re

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# All getElementById references in scripts
js_ids = set(re.findall(r'document\.getElementById\([\'"](.*?)[\'"]\)', html))

# All id="..." in HTML
dom_ids = set(re.findall(r'\bid=[\'"](.*?)[\'"]', html))

missing = js_ids - dom_ids
print(f"Total JS ID calls: {len(js_ids)}")
print(f"Total DOM IDs defined: {len(dom_ids)}")
if missing:
    print("WARNING: Missing DOM IDs found in index.html:", missing)
else:
    print("SUCCESS: 100% of DOM IDs referenced in JS exist in HTML!")
