import json

def merge_text_field(field):
    if isinstance(field, list):
        return ''.join(item.get('text', '') for item in field)
    return field

with open('script.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for obj in data:
    for key in ['ability', 'otherNightReminder', 'firstNightReminder']:
        if key in obj:
            obj[key] = merge_text_field(obj[key])
    if 'jinxes' in obj:
        del obj['jinxes']

with open('script_unformatted.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)