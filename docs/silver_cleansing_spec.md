# Fin 기상 데이터 Silver 정제 스펙 (초안)

## 0. 문서 메타
- 생성 시각(로컬): 2025-12-18 20:57:27
- 범위: Fin_RDA 주산지 일별_Fin_output_crop_new / Fin_기상청_output_crop / Fin_농업기상 관측지점 일 단위_Fin_output_daily
- 근거 문서: 아래 4종은 원본 작업 트리에 있었고 이 저장소에는 없다. 상세는 [LIMITS.md](./LIMITS.md)의 부재 참조 표를 본다
  - dqa/governance/cleansing_rules.md (클린징 원칙/키 정의)
  - dqa/runs/20251218_192448/eda/recommendations.md (EDA 요약)
  - docs/_generated/06_fin_user_guide.md (샘플 기반 EDA + 컬럼/시계열 요약)
  - dqa/runs/20251218_201835/duplicates/duplicates_summary.csv (중복 현황 요약)

## 1. 입력 데이터 요약

이 절의 초안 EDA 집계 3건은 **공개본에서 제거했다.**

제거 이유는 정확성이다. 초안 수치는 12-18 시점 샘플 기반 추정이었고, 이후 실제 정제 실행이 남긴 값과 어긋난다. 예를 들어 기상청 계열은 초안이 2,755,883행인데 실제 실행 입력은 3,103,904행이다. 근거 파일(`dqa/runs/...`)이 이 저장소에 없어 어느 쪽이 어떤 범위를 센 것인지 복원할 수 없다.

확정된 값은 실행 리포트에 있다. [reports/bronze_to_silver_report.md](../reports/bronze_to_silver_report.md)와 README의 결과 표를 본다. 그쪽은 입력 행수, 출력 행수, 제거 건수, 키 충돌이 실행 단위로 닫혀 있다.

아래 정제 규칙(2절 이후)은 초안 수치와 무관하게 그대로 유효하다.

## 2. 공통 정제 원칙 (DQA 규칙)
- 원본 보존, 새 출력 루트에만 클린징 적용
  - 근거: dqa/governance/cleansing_rules.md:L3-L7
- 중복 판단 기준은 키 정의에 따름
  - 근거: dqa/governance/cleansing_rules.md:L8
- 공통 순서: 스키마 고정 → 날짜 파싱 → 키 중복 제거 → 결측/이상치 리포트 → 새 루트 저장 후 DQA 재실행
  - 근거: dqa/governance/cleansing_rules.md:L101-L106
- 문서 정의 없는 컬럼은 UNKNOWN 유지
  - 근거: dqa/governance/cleansing_rules.md:L109-L110

## 3. 데이터셋별 Silver 정제 스펙
### 3.1 Fin_RDA 주산지 일별_Fin_output_crop_new (join-day)
- 입력 위치: Fin_RDA 주산지 일별_Fin_output_crop_new/bronze/csv/Agri-day-main-local-join-day/*.csv
  - 근거: docs/_generated/06_fin_user_guide.md:L11
- 키(중복 기준): obsr_Spot_Code + obsr_Datetm
  - 근거: dqa/governance/cleansing_rules.md:L23-L25
- 중복 처리: 키 동일 시 비어 있지 않은 컬럼 수가 많은 행 우선, 동률이면 먼저 등장한 행 유지
  - 근거: dqa/governance/cleansing_rules.md:L27-L29
- 표준화: obsr_Datetm 날짜 파싱(YYYY-MM-DD 또는 YYYY-MM-DD HH:MM:SS)
  - 근거: dqa/governance/cleansing_rules.md:L31-L33
- NULL 정규화(권고): 샘플값에서 `-`가 결측으로 등장 → NULL로 치환
  - 근거: docs/_generated/06_fin_user_guide.md:L57-L65
- 스키마 유지: 컬럼명/순서 변경 없음
  - 근거: dqa/governance/cleansing_rules.md:L31-L33, L102

### 3.2 Fin_기상청_output_crop (스키마 5종 분리)
- 스키마 드리프트 5종 감지됨 → 스키마별 별도 Silver 테이블 권장
  - 근거: dqa/runs/20251218_192448/eda/recommendations.md:L11

#### 3.2.1 frc_day_*.csv (주산지 일별)
- 3.1과 동일한 키/중복/표준화 적용
  - 근거: dqa/governance/cleansing_rules.md:L37-L38

#### 3.2.2 frc_obsr_probe*.csv
- 키: obsr_Spot_Code
  - 근거: dqa/governance/cleansing_rules.md:L43-L45
- 중복 처리: attempts 큰 행 우선, 동률이면 마지막 행 유지
  - 근거: dqa/governance/cleansing_rules.md:L46-L48

#### 3.2.3 crop_list.csv / frc_crop_info.csv
- 잠정 키: prdlst_Code + frc_Code
  - 근거: dqa/governance/cleansing_rules.md:L53-L55
- 중복 처리: prdlst_Code_Nm 또는 frc_Nm 비어 있지 않은 행 우선, 동률이면 첫 행
  - 근거: dqa/governance/cleansing_rules.md:L57-L59

#### 3.2.4 frc_obsr_codes.csv
- 잠정 키: frc_Code + obsr_Spot_Code
  - 근거: dqa/governance/cleansing_rules.md:L64-L66
- 중복 처리: do_Nm/spot_Nm 결측 적은 행 우선, 동률이면 첫 행
  - 근거: dqa/governance/cleansing_rules.md:L68-L70

#### 3.2.5 KMA-crop-detail/crop_detail_all.csv
- 키: ymd + areaId + paCropSpeId (대체 키: ymd + areaId + paCropName)
  - 근거: dqa/governance/cleansing_rules.md:L75-L77
- 중복 처리: 결측이 적은 행 우선, 동률이면 첫 행
  - 근거: dqa/governance/cleansing_rules.md:L79-L81
- 날짜 파싱: ymd는 `YYYY-MM-DD HH:MM:SS` 형식 (일 단위, 00:00:00 고정)
  - 근거: docs/_generated/06_fin_user_guide.md:L101

### 3.3 Fin_농업기상 관측지점 일 단위_Fin_output_daily (merged_daily.csv)
- 입력 위치: Fin_농업기상 관측지점 일 단위_Fin_output_daily/bronze/csv/merged_daily.csv
  - 근거: docs/_generated/06_fin_user_guide.md:L14
- 키: station_code + date + endpoint (date 없으면 obsr_Datetm 사용)
  - 근거: dqa/governance/cleansing_rules.md:L87-L89
- 중복 처리: 비어 있지 않은 컬럼 수 많은 행 우선 → chunk_end 최신 → 첫 행
  - 근거: dqa/governance/cleansing_rules.md:L91-L94
- 표준화: date/obsr_Datetm/chunk_start/chunk_end 날짜 파싱
  - 근거: dqa/governance/cleansing_rules.md:L96-L98
- 품질 체크: station_code vs obsr_Spot_Code 불일치 기록
  - 근거: dqa/governance/cleansing_rules.md:L96-L98

## 4. Silver 타입/값 정규화 (권고)
- 문자열 코드 유지: obsr_Spot_Code, station_code, areaId, paCropSpeId 등은 문자열 유지
  - 근거: 코드 컬럼은 샘플값이 문자열 형태로 제공됨
- 숫자 컬럼 파싱: 숫자형으로 보이는 값은 숫자형으로 변환, 파싱 실패 또는 `-`는 NULL 처리
  - 근거: 샘플에서 `-`가 결측으로 관측됨 (docs/_generated/06_fin_user_guide.md:L57-L65)
- 날짜 컬럼 파싱: obsr_Datetm, ymd, date, chunk_start, chunk_end는 날짜/시각 컬럼으로 변환
  - 근거: dqa/governance/cleansing_rules.md:L31-L33, L96-L98; docs/_generated/06_fin_user_guide.md:L101

## 5. Silver 품질 검증 체크리스트 (근거 + 권고)
- 중복 기준 검증: Fin_기상청_output_crop에서 중복 키가 다수 존재함
  - 근거: dqa/runs/20251218_201835/duplicates/duplicates_summary.csv:L3 (dup_keys=71093, dup_rows=75025)
- 키 결측 검증: Fin_기상청_output_crop에서 key_missing=24 관측
  - 근거: dqa/runs/20251218_201835/duplicates/duplicates_summary.csv:L3
- 정제 후 기준(권고): key_missing=0, dup_keys=0, dup_rows=0을 목표
- 날짜 파싱 실패(권고): 0 또는 원인 로그와 함께 리포트

## 6. 미정/협의 항목 (TBD)
- Silver 출력 경로(S3 버킷/프리픽스)
- 경매 데이터와의 조인 키(지역/상품 매핑 규칙)
- Gold 테이블 스키마(대시보드/ML 분리 기준)