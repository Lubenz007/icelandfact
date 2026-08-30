import json
import random
import re
import time
import urllib.request
import urllib.error
import urllib.parse
import os
from datetime import datetime, timezone

UA_HEADERS = {"User-Agent": "SaganIDag/1.0 (https://saganidag.is)"}


def fetch_url(url, timeout=20, retries=1):
    """GET with retries/backoff — timarit.is in particular has been observed
    to silently time out (not error) on some requests from GitHub Actions'
    shared runner IPs even though it responds instantly from other networks,
    so a transient stall shouldn't sink the whole attempt."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise last_err


def fetch_json(url, timeout=20, retries=1):
    return json.loads(fetch_url(url, timeout=timeout, retries=retries))

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

# Sunrise/sunset for Reykjavik via Open-Meteo (free, no auth)
sun_url = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=64.1355&longitude=-21.8954"
    "&daily=sunrise,sunset&timezone=UTC&forecast_days=1"
)
try:
    with urllib.request.urlopen(sun_url) as r:
        sun = json.loads(r.read())["daily"]
    sunrise = sun["sunrise"][0].split("T")[1]
    sunset  = sun["sunset"][0].split("T")[1]
except Exception as e:
    print(f"Sunrise API villa: {e}")
    sunrise = sunset = ""


def fetch_wikimedia(kind):
    """Fetch curated 'on this day' data from Wikipedia so Gemini has real
    facts to translate instead of inventing events/years from memory."""
    url = (
        "https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/"
        f"{kind}/{now.month:02d}/{now.day:02d}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "SaganIDag/1.0 (https://saganidag.is)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        items = data.get(kind, [])
        return [
            {"year": item.get("year"), "text": item.get("text", "").replace("(pictured)", "").strip()}
            for item in items
            if item.get("year") is not None and item.get("text")
        ]
    except Exception as e:
        print(f"Wikimedia {kind} API villa: {e}")
        return []


def sample_spread(items, n):
    """Evenly sample up to n items across the full list so the range of
    years/eras stays varied instead of skewing toward whatever sorts first."""
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


wiki_events = fetch_wikimedia("selected")[:20]
wiki_births = sample_spread(fetch_wikimedia("births"), 30)


def fetch_is_wikipedia_events():
    """Fetch the human-edited 'Atburðir' (events) section of is.wikipedia.org's
    day article (e.g. '30. ágúst') — already in Icelandic and includes Iceland-
    specific entries, unlike the English Wikimedia feed."""
    title = urllib.parse.quote(f"{day}. {month}")
    url = (
        "https://is.wikipedia.org/w/api.php?action=query&prop=extracts"
        f"&titles={title}&format=json&formatversion=2&explaintext=1&redirects=1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "SaganIDag/1.0 (https://saganidag.is)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        pages = data.get("query", {}).get("pages", [])
        extract = pages[0].get("extract", "") if pages else ""
    except Exception as e:
        print(f"is.wikipedia.org API villa: {e}")
        return []

    marker = "\n== Atburðir ==\n"
    start = extract.find(marker)
    if start == -1:
        return []
    start += len(marker)
    end = extract.find("\n== ", start)
    section = extract[start:end if end != -1 else len(extract)]

    events = []
    for line in section.split("\n"):
        line = line.strip()
        m = re.match(r"^(\d{1,4}(?:\s*f\.Kr)?)\s*[-–]\s*(.+)$", line)
        if m:
            events.append({"year": m.group(1), "text": m.group(2)})
    return events


is_events = fetch_is_wikipedia_events()


def fmt_list(items):
    return "\n".join(f"- ({it['year']}) {it['text']}" for it in items) or "(engin gögn fengust)"

wiki_events_text = fmt_list(wiki_events)
wiki_births_text = fmt_list(wiki_births)
is_events_text = fmt_list(is_events)


def fetch_cpi_series():
    """Fetch Iceland's full consumer price index history (1939=100, chained)
    from Statistics Iceland's public PXWeb API, so the 'verdlag' inflation
    comparison is computed from real government data, not guessed by Gemini."""
    url = (
        "https://px.hagstofa.is/pxis/api/v1/is/Efnahagur/visitolur/"
        "1_vnv/1_vnv/VIS01005.px"
    )
    query = {
        "query": [
            {"code": "Vísitala", "selection": {"filter": "item", "values": ["CPI"]}},
            {"code": "Grunnur", "selection": {"filter": "item", "values": ["B1939"]}},
        ],
        "response": {"format": "json-stat2"},
    }
    req = urllib.request.Request(
        url, data=json.dumps(query).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "SaganIDag/1.0 (https://saganidag.is)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        year_index = data["dimension"]["Ár"]["category"]["index"]
        values = data["value"]
        return {int(y): values[i] for y, i in year_index.items() if values[i] is not None}
    except Exception as e:
        print(f"Hagstofa CPI API villa: {e}")
        return {}


cpi_series = fetch_cpi_series()


def format_is_number(n):
    return f"{round(n):,}".replace(",", ".")


def build_verdlag_text(ar, hlutur, verd):
    """Compose the final 'verdlag' sentence: ar/hlutur/verd must already be a
    real, verified fact (see fetch_grounded_verdlag) — the inflation math
    comes from cpi_series so that part is never hallucinated either."""
    text = f"Árið {ar} kostaði {hlutur} um {format_is_number(verd)} kr. á Íslandi."
    if ar in cpi_series and cpi_series.get(ar):
        latest_year = max(cpi_series)
        factor = cpi_series[latest_year] / cpi_series[ar]
        multiplier = round(factor, 1) if factor < 10 else round(factor)
        # Deliberately phrased as general price-level change, not "this item
        # costs X today" — individual goods (fuel, alcohol, tech) can diverge
        # sharply from the overall CPI basket, so projecting a specific
        # today-price from one old price would be misleading, not grounded.
        text += (
            f" Almennt verðlag á Íslandi hefur hækkað um u.þ.b. {multiplier}-falt síðan þá,"
            f" samkvæmt vísitölu neysluverðs."
        )
    return text


MBL_PUBLICATION_ID = 58  # Morgunblaðið on timarit.is

PRICE_PATTERNS = [
    # OCR of old scans regularly confuses Icelandic letters (ð/ö, etc.), so
    # "eintakið" comes back as "eintakiö" and similar — match loosely on the
    # "eintak…" / "lausasöl…" stem instead of the exact word, in both
    # number-then-word and word-then-number order.
    re.compile(r"(\d[\d.,]*)\s*kr\.?\s*eintak\w{0,3}", re.IGNORECASE),
    re.compile(r"(\d[\d.,]*)\s*kr\.?\s*í\s*lausas[öo]lu", re.IGNORECASE),
    re.compile(r"lausas[öo]lu\w{0,4}\D{0,20}?(\d[\d.,]*)\s*kr", re.IGNORECASE),
    re.compile(r"[Vv]erð\s+í\s+lausas[öo]lu\D{0,20}?(\d[\d.,]*)\s*kr", re.IGNORECASE),
]


def parse_is_number(s):
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def find_newspaper_price(issue_id, max_pages=50):
    """Scan an issue's pages (OCR text is embedded directly in each page's
    HTML) for its own printed cover price — the imprint box isn't on a fixed
    page number, so this checks pages in order until it finds one."""
    try:
        first_html = fetch_url(f"https://timarit.is/issue/{issue_id}").decode("utf-8", "ignore")
    except Exception as e:
        print(f"timarit.is issue villa ({issue_id}): {e}")
        return None

    seen, page_ids = set(), []
    for pid in re.findall(r'href="/page/(\d+)"', first_html):
        if pid not in seen:
            seen.add(pid)
            page_ids.append(pid)

    for pid in page_ids[:max_pages]:
        try:
            html = fetch_url(f"https://timarit.is/page/{pid}", retries=1).decode("utf-8", "ignore")
        except Exception:
            continue
        for pattern in PRICE_PATTERNS:
            m = pattern.search(html)
            if m:
                price = parse_is_number(m.group(1))
                if price and 0 < price < 100000:
                    return price
    return None


def fetch_grounded_verdlag():
    """Ground 'verdlag' in a real archived Morgunblaðið cover price from
    timarit.is instead of a Gemini guess — picks a handful of candidate years
    (bounded to years the CPI series covers) and tries each until one yields
    both an archived issue near today's date and a readable price on it."""
    if not cpi_series:
        return ""
    min_year, max_year = min(cpi_series), min(max(cpi_series), now.year - 10)
    if min_year >= max_year:
        return ""
    candidate_years = random.sample(range(min_year, max_year + 1), min(6, max_year - min_year + 1))

    for year in candidate_years:
        try:
            cal = fetch_json(
                f"https://timarit.is/view/yearMonthChange?year={year}&month={now.month}&pubId={MBL_PUBLICATION_ID}"
            )
        except Exception as e:
            print(f"timarit.is dagatal villa ({year}): {e}")
            continue
        issues = cal.get("calendarIssues") or []
        if not issues:
            continue
        # the calendar response spans a window of surrounding months too, so
        # prefer issues actually in today's month before falling back
        same_month = [it for it in issues if it["value"].split(".")[1] == f"{now.month:02d}"]
        pool = same_month or issues
        target = min(pool, key=lambda it: abs(int(it["value"].split(".")[0]) - day))
        price = find_newspaper_price(target["key"])
        if price:
            print(f"  Verðlag grundað: Morgunblaðið {year} = {price} kr.")
            return build_verdlag_text(year, "eintak af Morgunblaðinu", price)
    print("  Verðlag: engin nothæf verðupplýsing fannst í tilraununum")
    return ""


api_key = os.environ["GEMINI_API_KEY"]
url = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.5-flash:generateContent?key={api_key}"
)

prompt = f"""Þú ert íslenskur sagnfræðingur og dagblaðamaður. Dagurinn í dag er {day}. {month}. Stjörnumerki dagsins er {zodiac}.

Hér fyrir neðan eru STAÐFESTIR atburðir og staðfest fólk fætt þennan dag, sótt beint af Wikipedia. Fyrir "atburdir" og "afmaeli" MÁTT ÞÚ EINGÖNGU velja úr þessum listum — EKKI finna upp eða bæta við neinu sem er ekki í listunum, og EKKI breyta ártölunum sem gefin eru upp.

STAÐFESTIR HEIMSATBURÐIR (veldu 5 áhugaverðustu, endursegðu stutt á íslensku):
{wiki_events_text}

STAÐFEST FÓLK FÆTT ÞENNAN DAG (veldu allt að 3 þekktustu á heimsvísu, þýddu starfsgrein á íslensku):
{wiki_births_text}

STAÐFESTIR ATBURÐIR ÚR ATBURÐADAGATALI ÍSLENSKU WIKIPEDIU, ÞENNAN DAG (þegar á íslensku — fyrir "atburdir_island" máttu EINGÖNGU velja þá atburði hér að neðan sem gerðust á Íslandi eða tengjast Íslandi/Íslendingum beint, allt að 3 stykki; ef enginn atburður hér tengist Íslandi skaltu skila tómu fylki fyrir atburdir_island):
{is_events_text}

Ef listi er merktur "(engin gögn fengust)" eða er of fátæklegur til að finna nóg af áhugaverðu efni, skildu viðkomandi fylki bara eftir styttra eða tómt — EKKI finna upp staðgengla.

Fyrir nafnadagur, orð dagsins og vissir þú skaltu AÐEINS nota staðfestar og vel þekktar staðreyndir sem þú ert mjög viss um. Ef þú ert ekki fullviss um atburð eða ártal — slepptu honum eða skildu fylkið/reitinn eftir tómt. Betra er að hafa færri en ranga staðreynd.

Tónlist, kvikmynd og stjörnuspá eru léttmeti/skemmtiefni fremur en sagnfræði — þar mátt þú gefa þitt besta svar eftir minni án þess að þurfa fulla vissu.

Svaraðu EINGÖNGU með JSON á þessu nákvæma formi:
{{
  "nafnadagur": "Nafn þess sem á nafnadag á Íslandi í dag samkvæmt íslenska nafnadagatalinu (eitt nafn)",
  "atburdir": [
    {{"ar": "ártal (nákvæmlega eins og í listanum að ofan)", "texti": "íslensk endursögn atburðar úr listanum að ofan"}},
    {{"ar": "ártal", "texti": "endursögn"}},
    {{"ar": "ártal", "texti": "endursögn"}},
    {{"ar": "ártal", "texti": "endursögn"}},
    {{"ar": "ártal", "texti": "endursögn"}}
  ],
  "atburdir_island": [
    {{"ar": "ártal (nákvæmlega eins og í íslenska atburðalistanum að ofan)", "texti": "endursögn atburðar úr þeim lista sem tengist Íslandi"}}
  ],
  "afmaeli": [
    {{"nafn": "fullt nafn úr listanum að ofan", "starfsgrein": "starfsgrein á íslensku", "ar": "fæðingarár nákvæmlega eins og í listanum"}},
    {{"nafn": "...", "starfsgrein": "...", "ar": "..."}},
    {{"nafn": "...", "starfsgrein": "...", "ar": "..."}}
  ],
  "tonlistUSA": "Nafn lags – Flytjandi (ár) sem var vinsælt/á toppi vinsældalista í Bandaríkjunum þennan mánaðardag eitthvert ár í fortíðinni, eftir bestu vitund",
  "tonlistUK": "Nafn lags – Flytjandi (ár) sem var vinsælt/á toppi vinsældalista í Bretlandi þennan mánaðardag eitthvert ár í fortíðinni, eftir bestu vitund",
  "bio": "Nafn þekktrar kvikmyndar (ár) sem var frumsýnd þennan mánaðardag eitthvert ár í fortíðinni, eftir bestu vitund",
  "ord_dagsins": {{"ord": "sjaldgæft íslenskt orð", "skyring": "skýring á íslensku í einni setningu"}},
  "vissir_thu": "Skemmtileg en SÖNN staðreynd sem flestir vita ekki, á íslensku.",
  "stjornuspa": "Stutt og skemmtileg retro-stjörnuspá fyrir {zodiac} í dag, tvær setningar á íslensku."
}}

Leiðbeiningar:
- atburdir, afmaeli og atburdir_island: EINGÖNGU úr listunum að ofan, aldrei uppspuni, ártöl mega ekki breytast
- afmaeli: veldu skemmtilegar/jákvæðar eða áhugaverðar persónur sem flestir kannast við — forðastu umdeildar eða óviðeigandi persónur (t.d. hryðjuverkamenn, glæpamenn) ef aðrir kostir eru í boði
- atburdir_island: má vera tómt fylki ef enginn atburður í listanum tengist Íslandi beint
- tonlistUSA/tonlistUK/bio: þetta er skemmtiefni, ekki söguleg heimild — veldu líklegasta/besta svar sem þú manst eftir í stað þess að skilja eftir tómt; skildu aðeins eftir tómt ef ekkert kemur til greina yfirhöfuð"""

body = json.dumps({
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {
        "temperature": 0.3,
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

verdlag = fetch_grounded_verdlag()

fact = {
    "date":        now.strftime("%Y-%m-%d"),
    "dagur":       day,
    "manudur":     month,
    "vikudagur":   weekday,
    "dagurArsins": day_of_year,
    "sunrise":     sunrise,
    "sunset":      sunset,
    "stjornumerki": zodiac,
    **gemini,
    "verdlag": verdlag,
}

with open("fact.json", "w", encoding="utf-8") as f:
    json.dump(fact, f, ensure_ascii=False, indent=2)

print(f"✓ {day}. {month} ({weekday}), dagur {day_of_year}, {zodiac}")
print(f"  Sólarupprás {sunrise} · Sólarlag {sunset}")
print(f"  Nafnadagur: {gemini.get('nafnadagur', '?')}")
print(f"  {len(fact.get('atburdir', []))} atburðir · {len(fact.get('atburdir_island', []))} á Íslandi · {len(fact.get('afmaeli', []))} afmæli")
print(f"  Verðlag: {'grundað' if verdlag else 'fannst ekki, tómt'}")
