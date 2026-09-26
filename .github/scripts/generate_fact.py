"""Sagan í Dag – content generator.

Two jobs:
  * Daily (GitHub Actions, 01:00 UTC): builds fact.json for today AND refreshes
    days/MM-DD.json for today, plus data/verdlag.json.
  * Backfill (.github/scripts/backfill_days.py): calls generate_day() for all
    366 calendar days so the "Afmælisdagurinn þinn" lookup is a static fetch.

Everything historical (events, births, Iceland events) is grounded in
Wikipedia data that the model may only select from and rephrase. The model
adds the fun layer: the historian's voice, quiz, word of the day.

LLM provider: Azure OpenAI (AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_KEY, optional
AZURE_OPENAI_DEPLOYMENT) is preferred when configured; Gemini (GEMINI_API_KEY)
is the fallback / free option. Either alone works.
"""
import json
import math
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
UA = "SaganIDag/2.0 (https://saganidag.is)"

MONTHS_IS = [
    "janúar", "febrúar", "mars", "apríl", "maí", "júní",
    "júlí", "ágúst", "september", "október", "nóvember", "desember"
]
WEEKDAYS_IS = [
    "Mánudagur", "Þriðjudagur", "Miðvikudagur",
    "Fimmtudagur", "Föstudagur", "Laugardagur", "Sunnudagur"
]
LANDSHLUTAR = [
    "Höfuðborgarsvæðið", "Reykjanes", "Vesturland", "Vestfirðir",
    "Norðurland", "Austurland", "Suðurland", "Landið allt", "Erlendis"
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


# ───────────────────────── HTTP helpers ─────────────────────────

def http_json(url, data=None, headers=None, timeout=30, retries=3):
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        hdrs.setdefault("Content-Type", "application/json")
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            detail = ""
            try:
                detail = e.read().decode()[:600]
            except Exception:
                pass
            # 4xx other than rate limit will not get better on retry
            if 400 <= e.code < 500 and e.code != 429:
                raise RuntimeError(f"HTTP {e.code} {e.reason}: {detail}") from e
            print(f"  HTTP {e.code} ({attempt + 1}/{retries}) {url[:80]} {detail[:120]}")
        except Exception as e:
            last = e
            print(f"  villa ({attempt + 1}/{retries}) {url[:80]}: {e}")
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Gafst upp á {url[:80]}: {last}")


# ───────────────────────── Sun (Reykjavík) ─────────────────────────

def sun_times(month, day, year=None, lat=64.1355, lon=-21.8954):
    """Sunrise/sunset in Reykjavík (UTC = Iceland time, no DST) using the
    standard NOAA approximation. Good to ~1–2 minutes, which is plenty, and
    needs no network so the 366-day backfill stays deterministic."""
    year = year or datetime.now(timezone.utc).year
    try:
        n = datetime(year, month, day).timetuple().tm_yday
    except ValueError:
        return "", ""
    zenith = math.radians(90.833)
    lat_r = math.radians(lat)

    def calc(rising):
        lng_hour = lon / 15
        t = n + ((6 if rising else 18) - lng_hour) / 24
        M = 0.9856 * t - 3.289
        L = M + 1.916 * math.sin(math.radians(M)) + 0.020 * math.sin(math.radians(2 * M)) + 282.634
        L %= 360
        RA = math.degrees(math.atan(0.91764 * math.tan(math.radians(L)))) % 360
        RA += (math.floor(L / 90) - math.floor(RA / 90)) * 90
        RA /= 15
        sinDec = 0.39782 * math.sin(math.radians(L))
        cosDec = math.cos(math.asin(sinDec))
        cosH = (math.cos(zenith) - sinDec * math.sin(lat_r)) / (cosDec * math.cos(lat_r))
        if cosH > 1 or cosH < -1:
            return ""
        H = 360 - math.degrees(math.acos(cosH)) if rising else math.degrees(math.acos(cosH))
        H /= 15
        T = H + RA - 0.06571 * t - 6.622
        UT = (T - lng_hour) % 24
        return f"{int(UT):02d}:{int((UT % 1) * 60):02d}"

    return calc(True), calc(False)


# ───────────────────────── Wikipedia sources ─────────────────────────

def fetch_wikimedia(kind, month, day):
    """'On this day' feed (English Wikipedia, curated). Returns list of dicts
    with year, text, title (canonical), thumb, image."""
    url = f"https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/{kind}/{month:02d}/{day:02d}"
    try:
        data = http_json(url, timeout=20)
    except Exception as e:
        print(f"Wikimedia {kind} villa: {e}")
        return []
    out = []
    for item in data.get(kind, []):
        if item.get("year") is None or not item.get("text"):
            continue
        page = (item.get("pages") or [{}])[0]
        thumb = (page.get("thumbnail") or {}).get("source", "")
        y = item["year"]
        out.append({
            "year": f"{-y} f.Kr." if isinstance(y, int) and y < 0 else str(y),
            "text": item["text"].replace("(pictured)", "").replace("  ", " ").strip(),
            "title": (page.get("titles") or {}).get("canonical", ""),
            "desc": page.get("description", ""),
            "thumb": thumb.split("?")[0] if thumb else "",
            "thumb_w": (page.get("thumbnail") or {}).get("width", 0),
            "thumb_h": (page.get("thumbnail") or {}).get("height", 0),
            "orig_w": (page.get("originalimage") or {}).get("width", 0),
        })
    return out


def fetch_pageviews(titles, days=30):
    """Sum of last N days of en.wikipedia pageviews per title. Batches of 50.
    Used to rank births by real-world fame instead of trusting the model."""
    views = {}
    titles = [t for t in titles if t]
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        url = (
            "https://en.wikipedia.org/w/api.php?action=query&prop=pageviews"
            f"&pvipdays={days}&format=json&formatversion=2&redirects=1&titles="
            + urllib.parse.quote("|".join(batch), safe="")
        )
        try:
            data = http_json(url, timeout=20)
        except Exception as e:
            print(f"pageviews villa: {e}")
            continue
        for p in data.get("query", {}).get("pages", []):
            total = sum(v or 0 for v in (p.get("pageviews") or {}).values())
            views[p.get("title", "").replace(" ", "_")] = total
    return views


def rank_births(births, top=25):
    views = fetch_pageviews([b["title"] for b in births])
    for b in births:
        b["views"] = views.get(b["title"], 0)
    ranked = sorted(births, key=lambda b: -b["views"])
    return ranked[:top]


def _strip_wikitext(t):
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t)   # [[A|B]] -> B, [[A]] -> A
    t = re.sub(r"'{2,}", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"\{\{[^}]*\}\}", "", t)
    return re.sub(r"\s+", " ", t).strip(" .")


def fetch_is_wikipedia_sections(month, day):
    """Human-edited Icelandic Wikipedia day page ('26. september'): the
    'Atburðir' and 'Fædd' sections, already in Icelandic and full of
    Iceland-specific entries the English feed never has. Reads the wikitext
    so each birth keeps its article title (needed to rank by pageviews)."""
    title = urllib.parse.quote(f"{day}. {MONTHS_IS[month - 1]}")
    url = (
        "https://is.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=content"
        f"&rvslots=main&titles={title}&format=json&formatversion=2&redirects=1"
    )
    try:
        data = http_json(url, timeout=20)
        pages = data.get("query", {}).get("pages", [])
        text = pages[0]["revisions"][0]["slots"]["main"]["content"] if pages else ""
    except Exception as e:
        print(f"is.wikipedia villa: {e}")
        return [], []

    def section(name):
        m = re.search(r"^==\s*" + name + r"\s*==\s*$", text, re.M)
        if not m:
            return []
        body = text[m.end():]
        nxt = re.search(r"^==[^=]", body, re.M)
        body = body[:nxt.start()] if nxt else body
        items = []
        for line in body.split("\n"):
            line = line.strip()
            m2 = re.match(r"^\*\s*\[\[(\d{1,4}(?:\s*f\.\s*Kr\.?)?)\]\]\s*[-–]\s*(.+)$", line)
            if not m2:
                m2 = re.match(r"^\*\s*(\d{1,4}(?:\s*f\.\s*Kr\.?)?)\s*[-–]\s*(.+)$", line)
            if not m2:
                continue
            rest = m2.group(2)
            link = re.search(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", rest)
            items.append({
                "year": m2.group(1).strip(),
                "text": _strip_wikitext(rest),
                "title": link.group(1).replace(" ", "_") if link else "",
            })
        return items

    return section("Atburðir"), section("Fædd")


def fetch_pageviews_is(titles, days=30):
    """Same as fetch_pageviews but on is.wikipedia (numbers are small but
    still rank well: Ólafur Jóhann Sigurðsson 53 vs an obscure botanist 11)."""
    views = {}
    titles = [t for t in titles if t]
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        url = (
            "https://is.wikipedia.org/w/api.php?action=query&prop=pageviews"
            f"&pvipdays={days}&format=json&formatversion=2&redirects=1&titles="
            + urllib.parse.quote("|".join(batch), safe="")
        )
        try:
            data = http_json(url, timeout=20)
        except Exception as e:
            print(f"is pageviews villa: {e}")
            continue
        redir = {r["from"]: r["to"] for r in data.get("query", {}).get("redirects", [])}
        for pg in data.get("query", {}).get("pages", []):
            total = sum(v or 0 for v in (pg.get("pageviews") or {}).values())
            t = pg.get("title", "")
            views[t.replace(" ", "_")] = total
            for src, dst in redir.items():
                if dst == t:
                    views[src.replace(" ", "_")] = total
    return views


def build_icelandic_births(is_births, births_all, top=15):
    """Merge Icelanders from both wikis and rank by fame:
      * is.wikipedia 'Fædd' entries ranked by is.wikipedia pageviews
      * en.wikipedia feed entries whose text says 'Iceland…' (Björk etc.),
        which carry en pageviews from rank_births (already fetched).
    Returns the list the model may choose 'afmaeli_island' from."""
    views = fetch_pageviews_is([b["title"] for b in is_births])
    for b in is_births:
        b["views"] = views.get(b["title"], 0)
        b["src"] = "is"
    ranked = sorted(is_births, key=lambda b: -b["views"])
    en_ice = [{**b, "src": "en"} for b in births_all if re.search(r"\bIceland", b.get("text", ""))]
    def key(b):  # same person on both wikis: same year + same first name
        return (str(b["year"]), b["text"].split()[0].strip(",").lower() if b["text"] else "")
    seen = {key(b) for b in ranked}
    merged = ranked[:top] + [b for b in en_ice if key(b) not in seen]
    return merged


def fmt_list(items, with_views=False):
    lines = []
    for it in items:
        extra = ""
        if with_views and it.get("views") is not None:
            wiki = "is.wikipedia" if it.get("src") == "is" else "en.wikipedia"
            extra = f" [{it['views']:,} flettingar á {wiki}]"
        lines.append(f"- ({it['year']}) {it['text']}{extra}")
    return "\n".join(lines) or "(engin gögn fengust)"


# ───────────────────────── Verðlag (CPI + Morgunblaðið) ─────────────────────────

def fetch_cpi_series():
    """Iceland CPI, 1939=100, from Statistics Iceland's PXWeb API."""
    url = "https://px.hagstofa.is/pxis/api/v1/is/Efnahagur/visitolur/1_vnv/1_vnv/VIS01005.px"
    query = {
        "query": [
            {"code": "Vísitala", "selection": {"filter": "item", "values": ["CPI"]}},
            {"code": "Grunnur", "selection": {"filter": "item", "values": ["B1939"]}},
        ],
        "response": {"format": "json-stat2"},
    }
    try:
        data = http_json(url, data=query, timeout=20)
        year_index = data["dimension"]["Ár"]["category"]["index"]
        values = data["value"]
        return {int(y): values[i] for y, i in year_index.items() if values[i] is not None}
    except Exception as e:
        print(f"Hagstofa CPI villa: {e}")
        return {}


def load_mbl_prices():
    try:
        with open(os.path.join(HERE, "mbl_prices.json"), encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except Exception as e:
        print(f"mbl_prices.json villa: {e}")
        return {}


def format_is_number(n):
    return f"{round(n):,}".replace(",", ".")


def build_verdlag_text(ar, hlutur, verd, cpi):
    text = f"Árið {ar} kostaði {hlutur} um {format_is_number(verd)} kr. á Íslandi."
    if ar in cpi and cpi.get(ar):
        latest = max(cpi)
        factor = cpi[latest] / cpi[ar]
        mult = round(factor, 1) if factor < 10 else round(factor)
        text += (
            f" Almennt verðlag á Íslandi hefur hækkað um u.þ.b. {mult}-falt síðan þá,"
            f" samkvæmt vísitölu neysluverðs."
        )
    return text


def grounded_verdlag(cpi, prices):
    if not prices or not cpi:
        return ""
    year, verd = random.choice(list(prices.items()))
    return build_verdlag_text(year, "eintak af Morgunblaðinu", verd, cpi)


# ───────────────────────── LLM providers ─────────────────────────

def _extract_json(raw):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Ekkert JSON í svari: {raw[:200]}")
    return json.loads(raw[start:end + 1])


def call_azure(prompt):
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    key = os.environ["AZURE_OPENAI_KEY"]
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5.6")
    # Azure OpenAI "v1" surface (…/openai/v1) is OpenAI-compatible:
    # POST /chat/completions with model = deployment name.
    if not endpoint.endswith("/openai/v1"):
        endpoint = endpoint + "/openai/v1"
    url = f"{endpoint}/chat/completions"
    body = {
        "model": deployment,
        "messages": [
            {"role": "system", "content": "Þú svarar EINGÖNGU með gildu JSON, engum öðrum texta."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": 6000,
        "reasoning_effort": "low",
    }
    headers = {"api-key": key, "Authorization": f"Bearer {key}"}
    try:
        data = http_json(url, data=body, headers=headers, timeout=180, retries=2)
    except RuntimeError as e:
        # Older/other deployments reject reasoning_effort or need temperature-free calls.
        if "reasoning_effort" in str(e) or "Unsupported parameter" in str(e):
            body.pop("reasoning_effort", None)
            data = http_json(url, data=body, headers=headers, timeout=180, retries=2)
        else:
            raise
    content = data["choices"][0]["message"]["content"]
    return _extract_json(content)


def call_gemini(prompt):
    key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 6000,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    data = http_json(url, data=body, timeout=180, retries=2)
    return _extract_json(data["candidates"][0]["content"]["parts"][0]["text"])


def call_llm(prompt):
    have_azure = os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_KEY")
    have_gemini = os.environ.get("GEMINI_API_KEY")
    errors = []
    if have_azure:
        try:
            return call_azure(prompt), "Azure OpenAI"
        except Exception as e:
            print(f"Azure villa: {e}")
            errors.append(f"Azure: {e}")
    if have_gemini:
        try:
            return call_gemini(prompt), "Gemini"
        except Exception as e:
            print(f"Gemini villa: {e}")
            errors.append(f"Gemini: {e}")
    if not (have_azure or have_gemini):
        raise SystemExit("Vantar AZURE_OPENAI_ENDPOINT+AZURE_OPENAI_KEY eða GEMINI_API_KEY")
    raise RuntimeError("Allir LLM-veitendur brugðust: " + " | ".join(errors))


# ───────────────────────── Prompt ─────────────────────────

def build_prompt(month, day, zodiac, wiki_events, births_ranked, is_events, is_births):
    m_name = MONTHS_IS[month - 1]
    return f"""Þú ert „Sagnfræðingurinn“ – skemmtilegur, hlýr og orðheppinn íslenskur sagnfræðingur sem skrifar daglegan dálk fyrir saganidag.is. Þú ert fróður en aldrei þurr: þú kryddar með smá húmor, óvæntum tengingum og hlýju, en ferð ALDREI rangt með staðreyndir. Dagurinn er {day}. {m_name}. Stjörnumerki dagsins er {zodiac}.

═══ STAÐFEST GÖGN (af Wikipedia) ═══

A) HEIMSATBURÐIR ÞENNAN DAG – enska Wikipedia (veldu 5 áhugaverðustu og fjölbreyttustu, mismunandi aldir, endursegðu á lipurri íslensku, 1–2 setningar hver):
{fmt_list(wiki_events)}

B) FÓLK FÆTT ÞENNAN DAG – enska Wikipedia, raðað eftir hversu margir lesa um viðkomandi (flettingar síðustu 30 daga = mælikvarði á frægð). Veldu 4–5 sem ÍSLENDINGAR kannast helst við, blandaðu saman núlifandi stjörnum og sögulegum persónum:
{fmt_list(births_ranked, with_views=True)}

C) ATBURÐIR ÚR ÍSLENSKU WIKIPEDIU ÞENNAN DAG (þegar á íslensku). Fyrir "atburdir_island" veldu EINGÖNGU þá sem gerðust á Íslandi eða tengjast Íslandi/Íslendingum beint, allt að 4:
{fmt_list(is_events)}

D) ÍSLENDINGAR FÆDDIR ÞENNAN DAG – úr íslensku og ensku Wikipediu, raðað eftir flettingum (= frægð). Veldu allt að 3 ÞEKKTUSTU Íslendingana (eða fólk með sterk Íslandstengsl) fyrir "afmaeli_island" – listamenn, íþróttafólk, stjórnmálafólk, rithöfunda sem þjóðin kannast við; hafðu frægustu efst. Slepptu útlendingum sem slæðast með í listanum. Ef enginn Íslendingur er í listanum skilaðu tómu fylki:
{fmt_list(is_births, with_views=True)}

═══ REGLUR ═══
- atburdir, atburdir_island, afmaeli, afmaeli_island: EINGÖNGU úr listunum að ofan. Aldrei uppspuni. Ártöl nákvæmlega eins og í listunum.
- Ef listi er „(engin gögn fengust)“ eða fátæklegur, skilaðu bara styttra/tómu fylki – EKKI finna upp staðgengla.
- afmaeli: forðastu umdeildar/óviðeigandi persónur (hryðjuverkamenn, glæpamenn) ef aðrir kostir eru í boði. Starfsgrein á íslensku, stutt.
- landshluti fyrir hvern íslenskan atburð: veldu EITT úr {json.dumps(LANDSHLUTAR, ensure_ascii=False)} eftir því hvar atburðurinn gerðist. „Landið allt“ fyrir landsmál (lög, kosningar, þjóðhátíð), „Erlendis“ ef hann gerðist utan Íslands.
- spurningar: 3 krossaspurningar SEM BYGGJA EINGÖNGU á atburðunum/afmælunum sem þú valdir að ofan (svarið þarf að vera í gögnunum). 4 svarmöguleikar hver, einn réttur, rangir kostir trúverðugir. Skemmtilegur tónn.
- nafnadagur, ord_dagsins, vissir_thu: AÐEINS staðreyndir sem þú ert MJÖG viss um. Betra tómt en rangt. Nafnadagur skv. íslenska nafnadagatalinu (eitt nafn).
- tonlistUSA/tonlistUK/bio: skemmtiefni eftir bestu vitund – lag/kvikmynd sem var á toppnum/vinsælt þennan mánaðardag eitthvert ár. Frekar besta ágiskun en tómt.
- kvedja: 2–3 setningar þar sem Sagnfræðingurinn heilsar lesanda og tengir daginn saman á skemmtilegan hátt (má vísa í eitthvað úr atburðunum). Persónulegt, hlýlegt, með glotti.
- stjornuspa: retro-stjörnuspá fyrir {zodiac}, 2 setningar, glettin.
- Allur texti á vandaðri íslensku. Engin enska nema í nöfnum.

Svaraðu EINGÖNGU með JSON á þessu nákvæma formi:
{{
  "kvedja": "…",
  "nafnadagur": "Nafn",
  "atburdir": [
    {{"ar": "ártal", "texti": "endursögn"}}
  ],
  "atburdir_island": [
    {{"ar": "ártal", "texti": "endursögn", "landshluti": "Suðurland"}}
  ],
  "afmaeli": [
    {{"nafn": "Fullt nafn", "starfsgrein": "starfsgrein á íslensku", "ar": "fæðingarár"}}
  ],
  "afmaeli_island": [
    {{"nafn": "Fullt nafn", "starfsgrein": "starfsgrein", "ar": "fæðingarár"}}
  ],
  "spurningar": [
    {{"spurning": "…?", "svor": ["A", "B", "C", "D"], "rett": 0, "skyring": "ein létt setning um rétta svarið"}}
  ],
  "tonlistUSA": "Lag – Flytjandi (ár)",
  "tonlistUK": "Lag – Flytjandi (ár)",
  "bio": "Kvikmynd (ár)",
  "ord_dagsins": {{"ord": "sjaldgæft íslenskt orð", "skyring": "skýring í einni setningu"}},
  "vissir_thu": "Skemmtileg en SÖNN staðreynd.",
  "stjornuspa": "…"
}}"""


# ───────────────────────── Post-processing ─────────────────────────

def pick_image(chosen_events, wiki_events):
    """Attach a real Wikipedia thumbnail: prefer an image belonging to one of
    the events the model actually chose, else the first event with an image."""
    by_year = {}
    for ev in wiki_events:
        if ev.get("thumb"):
            by_year.setdefault(str(ev["year"]), ev)
    for ev in chosen_events:
        src = by_year.get(str(ev.get("ar", "")))
        if src:
            return _image_dict(src, ev.get("texti"))
    for ev in wiki_events:
        if ev.get("thumb"):
            return _image_dict(ev)
    return None


def _image_dict(ev, caption=None):
    # Wikimedia only serves a fixed list of thumbnail widths now
    # (https://w.wiki/GHai); 500px is the sweet spot for a 680px-wide paper.
    # Never ask for a size larger than the original or it returns HTTP 400.
    url = ev["thumb"].replace("thumb.wikimedia.org", "upload.wikimedia.org")
    orig_w = ev.get("orig_w") or 0
    size = 500 if orig_w >= 500 else 330
    url = re.sub(r"/(\d{2,4})px-", f"/{size}px-", url)
    return {
        "url": url,
        "ar": str(ev["year"]),
        "texti": caption or ev["text"],   # Icelandic retelling when the model chose this event
        "heimild": f"https://en.wikipedia.org/wiki/{ev['title']}" if ev.get("title") else "https://en.wikipedia.org",
        "breidd": ev.get("thumb_w", 0),
        "haed": ev.get("thumb_h", 0),
    }


def sanitize(llm, wiki_events, births_ranked, is_events, is_births):
    """Enforce the grounding contract mechanically: drop any chosen item whose
    year does not appear in the source list it was supposed to come from."""
    def years(items):
        return {str(i["year"]).strip() for i in items}

    def keep(items, allowed, key="ar"):
        out = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            if str(it.get(key, "")).strip() in allowed or not allowed:
                out.append(it)
        return out

    llm["atburdir"] = keep(llm.get("atburdir"), years(wiki_events))[:5]
    llm["atburdir_island"] = keep(llm.get("atburdir_island"), years(is_events))[:4]
    for ev in llm["atburdir_island"]:
        if ev.get("landshluti") not in LANDSHLUTAR:
            ev["landshluti"] = "Landið allt"
    llm["afmaeli"] = keep(llm.get("afmaeli"), years(births_ranked))[:5]
    llm["afmaeli_island"] = keep(llm.get("afmaeli_island"), years(is_births))[:3]

    qs = []
    for q in llm.get("spurningar") or []:
        if not isinstance(q, dict):
            continue
        svor = q.get("svor") or []
        rett = q.get("rett")
        if isinstance(svor, list) and len(svor) == 4 and isinstance(rett, int) and 0 <= rett < 4 and q.get("spurning"):
            qs.append({"spurning": q["spurning"], "svor": svor, "rett": rett, "skyring": q.get("skyring", "")})
    llm["spurningar"] = qs[:3]

    for k in ["kvedja", "nafnadagur", "tonlistUSA", "tonlistUK", "bio", "vissir_thu", "stjornuspa"]:
        v = llm.get(k)
        llm[k] = v.strip() if isinstance(v, str) else ""
    od = llm.get("ord_dagsins")
    if not (isinstance(od, dict) and od.get("ord") and od.get("skyring")):
        llm["ord_dagsins"] = None
    return llm


# ───────────────────────── Main entry points ─────────────────────────

def generate_day(month, day, verbose=True):
    """Build the year-independent content for one calendar day."""
    zodiac = get_zodiac(month, day)
    sunrise, sunset = sun_times(month, day)

    wiki_events = fetch_wikimedia("selected", month, day)[:20]
    births_all = fetch_wikimedia("births", month, day)
    births_ranked = rank_births(births_all, top=25)
    is_events, is_births_raw = fetch_is_wikipedia_sections(month, day)
    is_births = build_icelandic_births(is_births_raw, births_all)

    if verbose:
        print(f"  Heimildir: {len(wiki_events)} heimsatburðir, {len(births_all)} fædd (topp {len(births_ranked)}), "
              f"{len(is_events)} ísl. atburðir, {len(is_births_raw)} ísl. fædd (topp {len(is_births)})")

    prompt = build_prompt(month, day, zodiac, wiki_events, births_ranked, is_events, is_births)
    llm, provider = call_llm(prompt)
    llm = sanitize(llm, wiki_events, births_ranked, is_events, is_births)

    result = {
        "mmdd": f"{month:02d}-{day:02d}",
        "dagur": day,
        "manudur": MONTHS_IS[month - 1],
        "manudurNr": month,
        "stjornumerki": zodiac,
        "sunrise": sunrise,
        "sunset": sunset,
        **llm,
        "mynd": pick_image(llm["atburdir"], wiki_events),
        "veitandi": provider,
        "uppfaert": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    return result


def write_json(path, obj):
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_verdlag_data(cpi, prices):
    """Static data the browser uses to compute 'verðlag þegar þú fæddist'."""
    if not cpi:
        return
    write_json(os.path.join(ROOT, "data", "verdlag.json"), {
        "cpi": {str(k): v for k, v in sorted(cpi.items())},
        "mbl": {str(k): v for k, v in sorted(prices.items())},
        "heimild": "Hagstofa Íslands (VNV, 1939=100) og Morgunblaðið á timarit.is",
        "uppfaert": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    })


def main():
    now = datetime.now(timezone.utc)
    month, day = now.month, now.day
    print(f"Sagan í Dag – {day}. {MONTHS_IS[month - 1]} {now.year}")

    day_data = generate_day(month, day)
    write_json(os.path.join(ROOT, "days", f"{day_data['mmdd']}.json"), day_data)

    cpi = fetch_cpi_series()
    prices = load_mbl_prices()
    write_verdlag_data(cpi, prices)
    verdlag = grounded_verdlag(cpi, prices)

    # Live sunrise for today from Open-Meteo when available (exact), else formula.
    sunrise, sunset = day_data["sunrise"], day_data["sunset"]
    try:
        sun = http_json(
            "https://api.open-meteo.com/v1/forecast?latitude=64.1355&longitude=-21.8954"
            "&daily=sunrise,sunset&timezone=UTC&forecast_days=1", timeout=15, retries=1
        )["daily"]
        sunrise = sun["sunrise"][0].split("T")[1]
        sunset = sun["sunset"][0].split("T")[1]
    except Exception as e:
        print(f"Open-Meteo villa (nota formúlu): {e}")

    fact = {
        "date": now.strftime("%Y-%m-%d"),
        "dagur": day,
        "manudur": MONTHS_IS[month - 1],
        "vikudagur": WEEKDAYS_IS[now.weekday()],
        "dagurArsins": now.timetuple().tm_yday,
        "sunrise": sunrise,
        "sunset": sunset,
        **{k: v for k, v in day_data.items() if k not in ("dagur", "manudur", "sunrise", "sunset")},
        "verdlag": verdlag,
    }
    write_json(os.path.join(ROOT, "fact.json"), fact)

    print(f"✓ {day}. {MONTHS_IS[month - 1]} ({fact['vikudagur']}), dagur {fact['dagurArsins']}, {fact['stjornumerki']} · {day_data['veitandi']}")
    print(f"  Sólarupprás {sunrise} · Sólarlag {sunset} · Nafnadagur: {fact.get('nafnadagur') or '?'}")
    print(f"  {len(fact['atburdir'])} atburðir · {len(fact['atburdir_island'])} á Íslandi · "
          f"{len(fact['afmaeli'])}+{len(fact['afmaeli_island'])} afmæli · {len(fact['spurningar'])} spurningar · "
          f"mynd: {'já' if fact.get('mynd') else 'nei'}")
    print(f"  Verðlag: {'grundað' if verdlag else 'fannst ekki, tómt'}")


if __name__ == "__main__":
    main()
