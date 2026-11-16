import re

with open('chatbot.html', 'r', encoding='utf-8') as f:
    html = f.read()

# All getElementById references in scripts
js_ids = set(re.findall(r'document\.getElementById\([\'"](.*?)[\'"]\)', html))

# All id="..." in HTML
dom_ids = set(re.findall(r'\bid=[\'"](.*?)[\'"]', html))

missing = js_ids - dom_ids
print(f"Total JS ID calls in chatbot.html: {len(js_ids)}")
print(f"Total DOM IDs defined in chatbot.html: {len(dom_ids)}")
if missing:
    print("WARNING: Missing DOM IDs found in chatbot.html:", missing)
else:
    print("SUCCESS: 100% of DOM IDs referenced in JS exist in chatbot.html!")
