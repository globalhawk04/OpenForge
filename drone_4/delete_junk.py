import json
FILE = "drone_arsenal.json"
with open(FILE, "r") as f:
    data = json.load(f)

# Keep only items that have a model_name
valid_items = [x for x in data['components'] if 'model_name' in x]

print(f"Removed {len(data['components']) - len(valid_items)} malformed items.")
data['components'] = valid_items

with open(FILE, "w") as f:
    json.dump(data, f, indent=2)
