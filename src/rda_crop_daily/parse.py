"""
RDA 농작물 주산지 일별 분석정보 XML -> CSV 파서.
- 입력: raw XML (기본: Fin_RDA_CropArea_Daily_20251219/raw)
- 출력: Fin_RDA_CropArea_Daily_20251219/bronze/csv/merged_crop_daily.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from xml.etree import ElementTree as ET


# 스펙 순서에 맞춘 컬럼 (성공 응답 예시 기준)
DEFAULT_COLS = [
    "no",
    "obsr_Datetm",
    "obsr_Spot_Code",
    "tmprt",
    "tmprt_Top",
    "tmprt_Lwet",
    "afp",
    "sunshn_Time",
    "solrad_Qy",
    "arvlty",
    "frfr_Tp",
    "frfr_Tp_Top",
    "frfr_Tp_Lwet",
    "udgr_Tp",
    "udgr_Tp_Top",
    "udgr_Tp_Lwet",
    "soil_Mitr_Cmst",
    "soil_Mitr_Cmst_Top",
    "soil_Mitr_Cmst_Lwet",
]


def parse_file(path: Path, cols: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    root = ET.fromstring(path.read_bytes())
    for item in root.findall(".//item"):
        row = []
        for c in cols:
            row.append(item.findtext(c, default="") or "")
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="RDA crop daily XML -> CSV")
    parser.add_argument(
        "--input-dir",
        default="Fin_RDA_CropArea_Daily_20251219/raw",
        help="XML raw 디렉터리",
    )
    parser.add_argument(
        "--output-csv",
        default="Fin_RDA_CropArea_Daily_20251219/bronze/csv/merged_crop_daily.csv",
        help="머지 CSV 경로",
    )
    args = parser.parse_args()

    in_dir = Path(args.input_dir)
    out_path = Path(args.output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    xml_files = sorted(in_dir.rglob("*.xml"))
    if not xml_files:
        print(f"No XML files under {in_dir}")
        return 0

    cols = DEFAULT_COLS
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for xp in xml_files:
            rows = parse_file(xp, cols)
            writer.writerows(rows)

    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
