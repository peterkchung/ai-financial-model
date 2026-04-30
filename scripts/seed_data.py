# About: One-shot data bootstrap. Downloads everything the AMZN end-to-end
# pipeline needs from public sources (SEC EDGAR, FRED, NYU Stern). Idempotent —
# re-running skips files that already exist.
#
# Run after a fresh clone:
#   make seed-data
#   make process-company COMPANY=amzn

from __future__ import annotations
import json
import os
import shutil
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

# SEC requires a User-Agent identifying the requester, format:
# "<Company / Project> <admin email>". Override via env var SEC_UA.
DEFAULT_UA = "ai-financial-model-research aifm-bootstrap@example.com"
UA = os.environ.get("SEC_UA", DEFAULT_UA)
REPO = Path(__file__).resolve().parents[1]


def fetch(url: str, dest: Path, ua: str = UA) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  ✓ {dest.relative_to(REPO)}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ⤓ {dest.relative_to(REPO)}")
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
    except urllib.error.HTTPError as e:
        dest.unlink(missing_ok=True)
        raise SystemExit(f"  ✗ {url} → HTTP {e.code}: {e.reason}") from e


def fetch_sec_fsds() -> None:
    """SEC bulk XBRL facts — the high-recall company-financials source."""
    print("\n[1/5] SEC Financial Statement Data Sets (~80 MB zip → ~640 MB unpacked)")
    fsds_dir = REPO / "data/sec/financial_statement_data_sets"
    zip_path = fsds_dir / "2026q1.zip"
    fetch(
        "https://www.sec.gov/files/dera/data/financial-statement-data-sets/2026q1.zip",
        zip_path,
    )
    unpacked = fsds_dir / "2026q1"
    if not (unpacked / "sub.txt").exists():
        print(f"  ⊞ unzipping {zip_path.name}")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(unpacked)


def fetch_amzn_form4s(n: int = 5) -> None:
    """Recent Form 4 (insider transactions) XML for AMZN."""
    print(f"\n[2/5] AMZN Form 4 filings (latest {n})")
    cik = "1018724"
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
        # Strip XSL stylesheet prefix from Form 4 paths to get raw XML
        doc = primary.split("/", 1)[1] if primary.startswith("xslF345X06/") else primary
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{doc}"
        local = REPO / f"data/sec/amzn/4_{date}_{doc.replace('/', '_')}"
        fetch(url, local)


def fetch_amzn_press_release() -> None:
    """Most recent AMZN earnings press release (8-K Ex 99.1).

    Discovers the latest 8-K from EDGAR submissions, then resolves its
    Ex 99.1 by listing the filing's archive index.
    """
    print("\n[3/5] AMZN earnings press release (latest 8-K Ex 99.1)")
    cik = "1018724"
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
    # Convention for AMZN: amzn-<periodend>xex991.htm
    import re
    m = re.search(r'amzn-\d+xex991\.htm', listing)
    if not m:
        print("  ! no ex 99.1 found in latest 8-K archive; skipping")
        return
    exhibit = m.group(0)
    fetch(archive_url + exhibit, REPO / "data/ir/amzn/latest_press_release.htm")


def fetch_fred_csvs() -> None:
    """FRED macro CSVs — feed into refresh_macro_fred.py."""
    print("\n[4/5] FRED macro CSVs")
    for series in ["DGS10", "DGS30", "DBAA", "DEXUSEU", "CPIAUCSL", "GDPC1"]:
        fetch(
            f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}",
            REPO / f"data/macro/fred/{series.lower()}.csv",
            ua="Mozilla/5.0",
        )


def fetch_damodaran() -> None:
    """NYU Stern industry-aggregate datasets — feed into refresh_industry_damodaran.py."""
    print("\n[5/5] NYU Stern industry datasets")
    base = "https://pages.stern.nyu.edu/~adamodar/pc/datasets"
    for fn in ["totalbeta.xls", "margin.xls", "roc.xls", "wacc.xls", "histimpl.xls"]:
        fetch(f"{base}/{fn}", REPO / f"data/macro/damodaran/{fn}", ua="Mozilla/5.0")


def main() -> None:
    print("Seeding ai-financial-model data corpus.")
    print("Idempotent: re-running skips files that already exist.\n")
    fetch_sec_fsds()
    fetch_amzn_form4s()
    fetch_amzn_press_release()
    fetch_fred_csvs()
    fetch_damodaran()
    print("\n✓ Done. Next steps:")
    print("  1. (optional) make refresh-macro       # FRED → data/macro_inputs/us_default.yaml")
    print("  2. (optional) make refresh-industry    # Damodaran → data/industry/retail_general.yaml")
    print("  3. make process-company COMPANY=amzn   # end-to-end pipeline")


if __name__ == "__main__":
    main()
