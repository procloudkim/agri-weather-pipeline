"""
RDA 농업기상 기본 관측 일자료(연/월/지점 단위, getWeatherMonDayList3) 수집 러너.

- 서비스키: .env의 AGRIWEATHER_SERVICE_KEY (URL에 1회만 포함)
- 필수 파라미터: Page_No, Page_Size(권장 40), search_Year(YYYY), search_Month(MM), obsr_Spot_Cd
- 기간: 1999-01 ~ 2025-12 월 단위로 태스크 생성
- 코드북: dqa/mappings/rda_station_codes.csv (obsr_Spot_Cd 컬럼 사용)
- 출력 트리 예: Fin_RDA_Basic_Obsr_Daily_20251219/{raw,manifest,logs}
- manifest: SUCCESS/NO_DATA/ERROR 기록, ALL DONE 로그 출력
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Iterable, List, Dict, Tuple

import requests
from dotenv import load_dotenv
from xml.etree import ElementTree as ET

BASE_URL = "https://apis.data.go.kr/1390802/AgriWeather/WeatherObsrInfo/V3/GnrlWeather/getWeatherMonDayList3"


class RateLimitError(RuntimeError):
    pass


def load_station_codes(path: Path, start_year: int, end_year: int, disable_filter: bool = False) -> List[Tuple[str, int | None, int | None]]:
    """Load station codes + begin_date(YYYY,MM), filtering by has_data and begin_date range (unless disabled)."""
    stations: List[Tuple[str, int | None, int | None]] = []
    if not path.exists():
        raise FileNotFoundError(f"station code file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = (row.get("obsr_Spot_Cd") or "").strip()
            if not code:
                continue
            begin_y: int | None = None
            begin_m: int | None = None
            if not disable_filter:
                has_data = (row.get("has_data") or "").strip().lower()
                if has_data and has_data not in {"true", "1", "y", "yes"}:
                    continue
                begin_date = (row.get("begin_date") or row.get("data_start_date") or "").strip()
                if begin_date:
                    try:
                        parts = begin_date.split("-")
                        bd_year = int(parts[0])
                        bd_month = int(parts[1]) if len(parts) > 1 else 1
                        if bd_year > end_year:
                            continue
                        begin_y, begin_m = bd_year, bd_month
                    except Exception:
                        begin_y, begin_m = None, None
            stations.append((code, begin_y, begin_m))
    # dedupe by code, keep earliest begin date
    dedup: Dict[str, Tuple[int | None, int | None]] = {}
    for code, by, bm in stations:
        if code not in dedup:
            dedup[code] = (by, bm)
        else:
            prev_by, prev_bm = dedup[code]
            if by is not None:
                if prev_by is None or (by < prev_by) or (by == prev_by and (bm or 1) < (prev_bm or 1)):
                    dedup[code] = (by, bm)
    return sorted([(c, y, m) for c, (y, m) in dedup.items()], key=lambda x: x[0])


def fetch_page(url_with_key: str, params: dict, timeout: int = 15) -> str:
    resp = requests.get(url_with_key, params=params, timeout=timeout)
    if resp.status_code == 429:
        raise RateLimitError("HTTP 429 Too Many Requests")
    resp.raise_for_status()
    return resp.text


def parse_total(xml_text: str) -> Tuple[int, List[Dict[str, str]]]:
    root = ET.fromstring(xml_text)
    total = 0
    total_el = root.find(".//totalCount") or root.find(".//Total_Count")
    if total_el is not None and total_el.text:
        try:
            total = int(total_el.text.strip())
        except Exception:
            total = 0
    items: List[Dict[str, str]] = []
    for item in root.findall(".//item"):
        row: Dict[str, str] = {}
        for child in item:
            row[child.tag] = child.text.strip() if child.text else ""
        items.append(row)
    return total, items


def sanitize_params(params: dict) -> dict:
    safe = dict(params)
    for name in list(safe):
        if "servicekey" in name.lower() or name.lower() in {"key", "apikey", "authkey"}:
            safe[name] = "***"
    return safe


def sanitize_error(message: str) -> str:
    if not message:
        return message
    return re.sub(r"(?i)(servicekey=)[^&\s]+", r"\1***", message)


def write_manifest(path: Path, rec: dict) -> None:
    # 공개본 정정(2026-08-16): 이 러너에는 마스킹 함수가 아예 없었다. 서비스키를
    # 쿼리스트링에 붙여 요청하므로 requests 예외 메시지에 전체 URL 이 들어가고,
    # 그것이 str(e) 로 manifest 와 로그에 그대로 기록되고 있었다. 세 러너 중
    # 유일하게 실제 유출 경로가 있던 곳이라 기록 직전에 일괄 마스킹으로 막는다.
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = dict(rec)
    if "error" in safe:
        safe["error"] = sanitize_error(str(safe["error"]))
    if isinstance(safe.get("params"), dict):
        safe["params"] = sanitize_params(safe["params"])
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(safe, ensure_ascii=False) + "\n")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RDA getWeatherMonDayList3 수집 러너")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--page-size", type=int, default=40, help="Page_Size (권장 40)")
    parser.add_argument("--rps", type=float, default=3.0, help="Requests per second (default 3.0)")
    parser.add_argument("--resume", action="store_true", help="manifest SUCCESS/NO_DATA 기준 스킵")
    parser.add_argument("--skip-existing", action="store_true", help="raw XML이 있으면 재요청 스킵")
    parser.add_argument("--max-retries", type=int, default=3, help="HTTP 재시도 횟수 (default 3)")
    parser.add_argument("--retry-backoff", type=float, default=2.0, help="재시도 백오프 시작값(초)")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP 타임아웃(초)")
    parser.add_argument("--stations-file", default="dqa/mappings/rda_station_codes.csv", help="obsr_Spot_Cd 목록 CSV 경로")
    parser.add_argument("--output-dir", default="Fin_RDA_Basic_Obsr_Daily_20251219", help="출력 베이스 디렉터리")
    parser.add_argument("--manifest", default=None, help="명시 시 해당 경로로 manifest 기록")
    parser.add_argument("--log-file", default=None, help="명시 시 로그 파일 경로")
    parser.add_argument("--no-station-filter", action="store_true", help="has_data/begin_date 필터 미적용(전수 호출)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    load_dotenv()
    key = (os.getenv("AGRIWEATHER_SERVICE_KEY") or "").strip()
    if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
        key = key[1:-1].strip()
    if not key:
        print("AGRIWEATHER_SERVICE_KEY not set", file=sys.stderr)
        return 1
    if "serviceKey" in key or "&" in key or "=" in key:
        print("AGRIWEATHER_SERVICE_KEY looks malformed; encoded 키만 넣어주세요.", file=sys.stderr)
        return 1

    url_with_key = f"{BASE_URL}?serviceKey={key}"

    start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    start_year = start.year
    end_year = end.year
    # 월 목록 생성
    months: List[Tuple[int, int]] = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        months.append((cur.year, cur.month))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)

    stations = load_station_codes(Path(args.stations_file), start_year, end_year, disable_filter=args.no_station_filter)
    if not stations:
        print("station codes empty", file=sys.stderr)
        return 1

    base_dir = Path(args.output_dir)
    raw_dir = base_dir / "raw"
    manifest_path = Path(args.manifest) if args.manifest else base_dir / "manifest" / "rda_daily_fetch.jsonl"
    log_path = Path(args.log_file) if args.log_file else base_dir / "logs" / "rda_daily_fetch.log"
    raw_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")],
    )

    # resume map
    completed: Dict[Tuple[str, int, int, int], int] = {}
    if args.resume and manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("status") not in {"SUCCESS", "NO_DATA"}:
                    continue
                station = str(rec.get("station_code") or "").strip()
                year = int(rec.get("year") or 0)
                month = int(rec.get("month") or 0)
                page = int(rec.get("page") or 0)
                completed[(station, year, month, page)] = int(rec.get("total") or rec.get("rows") or 0)
        logging.info("Resume enabled: loaded %d completed pages", len(completed))

    min_interval = 1.0 / args.rps if args.rps > 0 else 0.0
    next_allowed = time.monotonic()

    total_tasks = len(stations) * len(months)
    task_idx = 0
    t0 = time.time()

    for station, begin_y, begin_m in stations:
        for year, month in months:
            if begin_y is not None:
                if year < begin_y:
                    continue
                if year == begin_y and begin_m is not None and month < begin_m:
                    continue
            task_idx += 1
            logging.info("[%d/%d] station=%s year=%s month=%02d", task_idx, total_tasks, station, year, month)
            page_no = 1
            while True:
                if args.resume and (station, year, month, page_no) in completed:
                    page_no += 1
                    continue
                raw_name = f"{station}_{year}-{month:02d}_p{page_no}.xml"
                raw_path = raw_dir / raw_name
                if args.skip_existing and raw_path.exists():
                    try:
                        total, items = parse_total(raw_path.read_text(encoding="utf-8", errors="ignore"))
                        rows = len(items)
                        if rows < args.page_size or (page_no * args.page_size) >= total or total == 0:
                            break
                        page_no += 1
                        continue
                    except Exception:
                        # fall through to re-fetch if parsing existing file failed
                        pass

                params = {
                    "Page_No": page_no,
                    "Page_Size": args.page_size,
                    "search_Year": year,
                    "search_Month": f"{month:02d}",
                    "obsr_Spot_Cd": station,
                }

                attempts = 0
                xml_text = None
                while attempts <= args.max_retries:
                    if min_interval > 0:
                        now = time.monotonic()
                        if now < next_allowed:
                            time.sleep(next_allowed - now)
                        next_allowed = time.monotonic() + min_interval
                    try:
                        xml_text = fetch_page(url_with_key, params, timeout=args.timeout)
                        break
                    except RateLimitError as e:
                        logging.error("rate limit on page %d: %s", page_no, sanitize_error(str(e)))
                        write_manifest(
                            manifest_path,
                            {
                                "status": "RATE_LIMIT",
                                "station_code": station,
                                "year": year,
                                "month": month,
                                "page": page_no,
                                "params": params,
                            },
                        )
                        xml_text = None
                        break
                    except Exception as e:
                        attempts += 1
                        if attempts > args.max_retries:
                            logging.error("fetch failed p%d after retries: %s", page_no, sanitize_error(str(e)))
                            write_manifest(
                                manifest_path,
                                {
                                    "status": "ERROR",
                                    "station_code": station,
                                    "year": year,
                                    "month": month,
                                    "page": page_no,
                                    "error": str(e),
                                    "params": params,
                                },
                            )
                            xml_text = None
                            break
                        backoff = args.retry_backoff * (2 ** (attempts - 1))
                        logging.warning("retry %d/%d after %.1fs: %s", attempts, args.max_retries, backoff, sanitize_error(str(e)))
                        time.sleep(backoff)
                        continue

                if xml_text is None:
                    break

                raw_path.write_text(xml_text, encoding="utf-8")
                total, items = parse_total(xml_text)
                rows = len(items)
                status = "NO_DATA" if total == 0 or rows == 0 else "SUCCESS"
                write_manifest(
                    manifest_path,
                    {
                        "status": status,
                        "station_code": station,
                        "year": year,
                        "month": month,
                        "page": page_no,
                        "rows": rows,
                        "total": total,
                        "raw_file": str(raw_path),
                        "params": params,
                    },
                )
                logging.info("page %d rows=%d total=%d", page_no, rows, total)
                if rows < args.page_size or (page_no * args.page_size) >= total or total == 0:
                    break
                page_no += 1

            elapsed = time.time() - t0
            remain = (total_tasks - task_idx) * (elapsed / task_idx) if task_idx else 0
            logging.info("done station=%s year=%s month=%02d elapsed=%.1fs ETA~%.1fs", station, year, month, elapsed, remain)

    logging.info("ALL DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
