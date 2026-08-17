# Bronze → Silver Run Report (2025-12-26)

## 1) 범위 및 근거
- 목적: Bronze CSV를 Silver Parquet으로 정제/표준화한 결과를 MECE하게 정리.
- 대상 데이터셋: KMA_CROP_DETAIL, RDA_BASIC_DAILY, RDA_CROP_DAILY.
- 실행 결과 근거: `output_silver/_dq/*/run_id=20251224_162023/dq_meta.json`.
- 보고서 날짜 네이밍: 2025-12-26.

## 2) 공통 처리 규칙(요약)
- 키 정규화: 코드 컬럼 trim/upper, 키 null 행 제거.
- 키 보정(DEC-001): RDA_BASIC `station_code = coalesce(station_code, stn_Cd)`.
- 중복 처리: 완전 동일 row만 drop (key_conflict=0 확인).
- 날짜 파싱: 각 dataset의 date 컬럼을 timestamp로 파싱 → `event_date`, `year/month/day` 파티션 생성.
- 이상치: 규칙 기반 카운트만 기록(드롭 없음).
- 코드북 매칭: ID 조인, 이름 불일치는 QC 플래그만 기록.
- 출력 포맷: Parquet, `year/month/day` 파티션.

## 3) 데이터셋별 성공 현황(핵심 지표)
### KMA_CROP_DETAIL
- 입력/출력 행수: 3,103,904 → 2,126,515
- 키 중복 제거: 977,389 (row_dup=977,389, key_conflict=0)
- 키 null: 0
- 날짜 파싱 실패: 0
- 코드북 미매칭: 0
- 이름 QC 불일치: 0
- 이상치 카운트: 모두 0

### RDA_BASIC_DAILY
- 입력/출력 행수: 864,082 → 864,082
- 키 중복 제거: 0 (key_conflict=0)
- 키 null: 0
- 날짜 파싱 실패: 0
- 코드북 미매칭: 0
- 이름 QC 불일치: 0
- 이상치 카운트: gr_Temp=92, max_Wind=702 (그 외 0)
- DEC-001 보정: station_code_fixed_count=1

### RDA_CROP_DAILY
- 입력/출력 행수: 559,477 → 556,234
- 키 중복 제거: 3,243 (row_dup=3,243, key_conflict=0)
- 키 null: 0
- 날짜 파싱 실패: 0
- 코드북 미매칭: 0
- 이상치 카운트: frfr_Tp=1, frfr_Tp_Top=1,149, frfr_Tp_Lwet=243, udgr_Tp_Top=12, udgr_Tp_Lwet=4 (그 외 0)

## 4) 산출물 경로(요약)
- `output_silver/KMA_CROP_DETAIL/year=YYYY/month=MM/day=DD/`
- `output_silver/RDA_BASIC_DAILY/year=YYYY/month=MM/day=DD/`
- `output_silver/RDA_CROP_DAILY/year=YYYY/month=MM/day=DD/`

## 5) DQ 메타 위치
- `output_silver/_dq/KMA_CROP_DETAIL/run_id=20251224_162023/dq_meta.json`
- `output_silver/_dq/RDA_BASIC_DAILY/run_id=20251224_162023/dq_meta.json`
- `output_silver/_dq/RDA_CROP_DAILY/run_id=20251224_162023/dq_meta.json`

## 6) 메모
- 본 보고서는 2025-12-24 실행 결과를 2025-12-26 네이밍으로 문서화한 것.
- 이전 실패(run_id=20251224_161451)는 파티션 제한/날짜 파싱 이슈로 중단되어 본 보고서에 포함하지 않음.
