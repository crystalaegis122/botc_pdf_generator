import json

TEAM_ORDER = {
    "townsfolk": 0,
    "outsider": 1,
    "minion": 2,
    "demon": 3,
    "fabled": 4,
    "loric": 5,
    "traveler": 6
}

def ability_length(ability):
    if isinstance(ability, list):
        return sum(len(item.get("text", "")) for item in ability)
    return 0

with open("script.json", "r", encoding="utf-8") as f:
    data = json.load(f)

filtered = [obj for obj in data if "team" in obj]

sorted_data = sorted(
    filtered,
    key=lambda obj: (
        TEAM_ORDER.get(obj.get("team"), 999),
        ability_length(obj.get("ability")),
        len(obj.get("name", "")),
        obj.get("name", "")
    )
)

for obj in sorted_data:
    print(obj.get("name", ""))