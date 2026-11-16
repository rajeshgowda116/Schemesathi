import re

with open('index.html', 'r', encoding='utf-8') as f:
    text = f.read()

matches = set(re.findall(r'document\.getElementById\([\'"](.*?)[\'"]\)', text))
print("Found IDs:")
for m in sorted(matches):
    print(m)
