"""
RDA 농작물 주산지 농업기상분석정보 일별 조회(getWeatherPlpdDayList) 러너.

- 서비스키: .env의 AGRIWEATHER_SERVICE_KEY 사용 (querystring 포함 금지, 한 번만 전달)
- 코드북: dqa/mappings/rda_frc_crop_codes.csv, dqa/mappings/rda_frc_obsr_codes.csv
- 기간: CLI 입력(start/end), 날짜 청크 단위(begin_Date/end_Date) 호출
- 출력 트리 예: Fin_RDA_CropArea_Daily_20251219/{raw, manifest, logs}
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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List

import requests
from dotenv import load_dotenv
from xml.etree import ElementTree as ET

BASE_URL = "https://apis.data.go.kr/1390802/AgriWeather/WeatherObsrInfo/frcPlpd/getWeatherPlpdDayList"


class RateLimitError(RuntimeError):
    pass


def load_csv(path: Path) -> List[dict]:
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def daterange_chunks(start: datetime, end: datetime, span_days: int):
    cur = start
    delta = timedelta(days=span_days - 1)
    one_day = timedelta(days=1)
    while cur <= end:
        nxt = min(cur + delta, end)
        yield cur, nxt
        cur = nxt + one_day


def fetch_page(url: str, params: dict, timeout: int = 20) -> bytes:
    resp = requests.get(url, params=params, timeout=timeout)
    if resp.status_code == 429:
        raise RateLimitError("HTTP 429 Too Many Requests")
    resp.raise_for_status()
    return resp.content


def parse_total_and_rows(xml_bytes: bytes) -> tuple[int, int]:
    root = ET.fromstring(xml_bytes)
    total = int(root.findtext(".//total_Count") or root.findtext(".//totalCount") or "0")
    items = root.findall(".//item")
    return total, len(items)


def sanitize_params(params: dict) -> dict:
    safe = dict(params)
    if "serviceKey" in safe:
        safe["serviceKey"] = "***"
    return safe


def sanitize_error(message: str) -> str:
    if not message:
        return message
    # 공개본 정정(2026-08-16): 원본은 `[^&\\s]` 와 `\\1` 로 이스케이프가 한 단계 더 들어가
    # 있었다. 그 상태에서는 치환 결과가 리터럴 `\1***` 이 되고 키 뒷부분이 그대로 남아,
    # 마스킹한 것처럼 보이면서 실제로는 유출되고 있었다. KMA 러너의 정상 구현과 맞췄다.
    return re.sub(r"(?i)(servicekey=)[^&\s]+", r"\1***", message)


def build_params(obsr_spot_code: str, start: datetime, end: datetime, page: int, page_size: int) -> dict:
    return {
        "Page_No": page,
        "Page_Size": page_size,
        "obsr_Spot_Code": obsr_spot_code,
        "begin_Date": start.strftime("%Y%m%d"),
        "end_Date": end.strftime("%Y%m%d"),
    }


def load_completed(manifest_path: Path) -> dict[tuple[str, str, str, str, int], tuple[int, int]]:
    completed: dict[tuple[str, str, str, str, int], tuple[int, int]] = {}
    if not manifest_path.exists():
        return completed
    with manifest_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("status") not in {"SUCCESS", "NO_DATA"}:
                continue
            page = rec.get("page")
            try:
                page = int(page)
            except (TypeError, ValueError):
                continue
            obsr = str(rec.get("obsr_Spot_Code") or "").strip()
            start = str(rec.get("start") or "").strip()
            end = str(rec.get("end") or "").strip()
            if not obsr or not start or not end:
                continue
            rows = rec.get("rows") or 0
            total = rec.get("total") or rows
            try:
                rows = int(rows)
            except (TypeError, ValueError):
                rows = 0
            try:
                total = int(total)
            except (TypeError, ValueError):
                total = rows
            completed[(obsr, start, end, page)] = (rows, total)
    return completed


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RDA 농작물 주산지 일별 분석정보 수집 러너")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--rps", type=float, default=1.0)
    parser.add_argument("--chunk-days", type=int, default=31, help="날짜 청크 길이(일)")
    parser.add_argument("--resume", action="store_true", help="manifest SUCCESS/NO_DATA 스킵")
    parser.add_argument("--skip-existing", action="store_true", help="raw 파일 존재 시 스킵")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-backoff", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument(
        "--crop-codes",
        default="dqa/mappings/rda_frc_crop_codes.csv",
        help="작물 코드북",
    )
    parser.add_argument(
        "--obsr-codes",
        default="dqa/mappings/rda_frc_obsr_codes.csv",
        help="주산지 관측지점 코드북",
    )
    parser.add_argument(
        "--output-dir",
        default="Fin_RDA_CropArea_Daily_20251219",
        help="결과 베이스 디렉터리",
    )
    parser.add_argument("--manifest", default=None, help="manifest 경로 (기본: <output-dir>/manifest/rda_crop_fetch.jsonl)")
    parser.add_argument("--log-file", default=None, help="로그 파일 경로 (기본: <output-dir>/logs/rda_crop_fetch.log)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    load_dotenv()
    key = (os.getenv("AGRIWEATHER_SERVICE_KEY") or "").strip()
    if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
        key = key[1:-1].strip()
    if not key:
        logging.error("AGRIWEATHER_SERVICE_KEY not set")
        return 1
    if "serviceKey=" in key or "&" in key:
        logging.error("AGRIWEATHER_SERVICE_KEY malformed; encoded key만 입력하세요.")
        return 1

    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    end = datetime.strptime(args.end_date, "%Y-%m-%d")
    chunks = list(daterange_chunks(start, end, args.chunk_days))

    crop_codes = {row["frc_Code"]: row for row in load_csv(Path(args.crop_codes))}
    obsr_rows = load_csv(Path(args.obsr_codes))

    base_dir = Path(args.output_dir)
    out_raw = base_dir / "raw"
    manifest_path = Path(args.manifest) if args.manifest else base_dir / "manifest" / "rda_crop_fetch.jsonl"
    log_path = Path(args.log_file) if args.log_file else base_dir / "logs" / "rda_crop_fetch.log"
    out_raw.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")],
    )

    completed = load_completed(manifest_path) if args.resume else {}
    if args.resume and completed:
        logging.info("Resume enabled: loaded %d completed pages", len(completed))

    min_interval = 1.0 / args.rps if args.rps and args.rps > 0 else 0.0
    next_allowed = time.monotonic()

    total_tasks = len(obsr_rows) * len(chunks)
    task_idx = 0
    t0 = time.time()
    success_pages = 0
    skipped_pages = 0
    error_pages = 0
    rate_limited = False

    url_with_key = f"{BASE_URL}?serviceKey={key}"

    for obsr in obsr_rows:
        obsr_code = str(obsr.get("obsr_Spot_Code") or "").strip()
        frc_code = str(obsr.get("frc_Code") or "").strip()
        crop_meta = crop_codes.get(frc_code, {})
        prdlst_code = crop_meta.get("prdlst_Code", "")
        prdlst_nm = crop_meta.get("prdlst_Code_Nm", "")
        frc_nm = crop_meta.get("frc_Nm", "")
        if not obsr_code:
            continue

        for chunk_start, chunk_end in chunks:
            task_idx += 1
            start_str = str(chunk_start.date())
            end_str = str(chunk_end.date())
            logging.info(
                "[%d/%d] obsr=%s crop=%s %s~%s",
                task_idx,
                total_tasks,
                obsr_code,
                frc_code,
                chunk_start.date(),
                chunk_end.date(),
            )
            page_no = 1
            while True:
                raw_name = f"{obsr_code}_{chunk_start.date()}_{chunk_end.date()}_p{page_no}.xml"
                raw_path = out_raw / raw_name
                task_key = (obsr_code, start_str, end_str, page_no)

                if args.resume and task_key in completed:
                    rows, total = completed[task_key]
                    skipped_pages += 1
                    if rows < args.page_size or (page_no * args.page_size) >= total or total == 0:
                        break
                    page_no += 1
                    continue

                if args.skip_existing and raw_path.exists():
                    try:
                        total, rcdcnt = parse_total_and_rows(raw_path.read_bytes())
                        skipped_pages += 1
                        if rcdcnt < args.page_size or (page_no * args.page_size) >= total or total == 0:
                            break
                        page_no += 1
                        continue
                    except Exception:
                        pass

                params = build_params(obsr_code, chunk_start, chunk_end, page_no, args.page_size)
                xml_bytes = None
                attempts = 0
                while attempts <= args.max_retries:
                    if min_interval > 0:
                        now = time.monotonic()
                        if now < next_allowed:
                            time.sleep(next_allowed - now)
                        next_allowed = time.monotonic() + min_interval
                    try:
                        xml_bytes = fetch_page(url_with_key, params, timeout=args.timeout)
                        break
                    except RateLimitError as e:
                        rate_limited = True
                        safe_error = sanitize_error(str(e))
                        logging.error("rate limit hit p%d: %s", page_no, safe_error)
                        break
                    except Exception as e:
                        attempts += 1
                        safe_error = sanitize_error(str(e))
                        if attempts > args.max_retries:
                            logging.error("fetch failed p%d after retries: %s", page_no, safe_error)
                            write_manifest(
                                manifest_path,
                                {
                                    "status": "ERROR",
                                    "obsr_Spot_Code": obsr_code,
                                    "frc_Code": frc_code,
                                    "prdlst_Code": prdlst_code,
                                    "prdlst_Code_Nm": prdlst_nm,
                                    "frc_Nm": frc_nm,
                                    "start": start_str,
                                    "end": end_str,
                                    "page": page_no,
                                    "error": safe_error,
                                    "params": sanitize_params(params),
                                },
                            )
                            error_pages += 1
                            xml_bytes = None
                            break
                        backoff = args.retry_backoff * (2 ** (attempts - 1))
                        logging.warning(
                            "retry %d/%d after %.1fs: %s",
                            attempts,
                            args.max_retries,
                            backoff,
                            safe_error,
                        )
                        time.sleep(backoff)
                        continue

                if rate_limited or xml_bytes is None:
                    break

                raw_path.write_bytes(xml_bytes)
                total, rcdcnt = parse_total_and_rows(xml_bytes)
                logging.info("page %d rows=%d total=%d", page_no, rcdcnt, total)
                status = "NO_DATA" if total == 0 else "SUCCESS"
                if status == "SUCCESS":
                    success_pages += 1
                write_manifest(
                    manifest_path,
                    {
                        "status": status,
                        "obsr_Spot_Code": obsr_code,
                        "frc_Code": frc_code,
                        "prdlst_Code": prdlst_code,
                        "prdlst_Code_Nm": prdlst_nm,
                        "frc_Nm": frc_nm,
                        "start": start_str,
                        "end": end_str,
                        "page": page_no,
                        "rows": rcdcnt,
                        "total": total,
                        "raw_file": str(raw_path),
                        "params": sanitize_params(params),
                    },
                )
                if rcdcnt < args.page_size or (page_no * args.page_size) >= total or total == 0:
                    break
                page_no += 1

            elapsed = time.time() - t0
            remain = (total_tasks - task_idx) * (elapsed / task_idx) if task_idx else 0
            logging.info("done pages=%d, elapsed=%.1fs, ETA~%.1fs", page_no, elapsed, remain)
        if rate_limited:
            logging.error("rate limit encountered; stopping run")
            break

    logging.info(
        "summary tasks=%d success_pages=%d skipped_pages=%d error_pages=%d",
        total_tasks,
        success_pages,
        skipped_pages,
        error_pages,
    )
    logging.info("ALL DONE")
    if rate_limited:
        return 2
    return 0


def write_manifest(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
