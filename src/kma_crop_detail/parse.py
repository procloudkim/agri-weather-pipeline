"""
기상청_작물별 농업주산지 상세날씨 조회서비스 RAW(XML) → CSV 변환 스크립트.
 - 입력: <base>/raw/*.xml (crop_detail_run.py 수집 결과)
 - 출력: <base>/bronze/csv/crop_detail_all.csv
 - manifest: <base>/manifest/crop_detail_parse.jsonl (파일 단위 상태 기록)
 - 로그: <base>/logs/crop_detail_parse.log

응답 필드(문서 기준):
  ymd, areaId, areaName, paCropName, paCropSpeId, paCropSpeName,
  dayAvgTa, dayMaxTa, dayMinTa, dayAvgRhm, dayMinRhm,
  daySumRn, dayAvgWs, daySumSs, wmCount, wmCd
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from xml.etree import ElementTree as ET


FIELDS = [
    "ymd",
    "areaId",
    "areaName",
    "paCropName",
    "paCropSpeId",
    "paCropSpeName",
    "dayAvgTa",
    "dayMaxTa",
    "dayMinTa",
    "dayAvgRhm",
    "dayMinRhm",
    "daySumRn",
    "dayAvgWs",
    "daySumSs",
    "wmCount",
    "wmCd",
    "_source_file",
]


def parse_xml_file(path: Path) -> list[dict]:
    rows: list[dict] = []
    root = ET.parse(path).getroot()
    for item in root.findall(".//item"):
        row = {k: (item.findtext(k) or "").strip() for k in FIELDS if not k.startswith("_")}
        row["_source_file"] = path.name
        rows.append(row)
    return rows


def write_manifest(manifest: Path, file: Path, status: str, rows: int, error: str | None = None) -> None:
    rec = {
        "file": str(file),
        "status": status,
        "rows": rows,
        "error": error or "",
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="RAW XML → CSV 변환 (기상청 주산지 상세날씨)")
    parser.add_argument("--raw-dir", default="Fin_KMA_CropArea_Weather_20251219/raw", help="원본 XML 경로")
    parser.add_argument("--output-csv", default="Fin_KMA_CropArea_Weather_20251219/bronze/csv/crop_detail_all.csv")
    parser.add_argument("--manifest", default="Fin_KMA_CropArea_Weather_20251219/manifest/crop_detail_parse.jsonl")
    parser.add_argument("--log-file", default="Fin_KMA_CropArea_Weather_20251219/logs/crop_detail_parse.log")
    parser.add_argument("--skip-parsed", action="store_true", help="manifest 성공 기록된 파일은 건너뜀")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(), logging.FileHandler(args.log_file, encoding="utf-8")],
    )

    raw_dir = Path(args.raw_dir)
    manifest_path = Path(args.manifest)
    out_csv = Path(args.output_csv)

    parsed_ok = set()
    if args.skip_parsed and manifest_path.exists():
        with manifest_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if rec.get("status") == "SUCCESS":
                        parsed_ok.add(Path(rec.get("file")).name)
                except Exception:
                    continue

    files = sorted(raw_dir.glob("*.xml"))
    if not files:
        logging.warning("No XML files found in %s", raw_dir)
        return 0

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    total_rows = 0
    append_mode = args.skip_parsed and out_csv.exists()
    write_mode = "a" if append_mode else "w"
    write_header = not append_mode or out_csv.stat().st_size == 0
    with out_csv.open(write_mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()

        for i, file in enumerate(files, 1):
            if file.name in parsed_ok:
                logging.info("[%d/%d] skip (already parsed) %s", i, len(files), file.name)
                continue
            try:
                rows = parse_xml_file(file)
                if rows:
                    writer.writerows(rows)
                    total_rows += len(rows)
                write_manifest(manifest_path, file, "SUCCESS", len(rows))
                logging.info("[%d/%d] parsed %s rows=%d", i, len(files), file.name, len(rows))
            except Exception as e:
                write_manifest(manifest_path, file, "ERROR", 0, str(e))
                logging.error("[%d/%d] error %s: %s", i, len(files), file.name, e)

    logging.info("CSV written: %s rows=%d", out_csv, total_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
