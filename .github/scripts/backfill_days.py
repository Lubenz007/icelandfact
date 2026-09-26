"""Pre-generate days/MM-DD.json for every calendar day (366 incl. 29 Feb) so the
"Afmælisdagurinn þinn" lookup on the site is a plain static fetch: no key in
the browser, no rate limits, every day reviewable in git.

Usage:
  python backfill_days.py                # only missing days
  python backfill_days.py --force        # regenerate everything
  python backfill_days.py --only 03-14 12-24
  python backfill_days.py --max 50       # stop after N generated (resume later)

Env: same LLM keys as generate_fact.py. Set BACKFILL_COMMIT=1 to commit+push
every 20 days so a long GitHub Actions run cannot lose work if it dies.
"""
import os
import subprocess
import sys
import time
from calendar import monthrange

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_fact as gf  # noqa: E402

DAYS_DIR = os.path.join(gf.ROOT, "days")


def all_days():
    for m in range(1, 13):
        for d in range(1, monthrange(2024, m)[1] + 1):  # 2024 = leap year → 29 Feb
            yield m, d


def git_commit(msg):
    try:
        subprocess.run(["git", "add", "days", "data"], cwd=gf.ROOT, check=True)
        diff = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=gf.ROOT)
        if diff.returncode == 0:
            return
        subprocess.run(["git", "commit", "-m", msg], cwd=gf.ROOT, check=True)
        subprocess.run(["git", "pull", "--rebase", "-q"], cwd=gf.ROOT, check=False)
        subprocess.run(["git", "push"], cwd=gf.ROOT, check=True)
        print(f"  ✓ commit: {msg}")
    except Exception as e:
        print(f"  git villa: {e}")


def main(argv):
    force = "--force" in argv
    only = set()
    if "--only" in argv:
        i = argv.index("--only") + 1
        while i < len(argv) and not argv[i].startswith("--"):
            only.add(argv[i])
            i += 1
    max_n = None
    if "--max" in argv:
        max_n = int(argv[argv.index("--max") + 1])
    do_commit = os.environ.get("BACKFILL_COMMIT") == "1"

    todo = []
    for m, d in all_days():
        mmdd = f"{m:02d}-{d:02d}"
        if only and mmdd not in only:
            continue
        path = os.path.join(DAYS_DIR, f"{mmdd}.json")
        if os.path.exists(path) and not force:
            continue
        todo.append((m, d, path))

    print(f"Á að búa til {len(todo)} daga" + (f" (mest {max_n})" if max_n else ""))
    done = failed = 0
    start = time.time()
    for m, d, path in todo:
        if max_n is not None and done >= max_n:
            break
        mmdd = f"{m:02d}-{d:02d}"
        print(f"\n[{done + 1}/{len(todo)}] {d}. {gf.MONTHS_IS[m - 1]} ({mmdd})")
        for attempt in range(3):
            try:
                data = gf.generate_day(m, d)
                gf.write_json(path, data)
                print(f"  ✓ {len(data['atburdir'])} atb · {len(data['atburdir_island'])} ísl · "
                      f"{len(data['afmaeli'])}+{len(data['afmaeli_island'])} afm · "
                      f"{len(data['spurningar'])} sp · {data['veitandi']}")
                done += 1
                break
            except Exception as e:
                print(f"  villa ({attempt + 1}/3): {e}")
                time.sleep(5 * (attempt + 1))
        else:
            failed += 1
        if do_commit and done and done % 20 == 0:
            git_commit(f"Bakfylla daga ({done} af {len(todo)})")

    # Always refresh the shared verðlag data too.
    cpi = gf.fetch_cpi_series()
    gf.write_verdlag_data(cpi, gf.load_mbl_prices())
    if do_commit:
        git_commit(f"Bakfylla daga – lokið ({done} búnir til, {failed} mistókust)")

    mins = (time.time() - start) / 60
    print(f"\nLokið: {done} búnir til, {failed} mistókust, {mins:.1f} mín.")
    return 1 if failed and not done else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
