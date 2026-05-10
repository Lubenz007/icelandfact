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

def get_zodiac(month, day):
    if (month == 3 and day >= 21) or (month == 4 and day <= 19):   return "Hrútur"
    if (month == 4 and day >= 20) or (month == 5 and day <= 20):   return "Naut"
    if (month == 5 and day >= 21) or (month == 6 and day <= 20):   return "Tvíburar"
    if (month == 6 and day >= 21) or (month == 7 and day <= 22):   return "Krabbi"
    if (month == 7 and day >= 23) or (month == 8 and day <= 22):   return "Ljón"
    if (month == 8 and day >= 23) or (month == 9 and day <= 22):   return "Meyja"
    if (month == 9 and day >= 23) or (month == 10 and day <= 22):  return "Vog"
    if (month == 10 and day >= 23) or (month == 11 and day <= 21): return "Sporðdreki"
    if (month == 11 and day >= 22) or (month == 12 and day <= 21): return "Bogmaður"
    if (month == 12 and day >= 22) or (month == 1 and day <= 19):  return "Steinbukur"
    if (month == 1 and day >= 20) or (month == 2 and day <= 18):   return "Vatnsberi"
    return "Fiskur"

now        = datetime.now(timezone.utc)
month      = MONTHS_IS[now.month - 1]
day        = now.day
weekday    = WEEKDAYS_IS[now.weekday()]
day_of_year = now.timetuple().tm_yday
zodiac     = get_zodiac(now.month, now.day)

# Sunrise/sunset for Reykjavik (UTC = Iceland time, no DST)
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

api_key = os.environ["GEMINI_API_KEY"]
url = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.5-flash:generateContent?key={api_key}"
)

prompt = f"""Þú ert íslenskur sagnfræðingur og dagblaðamaður. Dagurinn í dag er {day}. {month}. Stjörnumerki dagsins er {zodiac}.

Svaraðu EINGÖNGU með JSON á þessu nákvæma formi:
{{
  "nafnadagur": "Nafn þess sem á nafnadag á Íslandi í dag (eitt nafn)",
  "atburdir": [
    {{"ar": "ártal", "texti": "stuttur lýsing á heimsatburði þennan dag"}},
    {{"ar": "ártal", "texti": "lýsing"}},
    {{"ar": "ártal", "texti": "lýsing"}},
    {{"ar": "ártal", "texti": "lýsing"}},
    {{"ar": "ártal", "texti": "lýsing"}}
  ],
  "atburdir_island": [
    {{"ar": "ártal", "texti": "atburður sem gerðist á Íslandi þennan dag"}},
    {{"ar": "ártal", "texti": "atburður á Íslandi"}},
    {{"ar": "ártal", "texti": "atburður á Íslandi"}}
  ],
  "afmaeli": [
    {{"nafn": "fullt nafn", "starfsgrein": "leikari / tónlistarmaður / o.fl.", "ar": "fæðingarár"}},
    {{"nafn": "fullt nafn", "starfsgrein": "starfsgrein", "ar": "fæðingarár"}},
    {{"nafn": "fullt nafn", "starfsgrein": "starfsgrein", "ar": "fæðingarár"}}
  ],
  "tonlistUSA": "Nafn lags – Flytjandi (ár)",
  "tonlistUK": "Nafn lags – Flytjandi (ár)",
  "bio": "Nafn kvikmyndar (ár)",
  "ord_dagsins": {{"ord": "sjaldgæft íslenskt orð", "skyring": "skýring á íslensku í einni setningu"}},
  "vissir_thu": "Skemmtileg staðreynd sem flestir vita ekki, óháð ártali, á íslensku.",
  "verdlag": "Árið [X] kostaði [hlutur] [upphæð] kr. á Íslandi.",
  "stjornuspa": "Stutt og skemmtileg retro-stjörnuspá fyrir {zodiac} í dag, tvær setningar á íslensku."
}}"""

body = json.dumps({
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {
        "temperature": 0.8,
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
    "stjornumerki": zodiac,
    **gemini
}

with open("fact.json", "w", encoding="utf-8") as f:
    json.dump(fact, f, ensure_ascii=False, indent=2)

print(f"✓ {day}. {month} ({weekday}), dagur {day_of_year}, {zodiac}")
print(f"  Sólarupprás {sunrise} · Sólarlag {sunset}")
print(f"  Nafnadagur: {gemini.get('nafnadagur', '?')}")
print(f"  {len(fact.get('atburdir', []))} atburðir · {len(fact.get('atburdir_island', []))} á Íslandi · {len(fact.get('afmaeli', []))} afmæli")
