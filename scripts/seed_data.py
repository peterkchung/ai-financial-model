# About: Per-company data bootstrap. Downloads everything one company's
# pipeline needs from public sources (SEC EDGAR, FRED), and slices the SEC
# FSDS bulk into a per-company subset. Idempotent — re-running skips files
# that already exist.
#
# Run after a fresh clone:
#   make seed-data COMPANY=amzn
#   make process-company COMPANY=amzn

from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import time
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

# SEC requires a User-Agent identifying the requester:
# "<Company / Project> <admin email>". Override via env var SEC_UA.
DEFAULT_UA = "ai-financial-model-research aifm-bootstrap@example.com"
UA = os.environ.get("SEC_UA", DEFAULT_UA)
REPO = Path(__file__).resolve().parents[1]


# Per-company configuration the script needs to seed. Add more companies here
# (CIK + ticker prefix used in 8-K exhibit naming) to support seeding them.
COMPANY_REGISTRY: dict[str, dict] = {
    "amzn": {"cik": "1018724", "ticker_prefix": "amzn"},
}


def fetch(url: str, dest: Path, ua: str = UA, *, retries: int = 3, backoff: float = 2.0) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  ✓ {dest.relative_to(REPO)}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ⤓ {dest.relative_to(REPO)}")
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
            return
        except urllib.error.HTTPError as e:
            # Partial body may have hit disk before status was raised (rare); clean up either way.
            dest.unlink(missing_ok=True)
            raise SystemExit(f"  ✗ {url} → HTTP {e.code}: {e.reason}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            # Read/connect timeouts and other transient socket errors. Drop any partial file
            # so the size>0 idempotency check doesn't later treat it as complete.
            dest.unlink(missing_ok=True)
            if attempt == retries:
                raise SystemExit(f"  ✗ {url} → {type(e).__name__}: {e} (after {retries} attempts)") from e
            wait = backoff ** attempt
            print(f"  … {type(e).__name__} on attempt {attempt}/{retries}; retrying in {wait:.0f}s")
            time.sleep(wait)


def fetch_sec_fsds() -> Path:
    """Bulk SEC FSDS file — shared download cache (per-company slice happens after).

    Returns the unpacked directory."""
    print("\n[1/4] SEC Financial Statement Data Sets bulk (~80 MB zip → ~640 MB unpacked)")
    cache = REPO / "data" / "sec_fsds_cache"
    zip_path = cache / "2026q1.zip"
    fetch(
        "https://www.sec.gov/files/dera/data/financial-statement-data-sets/2026q1.zip",
        zip_path,
    )
    unpacked = cache / "2026q1"
    if not (unpacked / "sub.txt").exists():
        print(f"  ⊞ unzipping {zip_path.name}")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(unpacked)
    return unpacked


def slice_fsds_for_company(bulk_dir: Path, *, cik: str, dest: Path) -> None:
    """Slice the bulk sub.txt + num.txt into per-company subsets.

    sub.txt: header + every row whose CIK matches (column 2, 1-indexed).
             Form filter is intentionally absent — we keep all forms (10-K,
             10-Q, 8-K, etc.) for the company so different ingester `form`
             selections can target the same slice.
    num.txt: header + every row whose adsh appears in the sliced sub.txt
             (i.e., every fact for any of this company's filings).
    """
    dest.mkdir(parents=True, exist_ok=True)
    sub_in = bulk_dir / "sub.txt"
    num_in = bulk_dir / "num.txt"
    sub_out = dest / "sub.txt"
    num_out = dest / "num.txt"

    if sub_out.exists() and num_out.exists() and sub_out.stat().st_size > 0 and num_out.stat().st_size > 0:
        print(f"  ✓ {sub_out.relative_to(REPO)}")
        print(f"  ✓ {num_out.relative_to(REPO)}")
        return

    print(f"  ⊟ slicing CIK {cik} from {bulk_dir.relative_to(REPO)}")
    company_adshes: set[str] = set()
    with sub_in.open(encoding="latin-1") as src, sub_out.open("w", encoding="latin-1") as out:
        header = src.readline()
        out.write(header)
        for line in src:
            cols = line.rstrip("\n").split("\t")
            if len(cols) > 1 and cols[1] == cik:
                out.write(line)
                company_adshes.add(cols[0])

    with num_in.open(encoding="latin-1") as src, num_out.open("w", encoding="latin-1") as out:
        header = src.readline()
        out.write(header)
        for line in src:
            adsh = line.split("\t", 1)[0]
            if adsh in company_adshes:
                out.write(line)

    print(f"  ⤓ {sub_out.relative_to(REPO)} ({sum(1 for _ in sub_out.open()):,} rows)")
    print(f"  ⤓ {num_out.relative_to(REPO)} ({sum(1 for _ in num_out.open()):,} rows)")


def fetch_form4s(*, company: str, cik: str, n: int = 5) -> None:
    print(f"\n[2/4] {company.upper()} Form 4 filings (latest {n})")
    cik_padded = cik.zfill(10)
    sub_url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    req = urllib.request.Request(sub_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        idx = json.loads(resp.read())

    r = idx["filings"]["recent"]
    matches = [
        (r["accessionNumber"][i], r["filingDate"][i], r["primaryDocument"][i])
        for i in range(len(r["accessionNumber"]))
        if r["form"][i] == "4"
    ][:n]

    for accession, date, primary in matches:
        acc_clean = accession.replace("-", "")
        doc = primary.split("/", 1)[1] if primary.startswith("xslF345X06/") else primary
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{doc}"
        local = REPO / f"coverage/{company}/inputs/sec_filings/4_{date}_{doc.replace('/', '_')}"
        fetch(url, local)


def fetch_press_release(*, company: str, cik: str, ticker_prefix: str) -> None:
    print(f"\n[3/4] {company.upper()} earnings press release (latest 8-K Ex 99.1)")
    cik_padded = cik.zfill(10)
    sub_url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    req = urllib.request.Request(sub_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        idx = json.loads(resp.read())

    r = idx["filings"]["recent"]
    eight_k = next(
        (i for i in range(len(r["accessionNumber"])) if r["form"][i] == "8-K"),
        None,
    )
    if eight_k is None:
        print("  ! no 8-K found; skipping press release")
        return

    accession = r["accessionNumber"][eight_k]
    acc_clean = accession.replace("-", "")
    archive_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/"
    req = urllib.request.Request(archive_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        listing = resp.read().decode("utf-8", errors="ignore")
    pattern = re.compile(rf'{ticker_prefix}-\d+xex991\.htm')
    m = pattern.search(listing)
    if not m:
        print(f"  ! no ex 99.1 found matching {pattern.pattern} in latest 8-K archive; skipping")
        return
    exhibit = m.group(0)
    fetch(archive_url + exhibit,
          REPO / f"coverage/{company}/inputs/ir/latest_press_release.htm")


def fetch_fred_csvs(*, company: str) -> None:
    print(f"\n[4/4] FRED macro CSVs (per-company copy)")
    for series in ["DGS10", "DGS30", "DBAA", "DEXUSEU", "CPIAUCSL", "GDPC1"]:
        fetch(
            f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}",
            REPO / f"coverage/{company}/inputs/macro/fred/{series.lower()}.csv",
            ua="Mozilla/5.0",
        )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--company", default="amzn",
                   help="Coverage ticker (registered in COMPANY_REGISTRY).")
    args = p.parse_args()

    if args.company not in COMPANY_REGISTRY:
        raise SystemExit(
            f"Unknown company: {args.company}. "
            f"Registered: {sorted(COMPANY_REGISTRY)}. "
            f"To add a new one, append a {{cik, ticker_prefix}} entry to "
            f"COMPANY_REGISTRY in scripts/seed_data.py."
        )
    info = COMPANY_REGISTRY[args.company]

    print(f"Seeding ai-financial-model data corpus for {args.company.upper()}.")
    print("Idempotent: re-running skips files that already exist.\n")

    bulk_dir = fetch_sec_fsds()
    slice_fsds_for_company(
        bulk_dir,
        cik=info["cik"],
        dest=REPO / f"coverage/{args.company}/inputs/sec_xbrl",
    )
    fetch_form4s(company=args.company, cik=info["cik"])
    fetch_press_release(company=args.company, cik=info["cik"],
                        ticker_prefix=info["ticker_prefix"])
    fetch_fred_csvs(company=args.company)

    print("\n✓ Done. Next steps:")
    print(f"  1. (optional) make refresh-macro COMPANY={args.company}")
    print(f"  2. make process-company COMPANY={args.company}   # end-to-end pipeline")


if __name__ == "__main__":
    main()
