import json
import urllib.request
import urllib.error
import os
from datetime import datetime, timezone

MONTHS_IS = [
    "janúar", "febrúar", "mars", "apríl", "maí", "júní",
    "júlí", "ágúst", "september", "október", "nóvember", "desember"
]
WEEKDAYS_IS = [
    "Mánudagur", "Þriðjudagur", "Miðvikudagur",
    "Fimmtudagur", "Föstudagur", "Laugardagur", "Sunnudagur"
]

now = datetime.now(timezone.utc)
month = MONTHS_IS[now.month - 1]
day = now.day
weekday = WEEKDAYS_IS[now.weekday()]
day_of_year = now.timetuple().tm_yday

# Sunrise/sunset for Reykjavik (Iceland = UTC+0, no DST)
sun_url = (
    f"https://api.sunrise-sunset.org/json"
    f"?lat=64.1355&lng=-21.8954&date={now.strftime('%Y-%m-%d')}&formatted=0"
)
try:
    with urllib.request.urlopen(sun_url) as r:
        sun = json.loads(r.read())["results"]
    sunrise = datetime.fromisoformat(sun["sunrise"]).strftime("%H:%M")
    sunset  = datetime.fromisoformat(sun["sunset"]).strftime("%H:%M")
except Exception as e:
    print(f"Sunrise API villa: {e}")
    sunrise = sunset = ""

# Gemini
api_key = os.environ["GEMINI_API_KEY"]
url = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.5-flash:generateContent?key={api_key}"
)

prompt = f"""Þú ert íslenskur sagnfræðingur. Dagurinn í dag er {day}. {month}.

Gefðu mér eftirfarandi á íslensku. Svaraðu EINGÖNGU með JSON á þessu formi:
{{
  "atburdir": [
    {{"ar": "ártal", "texti": "stuttur lýsing á atburði sem átti sér stað þennan dag í sögunni"}},
    {{"ar": "ártal", "texti": "lýsing"}},
    {{"ar": "ártal", "texti": "lýsing"}},
    {{"ar": "ártal", "texti": "lýsing"}},
    {{"ar": "ártal", "texti": "lýsing"}}
  ],
  "afmaeli": [
    {{"nafn": "fullt nafn", "starfsgrein": "leikari / tónlistarmaður / íþróttamaður / o.fl.", "ar": "fæðingarár"}},
    {{"nafn": "fullt nafn", "starfsgrein": "starfsgrein", "ar": "fæðingarár"}},
    {{"nafn": "fullt nafn", "starfsgrein": "starfsgrein", "ar": "fæðingarár"}}
  ],
  "tonlistUSA": "Nafn lags – Flytjandi (#1 á Billboard þennan dag)",
  "tonlistUK": "Nafn lags – Flytjandi (#1 á UK listanum þennan dag)",
  "bio": "Nafn kvikmyndar (#1 í Bandaríkjunum þennan dag)"
}}

Leiðbeiningar:
- Gefðu forgang íslenskri og norrænnri sögu í atburðarlista
- Afmælisfólk skal vera þekkt alþjóðlega
- Tónlist og kvikmyndir skulu vera frá mismunandi árum (ekki alltaf sama árið)
- Sé þér óvíst um tónlist eða kvikmynd, gefðu þitt besta svar"""

body = json.dumps({
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {
        "temperature": 0.7,
        "maxOutputTokens": 2048,
        "responseMimeType": "application/json",
        "thinkingConfig": {"thinkingBudget": 0}
    }
}).encode()

req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.reason}")
    print(e.read().decode())
    raise

raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
raw = raw.replace("```json", "").replace("```", "").strip()
gemini = json.loads(raw)

fact = {
    "date":        now.strftime("%Y-%m-%d"),
    "dagur":       day,
    "manudur":     month,
    "vikudagur":   weekday,
    "dagurArsins": day_of_year,
    "sunrise":     sunrise,
    "sunset":      sunset,
    **gemini
}

with open("fact.json", "w", encoding="utf-8") as f:
    json.dump(fact, f, ensure_ascii=False, indent=2)

print(f"✓ {day}. {month} ({weekday}), dagur {day_of_year}")
print(f"  Sólarupprás {sunrise} · Sólarlag {sunset}")
print(f"  {len(fact.get('atburdir', []))} atburðir · {len(fact.get('afmaeli', []))} afmæli")
