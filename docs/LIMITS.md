# 증거와 한계

이 저장소가 무엇을 보여주고 무엇을 보여주지 못하는지 밝힙니다.

## 확인할 수 있는 것

| 항목 | 확인 방법 |
|---|---|
| 수집 상태를 셋으로 나눈 판정 구조 | `src/*/collect.py`의 manifest 기록부 |
| 재시작 가능성 | `--resume`, `--skip-existing` 인자와 manifest 조회 로직 |
| 요청 간격 제어와 백오프 | 각 러너의 `--rps`, `--max-retries`, `--retry-backoff` |
| 정제 규칙과 키 정의 | `docs/silver_cleansing_spec.md`, `src/common/silverize.py` |
| 품질 메타 필드 구성 | `docs/run_logging_spec.md`, `reports/dq_meta_sample.json` |
| 키 충돌 불변식 | `tests/test_dq_invariant.py`를 직접 실행 |
| 서비스키 마스킹 | `tests/test_redaction.py`를 직접 실행 |
| 행 수와 중복 제거 결과 | `reports/bronze_to_silver_report.md` |

## 확인할 수 없는 것

| 항목 | 이유 |
|---|---|
| 전체 백필 재실행 | 10년 이상 구간의 실제 수집은 서비스키와 상당한 시간이 필요합니다 |
| 클라우드 증분 파이프라인 | Lambda, Glue, Step Functions, EventBridge 구성은 교육 계정 종료로 접근 불가 |
| Gold 계층과 대시보드 | 같은 이유. 화면은 팀 발표 자료에 있으나 계정 식별자 때문에 공개하지 않음 |
| 원천별 제공 시작일 | 당시 기록마다 값이 달라 원천 manifest 재집계가 필요한데 근거 파일이 없음 |
| 개인 커밋 이력 | 당시 작업이 git으로 관리되지 않았음. 인계 패키지가 압축본으로 전달됨 |
| 비용 절감액 | 원인은 찾았으나 개선 후 재측정을 하지 못하고 과정이 종료됨 |

## 이 저장소에 없는 참조

인계 패키지에 포함되지 않아 문서가 가리키지만 여기 없는 파일입니다. 문서를 읽다가 링크가 끊긴 것처럼 보이면 아래 목록을 확인하십시오.

| 참조 | 어디서 가리키는가 | 무엇이었는가 |
|---|---|---|
| `dqa/governance/cleansing_rules.md` | `silver_cleansing_spec.md` | 클린징 원칙과 키 정의 원본 |
| `dqa/runs/<run_id>/eda/recommendations.md` | `silver_cleansing_spec.md` | EDA 요약. 초안 수치의 근거 |
| `dqa/runs/<run_id>/duplicates/duplicates_summary.csv` | `silver_cleansing_spec.md` | 중복 현황 요약 |
| `docs/_generated/06_fin_user_guide.md` | `silver_cleansing_spec.md` | 샘플 기반 EDA와 컬럼 요약 |
| `docs/_generated/25_weather_api_column_glossary_20251229.md` | `api_call_workflow.md` | 컬럼 용어집 |
| `pipeline_v1/run_local_backfill.ps1` | `orchestration_handoff.md` | 백필 배치 실행 스크립트 |
| `rda_obsr_codebook_run.py`, `xml_to_csv_rda_obsr_codebook.py` | `orchestration_handoff.md` | 관측지점 코드북 갱신 |
| `rda_crop_codebook_run.py`, `xml_to_csv_rda_crop_codebook.py` | `orchestration_handoff.md` | 작물 코드북 갱신 |

`run_local_backfill.ps1`이 없어 배치 일괄 실행은 재현되지 않습니다. 대신 러너를 직접 호출하는 예제를 README에 두었습니다.

코드북 갱신 스크립트가 없어도 코드북 CSV 4종은 `data/codebooks/`에 결과물로 있습니다.

## 주장하지 않는 것

- 프로덕션 운영, SLA, 장애 대응 경험
- 실사용자와 트래픽
- 성능 우위나 처리 속도
- 비용 절감액
- 팀 전체 플랫폼의 소유
- 이 저장소의 테스트를 당시 개발 품질의 증거로 사용하는 것. [PROVENANCE.md](./PROVENANCE.md)를 참조하십시오

## 수치 사용 기준

산출 근거 파일이 존재하고, 계산 과정을 설명할 수 있으며, 담당 범위 안에서 나온 수치만 사용합니다. 세 조건 중 하나라도 만족하지 않으면 서술로 대체합니다.

이 기준 때문에 제외한 것이 있습니다. 팀 전체가 다룬 경매 원천의 행 수는 발표 자료 한 곳에만 있고 재집계 근거가 없어 이 저장소에서 언급하지 않습니다. 초안 EDA 집계 3건도 같은 이유로 제거했습니다.
