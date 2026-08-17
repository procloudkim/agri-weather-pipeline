"""
기상청_작물별 농업주산지 상세날씨 조회서비스 호출 러너(getDayStatistics).

- .env의 AGRIWEATHER_SERVICE_KEY 사용
- 지역/작물 특성 코드북: docs/kma_local_code_22.05.csv 또는 활용가이드 제공 CSV
- 기간: CLI 입력(start/end), 날짜 청크 호출
- Page_Size: 기본 1000, Page_No=1부터 totalCount까지 반복
- 출력 트리 예: Fin_KMA_CropArea_Weather_20251219/raw/*.xml, manifest/*.jsonl, logs/*.log
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List

import requests
from dotenv import load_dotenv
from xml.etree import ElementTree as ET

# 문서 기준 엔드포인트 (일통계)
BASE_URL = "http://apis.data.go.kr/1360000/FmlandWthrInfoService/getDayStatistics"

class RateLimitError(RuntimeError):
    pass


def load_codes(path: Path) -> List[dict]:
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
    # url은 serviceKey가 미리 붙은 형태로 전달된다.
    resp = requests.get(url, params=params, timeout=timeout)
    if resp.status_code == 429:
        raise RateLimitError("HTTP 429 Too Many Requests")
    resp.raise_for_status()
    return resp.content


def parse_total_and_rows(xml_bytes: bytes) -> tuple[int, int]:
    root = ET.fromstring(xml_bytes)
    total = int(root.findtext(".//totalCount") or root.findtext(".//total_Count") or "0")
    items = root.findall(".//item")
    return total, len(items)


def build_params(
    area_id: str,
    pa_crop_spe_id: str,
    start: datetime,
    end: datetime,
    page_no: int,
    page_size: int,
) -> dict:
    # 문서 기준 필드명: ST_YMD, ED_YMD, AREA_ID, PA_CROP_SPE_ID
    return {
        "pageNo": page_no,
        "numOfRows": page_size,
        "dataType": "XML",
        "ST_YMD": start.strftime("%Y%m%d"),
        "ED_YMD": end.strftime("%Y%m%d"),
        "AREA_ID": area_id,
        "PA_CROP_SPE_ID": pa_crop_spe_id,
    }


def write_manifest(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def sanitize_params(params: dict) -> dict:
    # 공개본 정정(2026-08-16): 원본은 dict 를 그대로 반환해 이름과 달리 아무것도
    # 마스킹하지 않았다. 이 러너는 서비스키를 URL 에 미리 붙여 전달하므로 params 에
    # 키가 들어올 경로가 없어 유출은 없었으나, 마스킹한다고 이름 붙인 함수가
    # 실제로는 통과시키는 상태는 다음 사람에게 잘못된 안전감을 준다.
    safe = dict(params)
    for name in list(safe):
        if "servicekey" in name.lower() or name.lower() in {"key", "apikey", "authkey"}:
            safe[name] = "***"
    return safe


def sanitize_error(message: str) -> str:
    if not message:
        return message
    return re.sub(r"(?i)(servicekey=)[^&\s]+", r"\1***", message)


def _parse_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
            page = _parse_int(rec.get("page"))
            if page is None:
                continue
            area_id = str(rec.get("area_id") or "").strip()
            pa_crop_spe_id = str(rec.get("pa_crop_spe_id") or "").strip()
            start = str(rec.get("start") or "").strip()
            end = str(rec.get("end") or "").strip()
            if not area_id or not pa_crop_spe_id or not start or not end:
                continue
            rows = _parse_int(rec.get("rows")) or 0
            total = _parse_int(rec.get("total")) or rows
            completed[(area_id, pa_crop_spe_id, start, end, page)] = (rows, total)
    return completed


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="기상청 주산지 상세날씨 호출 러너")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--rps", type=float, default=1.0)
    parser.add_argument(
        "--key-param",
        default="serviceKey",
        choices=["serviceKey", "ServiceKey"],
        help="서비스키 파라미터명 (default: serviceKey)",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=30,
        help="날짜 청크 길이(일) (default: 30)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="manifest SUCCESS/NO_DATA 기준으로 재시작 시 스킵",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="raw 파일이 이미 있으면 해당 페이지 재요청 스킵",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="요청 실패 재시도 횟수 (default: 3)",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=2.0,
        help="재시도 백오프 시작값(초) (default: 2.0)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP 타임아웃(초) (default: 20)",
    )
    parser.add_argument("--workers", type=int, default=1)  # 병렬 미사용 스텁
    parser.add_argument(
        "--region-code-file",
        required=False,
        default="docs/kma_local_code_22.05.csv",
        help="지역 코드 CSV 경로 (기본: docs/kma_local_code_22.05.csv)",
    )
    parser.add_argument(
        "--output-dir",
        default="Fin_KMA_CropArea_Weather_20251219",
        help="결과 베이스 디렉터리 (raw/manifest/logs 하위 생성)",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="명시 시 해당 경로로 manifest 기록 (기본: <output-dir>/manifest/crop_detail_fetch.jsonl)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="명시 시 파일 로그 기록 (기본: <output-dir>/logs/crop_detail_fetch.log)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    load_dotenv()
    key = (os.getenv("AGRIWEATHER_SERVICE_KEY") or "").strip()
    if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
        key = key[1:-1].strip()
    if not key:
        logging.error("AGRIWEATHER_SERVICE_KEY not set")
        return 1
    if "serviceKey=" in key or "ServiceKey=" in key or "&" in key:
        logging.error("AGRIWEATHER_SERVICE_KEY looks malformed; use the encoded key only.")
        return 1
    key_param = args.key_param or "serviceKey"
    url_with_key = f"{BASE_URL}?{key_param}={key}"

    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    end = datetime.strptime(args.end_date, "%Y-%m-%d")
    regions = load_codes(Path(args.region_code_file))

    base_dir = Path(args.output_dir)
    out_raw = base_dir / "raw"
    manifest_path = Path(args.manifest) if args.manifest else base_dir / "manifest" / "crop_detail_fetch.jsonl"
    log_path = Path(args.log_file) if args.log_file else base_dir / "logs" / "crop_detail_fetch.log"
    out_raw.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")],
    )

    chunks = list(daterange_chunks(start, end, args.chunk_days))
    completed = load_completed(manifest_path) if args.resume else {}
    min_interval = 1.0 / args.rps if args.rps and args.rps > 0 else 0.0
    next_allowed = time.monotonic()

    pairs: list[tuple[str, str]] = []
    seen_pairs = set()
    for region in regions:
        area_id = (
            region.get("region_code")
            or region.get("지역코드")
            or region.get("AREA_ID")
            or region.get("areaId")
            or region.get("CODE")
            or region.get("코드")
            or region.get("지역_아이디")
            or ""
        )
        pa_crop_spe_id = (
            region.get("PA_CROP_SPE_ID")
            or region.get("pa_crop_spe_id")
            or region.get("주산지_작물_특성_아이디")
            or ""
        )
        area_id = str(area_id).strip()
        pa_crop_spe_id = str(pa_crop_spe_id).strip()
        if not area_id or not pa_crop_spe_id:
            continue
        key = (area_id, pa_crop_spe_id)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        pairs.append(key)

    total_tasks = len(pairs) * len(chunks)
    if total_tasks == 0:
        logging.warning("No tasks to run (check crop/region codes)")
        return 0

    task_idx = 0
    t0 = time.time()

    success_pages = 0
    skipped_pages = 0
    error_pages = 0
    rate_limited = False

    if args.resume and completed:
        logging.info("Resume enabled: loaded %d completed pages", len(completed))

    for area_id, pa_crop_spe_id in pairs:
        for chunk_start, chunk_end in chunks:
            task_idx += 1
            start_str = str(chunk_start.date())
            end_str = str(chunk_end.date())
            logging.info(
                "[%d/%d] area=%s cropSpe=%s %s~%s",
                task_idx,
                total_tasks,
                area_id,
                pa_crop_spe_id,
                chunk_start.date(),
                chunk_end.date(),
            )
            page_no = 1
            while True:
                raw_name = f"{area_id}_{pa_crop_spe_id}_{chunk_start.date()}_{chunk_end.date()}_p{page_no}.xml"
                raw_path = out_raw / raw_name
                task_key = (area_id, pa_crop_spe_id, start_str, end_str, page_no)

                if args.resume and task_key in completed:
                    rows, total = completed[task_key]
                    skipped_pages += 1
                    if rows < args.page_size or (page_no * args.page_size) >= total:
                        break
                    page_no += 1
                    continue

                if args.skip_existing and raw_path.exists():
                    try:
                        total, rcdcnt = parse_total_and_rows(raw_path.read_bytes())
                        skipped_pages += 1
                        if rcdcnt < args.page_size or (page_no * args.page_size) >= total:
                            break
                        page_no += 1
                        continue
                    except Exception:
                        pass

                params = build_params(
                    area_id,
                    pa_crop_spe_id,
                    chunk_start,
                    chunk_end,
                    page_no,
                    args.page_size,
                )
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
                        logging.error("rate limit hit on page %d: %s", page_no, safe_error)
                        write_manifest(
                            manifest_path,
                            {
                                "status": "RATE_LIMIT",
                                "area_id": area_id,
                                "pa_crop_spe_id": pa_crop_spe_id,
                                "start": start_str,
                                "end": end_str,
                                "page": page_no,
                                "error": safe_error,
                                "params": sanitize_params(params),
                            },
                        )
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
                                    "area_id": area_id,
                                    "pa_crop_spe_id": pa_crop_spe_id,
                                    "start": start_str,
                                    "end": end_str,
                                    "page": page_no,
                                    "error": safe_error,
                                    "attempts": attempts,
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

                if rate_limited:
                    break
                if xml_bytes is None:
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
                        "area_id": area_id,
                        "pa_crop_spe_id": pa_crop_spe_id,
                        "start": start_str,
                        "end": end_str,
                        "page": page_no,
                        "rows": rcdcnt,
                        "total": total,
                        "raw_file": str(raw_path),
                        "params": sanitize_params(params),
                    },
                )
                if rcdcnt < args.page_size or (page_no * args.page_size) >= total:
                    break
                page_no += 1
            # ETA 로그
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


if __name__ == "__main__":
    sys.exit(main())
