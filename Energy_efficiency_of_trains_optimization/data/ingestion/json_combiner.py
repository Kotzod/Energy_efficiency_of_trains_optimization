import json
from os import path
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
filename1 = PROJECT_ROOT / "data" / "raw" / "digitraffic_corridor_winter_2025-11-01_to_2025-12-26.json"
filename2 = PROJECT_ROOT / "data" / "raw" / "digitraffic_corridor_winter_run2.json"

if not path.isfile(filename1):
    raise FileNotFoundError(f"File not found: {filename1}")
if not path.isfile(filename2):
    raise FileNotFoundError(f"File not found: {filename2}")

with open(filename1) as fp:
    listObj1 = json.load(fp)

with open(filename2) as fn:
    listObj2 = json.load(fn)

print(f"Run 1: {len(listObj1)} trains")
print(f"Run 2: {len(listObj2)} trains")

listObj1.extend(listObj2)

output_path = PROJECT_ROOT / "data" / "raw" / "digitraffic_corridor_winter.json"
with open(output_path, 'w') as json_file:
    json.dump(listObj1, json_file, indent=4, separators=(',', ': '))

print(f"Combined {len(listObj1)} trains into {output_path}")