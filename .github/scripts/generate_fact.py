import json
import urllib.request
import os
from datetime import datetime, timezone

MONTHS_IS = [
    "janúar", "febrúar", "mars", "apríl", "maí", "júní",
    "júlí", "ágúst", "september", "október", "nóvember", "desember"
]

now = datetime.now(timezone.utc)
month = MONTHS_IS[now.month - 1]
day = now.day

api_key = os.environ["GEMINI_API_KEY"]
url = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.5-flash:generateContent?key={api_key}"
)

prompt = f"""Þú ert íslenskur sagnfræðingur. Dagurinn í dag er {day}. {month}.

Segðu mér eina áhugaverða og nákvæma söguleg staðreynd sem tengist þessum degi ({day}. {month}) á hvaða ári sem er.
Gefðu forgang íslenskri sögu (Ísland, Norðurlönd, Víkingar), en heimssaga er líka í lagi ef hún er sérstaklega áhugaverð.

Svaraðu EINGÖNGU með JSON hlut á þessu nákvæma formi (engar markdown merkingar, ekkert annað):
{{
  "ar": "Ártal atburðarins (t.d. 1944)",
  "fyrirsogn": "Ein setnig sem lýsir atburðinum á íslensku.",
  "smaaatridi": "Tvær eða þrjár setningar með áhugaverðum bakgrunni eða eftirmálum á íslensku."
}}"""

body = json.dumps({
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {
        "temperature": 0.8,
        "maxOutputTokens": 1024,
        "responseMimeType": "application/json",
        "thinkingConfig": {"thinkingBudget": 0}
    }
}).encode()

req = urllib.request.Request(
    url, data=body, headers={"Content-Type": "application/json"}
)
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.reason}")
    print(e.read().decode())
    raise

raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
raw = raw.replace("```json", "").replace("```", "").strip()
fact = json.loads(raw)
fact["date"] = now.strftime("%Y-%m-%d")

with open("fact.json", "w", encoding="utf-8") as f:
    json.dump(fact, f, ensure_ascii=False, indent=2)

print(f"✓ {day}. {month} ({fact['ar']}): {fact['fyrirsogn']}")
