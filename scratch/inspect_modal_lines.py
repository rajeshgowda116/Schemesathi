with open('index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("Line 505-515:")
for i in range(504, min(515, len(lines))):
    print(f"{i+1}: {lines[i]}", end='')

print("\nLine 585-595:")
for i in range(584, min(595, len(lines))):
    print(f"{i+1}: {lines[i]}", end='')

print("\nLine 695-705:")
for i in range(694, min(705, len(lines))):
    print(f"{i+1}: {lines[i]}", end='')
