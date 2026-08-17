# API 수집/파싱 스크립트 각주 리뷰 (2025-12-29)

> 이 문서는 2025-12-29 원본 인계 문서다. 파일명은 그때 기준이며 기록이므로 고치지 않았다. 이 저장소의 경로 대응은 [`PROVENANCE.md`](./PROVENANCE.md)의 대응표에 있다.

## 목적
- 코드 수정 없이, **각 스크립트의 역할/입력/출력/주의사항**을 한글로 각주 형태로 기록.
- 오케스트레이션(Lambda/StepFunctions/DynamoDB 워터마크) 설계 시 참고용.

---
## 01.기상청_작물별 농업주산지 상세날씨 조회서비스
## KMA_CROP_DETAIL
### 1) 수집 스크립트: `crop_detail_run.py`
- 역할: KMA 주산지 작물 상세날씨(getDayStatistics) **일통계** 수집 러너.
- 입력(주요 파라미터): `--start-date`, `--end-date`, `--page-size`, `--chunk-days`, `--rps`, `--region-code-file`, `--output-dir`.
- 필수 환경: `.env`의 `AGRIWEATHER_SERVICE_KEY`(encoded 키만 허용).
- 출력: `raw/*.xml`, `manifest/crop_detail_fetch.jsonl`, `logs/crop_detail_fetch.log`.
- 주의: `serviceKey=`/`&` 포함 키는 오류 처리로 즉시 종료.
- 재시작: `--resume`(manifest SUCCESS/NO_DATA 스킵), `--skip-existing`(raw 파일 존재 시 스킵).
- API 파라미터: `ST_YMD`, `ED_YMD`, `AREA_ID`, `PA_CROP_SPE_ID`.
- 종료 신호: `ALL DONE` 로그, RateLimit 시 return code 2.
- 각주: 함수 구성/의도는 `load_codes`, `daterange_chunks`, `fetch_page`, `parse_total_and_rows`, `build_params`, `load_completed`에 집중됨.[^kma_run]

### 2) 파싱 스크립트: `xml_to_csv_crop_detail.py`
- 역할: RAW XML → Bronze CSV 단일 병합(`crop_detail_all.csv`).
- 입력/출력: `--raw-dir`, `--output-csv`, `--manifest`, `--log-file`.
- 컬럼: 스펙 필드 + `_source_file` 포함.
- 재시작: `--skip-parsed` 시 manifest SUCCESS 파일 스킵.
- 주의: `_source_file`은 Silver에서 제거됨(중복 원인 분석용).
- 각주: XML 파싱은 `parse_xml_file`, 기록은 `write_manifest` 중심.[^kma_parse]

---
## 02.농촌진흥청 국립농업과학원_농업기상 기본 관측데이터 조회
## RDA_BASIC_DAILY
### 3) 수집 스크립트: `rda_daily_run.py`
- 역할: RDA 기본 관측 일별(getWeatherMonDayList3) 월 단위 수집.
- 입력(주요 파라미터): `--start-date`, `--end-date`, `--page-size(권장 40)`, `--rps`, `--stations-file`.
- 필수 환경: `.env`의 `AGRIWEATHER_SERVICE_KEY`(querystring 포함 금지).
- 코드북: `dqa/mappings/rda_station_codes.csv`(`obsr_Spot_Cd`).
- 출력: `raw/*.xml`, `manifest/rda_daily_fetch.jsonl`, `logs/rda_daily_fetch.log`.
- 재시작: manifest 기반 SUCCESS/NO_DATA 스킵, raw 존재 시 스킵.
- 주의: `--no-station-filter` 없으면 `has_data/begin_date` 필터 적용.
- 각주: 스테이션 필터/정렬은 `load_station_codes`에 집중됨.[^rda_daily_run]

### 4) 파싱 스크립트: `xml_to_csv_rda_daily.py`
- 역할: RAW XML → `merged_daily.csv` 변환.
- 입력/출력: `--input-dir`, `--output-csv`.
- 파생 컬럼: `station_code`, `endpoint`, `chunk_start`, `chunk_end`는 **파일명 기반**.
- 주의: 파일명 형식이 깨지면 `chunk_*` 파생이 실패할 수 있음.
- 각주: 파싱 로직은 `parse_xml`에 집중됨.[^rda_daily_parse]

---
## 03.농촌진흥청 국립농업과학원_농업기상 농작물 주산지 농업기상분석정보 조회 서비스
## RDA_CROP_DAILY
### 5) 수집 스크립트: `rda_crop_run.py`
- 역할: RDA 주산지 농업기상 분석 일별(getWeatherPlpdDayList) 수집.
- 입력(주요 파라미터): `--start-date`, `--end-date`, `--page-size(기본 1000)`, `--chunk-days`.
- 코드북: `dqa/mappings/rda_frc_crop_codes.csv`, `dqa/mappings/rda_frc_obsr_codes.csv`.
- 출력: `raw/*.xml`, `manifest/rda_crop_fetch.jsonl`, `logs/rda_crop_fetch.log`.
- 재시작: `--resume`/`--skip-existing` 지원.
- 주의: RateLimit 발생 시 즉시 중단(return 2), RATE_LIMIT은 별도 기록되지 않음.
- 각주: 파라미터 구성은 `build_params`, 재시작은 `load_completed` 중심.[^rda_crop_run]

### 6) 파싱 스크립트: `xml_to_csv_rda_crop.py`
- 역할: RAW XML → `merged_crop_daily.csv` 병합.
- 입력/출력: `--input-dir`, `--output-csv`.
- 컬럼: 스펙 순서 고정(`DEFAULT_COLS`).
- 주의: manifest/로그 없음(표준 출력만).
- 각주: 파싱 로직은 `parse_file`에 집중됨.[^rda_crop_parse]

---

## 오케스트레이션 연결 포인트(요약)
- 워터마크 기준: KMA `ymd`, RDA_BASIC `date`, RDA_CROP `obsr_Datetm`.
- 재시도 기준: manifest의 ERROR만 재처리, SUCCESS/NO_DATA 스킵.
- Silver 규칙: PK/DEC‑001/중복/이상치 규칙은 `33_orchestration_handoff_20251229.md` 참조.

---

## 각주
[^kma_run]: `crop_detail_run.py` 상단 설명과 함수 정의 구역(코드 전체 흐름: load_codes → chunk loop → fetch_page → manifest).
[^kma_parse]: `xml_to_csv_crop_detail.py`의 `parse_xml_file`/`write_manifest`/`main`.
[^rda_daily_run]: `rda_daily_run.py`의 `load_station_codes`/`parse_total`/`main`.
[^rda_daily_parse]: `xml_to_csv_rda_daily.py`의 `parse_xml`.
[^rda_crop_run]: `rda_crop_run.py`의 `build_params`/`load_completed`/`main`.
[^rda_crop_parse]: `xml_to_csv_rda_crop.py`의 `parse_file`/`DEFAULT_COLS`.
