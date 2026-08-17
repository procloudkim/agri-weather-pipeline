# 오케스트레이션 전달용: Raw → Bronze / Bronze → Silver 절차 요약 (2025-12-29)

> 이 문서는 2025-12-29 원본 인계 문서다. 파일명은 그때 기준이며 기록이므로 고치지 않았다. 이 저장소의 경로 대응은 [`PROVENANCE.md`](./PROVENANCE.md)의 대응표에 있다.

## 1) 목적/범위
- 대상: **KMA_CROP_DETAIL, RDA_BASIC_DAILY, RDA_CROP_DAILY** 3개 API.
- 목표: 수집(Raw) → 파싱(Bronze) → 정제/파티션(Silver) 절차를 **자동화/재현** 가능하게 전달.
- 제외: `docs/참고문서/데이터_필드 -main 기상청.csv`는 **main KMA 관측 서비스 문서**로, 본 3개 API와 무관.

---

## 2) Raw → Bronze (수집/파싱)
### 공통 규칙
- serviceKey는 `.env`의 `AGRIWEATHER_SERVICE_KEY` 사용(노출 금지).
- 페이지: **Page_No=1 시작**, **Page_Size=1000** 기본.
- RPS 낮게 유지, 대용량 기간은 **날짜 청크**.
- idempotency: **manifest 기반** (SUCCESS/NO_DATA 스킵, ERROR만 재시도).

### KMA_CROP_DETAIL
- 수집: KMA 주산지 작물 상세날씨 API.
- 수집 스크립트: `crop_detail_run.py`
- 파싱 스크립트: `xml_to_csv_crop_detail.py`
- Raw: `Fin_KMA_CropArea_Weather_20251219/raw/`
- Bronze: `Fin_KMA_CropArea_Weather_20251219/bronze/csv/crop_detail_all.csv`
- 코드북(매칭): `dqa/mappings/kma_region_codes.csv`

### RDA_BASIC_DAILY
- 수집: RDA 기본 관측 일별 API.
- 수집 스크립트: `rda_daily_run.py`
- 파싱 스크립트: `xml_to_csv_rda_daily.py`
- Raw: `Fin_RDA_Basic_Obsr_Daily_20251219/raw/`
- Bronze: `Fin_RDA_Basic_Obsr_Daily_20251219/bronze/csv/merged_daily.csv`
- 코드북(매칭): `dqa/mappings/rda_station_codes.csv`

### RDA_CROP_DAILY
- 수집: RDA 주산지 농업기상 관측 일별 API.
- 수집 스크립트: `rda_crop_run.py`
- 파싱 스크립트: `xml_to_csv_rda_crop.py`
- Raw: `Fin_RDA_CropArea_Daily_20251219/raw/`
- Bronze: `Fin_RDA_CropArea_Daily_20251219/bronze/csv/merged_crop_daily.csv`
- 코드북(매칭): `dqa/mappings/rda_frc_obsr_codes.csv`, `dqa/mappings/rda_frc_crop_codes.csv`

### 코드북 갱신(선택)
- 관측지점 코드북 수집: `rda_obsr_codebook_run.py`
- 관측지점 코드북 파싱: `xml_to_csv_rda_obsr_codebook.py`
- 작물 코드북 수집: `rda_crop_codebook_run.py`
- 작물 코드북 파싱: `xml_to_csv_rda_crop_codebook.py`

### 백필 기간(브론즈 기준)

이 문서의 이전 판에는 원천별 시작일이 적혀 있었으나 **공개본에서 제거했다.**

세 원천의 실제 제공 시작일은 확인 기록마다 값이 달랐다. 같은 데이터셋에 대해 당시 작업 기록, 발표 자료, 이 인계 문서가 각각 다른 날짜를 제시한다. 어느 하나를 고르려면 원천 manifest를 다시 집계해야 하는데 그 근거 파일이 이 저장소에 없다.

값이 셋이면 세 번째 값을 새로 적는 것이 문제를 키운다. 그래서 시작일은 단정하지 않는다. 종료일은 스냅샷 기준 2025-12 중순이다.

---

## 3) Bronze → Silver (정제/파티션)
### 공통 규칙
- 코드 컬럼: **문자열 유지(leading zero 보존)**, trim/upper.
- 결측 표기: `-` → null.
- 중복: **완전 동일 행만 제거**.
- key_conflict = key_dup - row_dup (충돌 여부 판단).
- 이상치(카운트만): 강수/풍속 < 0, 습도 > 100, |온도| > 60.
- 파티션: **year/month/day** (event_date 기준).

### PK 정의
- KMA: `(ymd, areaId, paCropSpeId)`
- RDA_BASIC: `(station_code, date)`  
  - DEC‑001: `station_code = coalesce(station_code, stn_Cd)` 적용 후 null drop
- RDA_CROP: `(obsr_Spot_Code, obsr_Datetm)` (+ no는 타이브레이커, 현재 불필요)

### Silver 출력 경로
- 로컬: `data/silver/<dataset>/year=YYYY/month=MM/day=DD/`
- S3: `s3://<silver-bucket>/<dataset>/year=YYYY/month=MM/day=DD/`

버킷명은 공개본에서 placeholder로 바꿨다. 당시 계정은 종료됐으므로 실제 이름을 남길 이유가 없고, 남기면 계정 식별자가 된다.

---

## 4) DQ 메타(필수)
경로:
- `output_silver/_dq/<dataset>/run_id=YYYYMMDD_HHMMSS/dq_meta.json`

필드(요지):
- `row_count_in`, `row_count_out`
- `key_null_rows`, `key_dup_rows`, `row_dup_rows`, `key_conflict_rows`
- `date_parse_failed`
- `outlier_counts`
- `codebook_unmatched_rows`
- `name_qc_mismatch_counts`
- (RDA_BASIC) `station_code_fixed_count`

---

## 5) 자동화 설계 포인트(Glue/Step Functions)
- Glue Job은 **dataset_id, input, output, run_id**만 바꿔 재사용 가능하게 설계.
- DynamoDB 워터마크 기준:
  - KMA: `ymd`
  - RDA_BASIC: `date`
  - RDA_CROP: `obsr_Datetm`
- 실패 재시도는 **ERROR만**, SUCCESS/NO_DATA는 스킵.
- 로그/메타는 S3에 누적 저장(추적성 확보).

---

## 6) 운영 체크리스트(전달용)
- [ ] `.env`의 `AGRIWEATHER_SERVICE_KEY` 유효 확인
- [ ] 코드북 최신성 확인 (`dqa/mappings/*`)
- [ ] manifest 재시도 정책 확인 (SUCCESS/NO_DATA 스킵)
- [ ] Silver 규칙(DEC‑001 포함) 동일 적용
- [ ] DQ 메타 생성/보관 확인

---

## 7) 참고 문서
- KMA crop detail 스펙: `docs/기상청_작물별_농업주산지_상세날씨_조회서비스_DATAINFO.md`
- RDA 주산지 스펙: `docs/_generated/docx_extract/농촌진흥청 국립농업과학원_농작물 주산지 농업기상분석 정보 제공 오픈 API 조회 서비스_20251224.md`
- 컬럼 사전: `docs/_generated/25_weather_api_column_glossary_20251229.md`
