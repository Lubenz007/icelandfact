"""
One-off maintenance script — NOT run by the daily workflow.

timarit.is returns HTTP 403 to GitHub Actions' shared runner IPs on its
/issue and /page endpoints (likely deliberate anti-scraping protection on
their digitized archive), so the daily generate_fact.py can't call it live.
Instead, run this script manually from a machine timarit.is doesn't block
to (re)build .github/scripts/mbl_prices.json — a small table of real,
verified {year: price} entries for Morgunblaðið's printed cover price,
scraped once. generate_fact.py just picks a random entry from that file at
runtime, so the daily job never needs to reach timarit.is itself.

Usage: python3 .github/scripts/collect_mbl_prices.py [start_year] [end_year] [step]
Merges newly-found years into the existing JSON file (doesn't overwrite it).
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA_HEADERS = {"User-Agent": "SaganIDag/1.0 (https://saganidag.is)"}
MBL_PUBLICATION_ID = 58
OUT_PATH = Path(__file__).parent / "mbl_prices.json"

PRICE_PATTERNS = [
    re.compile(r"(\d[\d.,]*)\s*kr\.?\s*eintak\w{0,3}", re.IGNORECASE),
    re.compile(r"(\d[\d.,]*)\s*kr\.?\s*í\s*lausas[öo]lu", re.IGNORECASE),
    re.compile(r"lausas[öo]lu\w{0,4}\D{0,20}?(\d[\d.,]*)\s*kr", re.IGNORECASE),
    re.compile(r"[Vv]erð\s+í\s+lausas[öo]lu\D{0,20}?(\d[\d.,]*)\s*kr", re.IGNORECASE),
]


def fetch_url(url, timeout=20, retries=1):
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


def fetch_json(url, **kw):
    return json.loads(fetch_url(url, **kw))


def parse_is_number(s):
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def find_newspaper_price(issue_id, max_pages=90):
    try:
        first_html = fetch_url(f"https://timarit.is/issue/{issue_id}").decode("utf-8", "ignore")
    except Exception as e:
        print(f"  issue villa ({issue_id}): {e}")
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


def collect(start_year, end_year, step, month, day):
    existing = {}
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))

    for year in range(start_year, end_year + 1, step):
        if str(year) in existing:
            continue
        try:
            cal = fetch_json(
                f"https://timarit.is/view/yearMonthChange?year={year}&month={month}&pubId={MBL_PUBLICATION_ID}"
            )
        except Exception as e:
            print(year, "CAL ERROR", e)
            continue
        issues = cal.get("calendarIssues") or []
        same_month = [it for it in issues if it["value"].split(".")[1] == f"{month:02d}"]
        pool = same_month or issues
        if not pool:
            print(year, "no issues")
            continue
        target = min(pool, key=lambda it: abs(int(it["value"].split(".")[0]) - day))
        price = find_newspaper_price(target["key"])
        print(year, "->", target["value"], "price:", price)
        if price:
            existing[str(year)] = price
            OUT_PATH.write_text(
                json.dumps(dict(sorted(existing.items(), key=lambda kv: int(kv[0]))), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    print(f"\n{len(existing)} ár í {OUT_PATH.name}")


if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1940
    end = int(sys.argv[2]) if len(sys.argv) > 2 else now.year - 10
    step = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    collect(start, end, step, now.month, now.day)
