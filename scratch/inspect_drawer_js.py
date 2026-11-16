with open('index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("Line 1485-1510:")
for i in range(1484, min(1510, len(lines))):
    print(f"{i+1}: {lines[i]}", end='')

print("\nLine 1675-1710:")
for i in range(1674, min(1710, len(lines))):
    print(f"{i+1}: {lines[i]}", end='')
