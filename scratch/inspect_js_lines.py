with open('index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("Line 1210-1250:")
for i in range(1209, min(1250, len(lines))):
    print(f"{i+1}: {lines[i]}", end='')

print("\nLine 1285-1395:")
for i in range(1284, min(1395, len(lines))):
    print(f"{i+1}: {lines[i]}", end='')
