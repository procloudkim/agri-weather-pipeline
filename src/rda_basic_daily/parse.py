"""
RDA getWeatherYearDayList3 raw XML -> CSV 파서.

- 입력: Fin_RDA_Daily_Weather_20251220/raw/*.xml
- 출력: Fin_RDA_Daily_Weather_20251220/bronze/csv/merged_daily.csv
- 주요 컬럼: station_code, stn_Cd, stn_Name, date(=obsr_Datetm), endpoint, chunk_start, chunk_end,
             no, temp, hghst_Artmp, lowst_Artmp, hum, wind, max_Wind, rn, srqty, sun_Time,
             condens_Time, widdir, gr_Temp, soil_Temp, soil_Wt
"""

from __future__ import annotations

import argparse
import calendar
import csv
from pathlib import Path
from typing import Dict, List
import xml.etree.ElementTree as ET

COLUMNS = [
    "station_code",
    "stn_Cd",
    "stn_Name",
    "date",
    "endpoint",
    "chunk_start",
    "chunk_end",
    "no",
    "temp",
    "hghst_Artmp",
    "lowst_Artmp",
    "hum",
    "wind",
    "max_Wind",
    "rn",
    "srqty",
    "sun_Time",
    "condens_Time",
    "widdir",
    "gr_Temp",
    "soil_Temp",
    "soil_Wt",
]


def parse_xml(path: Path) -> List[Dict[str, str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    root = ET.fromstring(text)
    records: List[Dict[str, str]] = []
    # station / year-month 추출
    name_parts = path.stem.split("_")
    station = name_parts[0] if name_parts else ""
    year = ""
    month = ""
    if len(name_parts) > 1 and "-" in name_parts[1]:
        ym = name_parts[1]
        y, m = ym.split("-", 1)
        year = y
        month = m
    chunk_start = f"{year}-{month}-01" if year and month else ""
    if year and month:
        try:
            last_day = calendar.monthrange(int(year), int(month))[1]
            chunk_end = f"{year}-{month}-{last_day:02d}"
        except Exception:
            chunk_end = ""
    else:
        chunk_end = ""
    for item in root.findall(".//item"):
        row: Dict[str, str] = {}
        for child in item:
            row[child.tag] = child.text.strip() if child.text else ""
        row["station_code"] = row.get("obsr_Spot_Cd") or row.get("stn_Cd") or station
        row["stn_Cd"] = row.get("stn_Cd") or row["station_code"]
        row["stn_Name"] = row.get("stn_Name") or row.get("obsr_Spot_Nm") or ""
        row["date"] = row.get("date") or row.get("obsr_Datetm") or row.get("tm") or ""
        row["endpoint"] = "getWeatherMonDayList3"
        row["chunk_start"] = chunk_start
        row["chunk_end"] = chunk_end
        records.append(row)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse RDA daily raw XML to CSV")
    parser.add_argument("--input-dir", default="Fin_RDA_Basic_Obsr_Daily_20251219/raw", help="raw XML 디렉터리")
    parser.add_argument("--output-csv", default="Fin_RDA_Basic_Obsr_Daily_20251219/bronze/csv/merged_daily.csv")
    args = parser.parse_args()

    raw_dir = Path(args.input_dir)
    out_csv = Path(args.output_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(raw_dir.glob("*.xml"))
    if not files:
        print(f"No XML files under {raw_dir}")
        return 1

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for path in files:
            try:
                rows = parse_xml(path)
                for row in rows:
                    writer.writerow({col: row.get(col, "") for col in COLUMNS})
            except Exception as e:  # pragma: no cover - best effort
                print(f"Failed to parse {path}: {e}")
                continue

    print(f"Wrote {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
