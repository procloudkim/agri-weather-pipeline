# 출처와 변경 이력

이 저장소의 어느 파일이 2025년 당시 작성물이고 어느 것이 2026년 공개 준비에서 손댄 것인지 파일 단위로 밝힙니다.

기준일은 2026-08-16입니다.

## 분류

| 표시 | 뜻 |
|---|---|
| **원본** | 2025년 당시 작성물. 내용 변경 없음 |
| **원본 정정** | 2025년 당시 작성물이되 공개를 위해 특정 부분을 고침. 무엇을 왜 고쳤는지 아래 표에 적음 |
| **공개본 신규** | 2026년에 새로 쓴 것. 당시 존재하지 않았음 |

## 파일별

### 코드

| 파일 | 분류 | 변경 내용 |
|---|---|---|
| `src/kma_crop_detail/collect.py` | 원본 정정 | `sanitize_params`가 인자를 그대로 반환하는 무동작이었음. 실제 마스킹 구현으로 교체. 이 러너는 키를 URL에 미리 붙여 전달하므로 유출 경로는 없었음 |
| `src/kma_crop_detail/parse.py` | 원본 | |
| `src/rda_basic_daily/collect.py` | 원본 정정 | 마스킹 함수가 없어 서비스키가 붙은 URL이 예외 메시지로 manifest와 로그에 기록되고 있었음. `sanitize_params`와 `sanitize_error`를 신설해 `write_manifest`와 로깅 3곳에 배선 |
| `src/rda_basic_daily/parse.py` | 원본 | |
| `src/rda_crop_daily/collect.py` | 원본 정정 | `sanitize_error`의 정규식 이스케이프가 한 단계 더 들어가 치환 결과가 리터럴 `\1***`가 되고 키 뒷부분이 남았음. KMA 러너의 정상 구현으로 교정 |
| `src/rda_crop_daily/parse.py` | 원본 | |
| `src/common/silverize.py` | 원본 | 파일명만 `local_silverize.py`에서 변경 |

코드 정정 3건은 전부 보안 결함 수정입니다. 로직, 파싱 규칙, 정제 규칙은 손대지 않았습니다.

#### 원본 이름과 이 저장소 경로의 대응

이식한 원본 문서 3종(`code_review_notes.md`, `orchestration_handoff.md`, `run_logging_spec.md`)은 2025-12-29 당시 이름을 씁니다. 그 문서들은 기록이므로 고치지 않았습니다. 대응은 아래와 같습니다.

| 원본 이름 | 이 저장소 |
|---|---|
| `crop_detail_run.py` | `src/kma_crop_detail/collect.py` |
| `xml_to_csv_crop_detail.py` | `src/kma_crop_detail/parse.py` |
| `rda_daily_run.py` | `src/rda_basic_daily/collect.py` |
| `xml_to_csv_rda_daily.py` | `src/rda_basic_daily/parse.py` |
| `rda_crop_run.py` | `src/rda_crop_daily/collect.py` |
| `xml_to_csv_rda_crop.py` | `src/rda_crop_daily/parse.py` |
| `local_silverize.py`, `pipeline_v1/local_silverize.py` | `src/common/silverize.py` |
| `dq_meta.json` | `reports/dq_meta_sample.json` (실행 1건의 실물) |
| `dqa/mappings/*.csv` | `data/codebooks/*.csv` |

대응이 없는 이름은 이 저장소에 포함되지 않은 것입니다. 무엇이 왜 빠졌는지는 [`LIMITS.md`](./LIMITS.md)의 미포함 참조 표에 있습니다.

### 데이터와 산출물

| 파일 | 분류 | 비고 |
|---|---|---|
| `data/codebooks/*.csv` 4종 | 원본 | 공공데이터포털 제공 자료의 파생본. 원 권리는 제공기관에 있음 |
| `reports/bronze_to_silver_report.md` | 원본 | 2025-12-26 작성 |
| `reports/dq_meta_sample.json` | 원본 | 2025-12-24 실행(`run_id=20251224_162023`)의 실물 |

### 문서

| 파일 | 분류 | 변경 내용 |
|---|---|---|
| `docs/orchestration_handoff.md` | 원본 정정 | 두 곳. S3 버킷명을 placeholder로 치환. 원천별 백필 시작일 3건을 제거하고 사유 기록 |
| `docs/silver_cleansing_spec.md` | 원본 정정 | 1절의 초안 EDA 집계 3건 제거. 근거 파일이 저장소에 없고 실제 실행값과 어긋남 |
| `docs/run_logging_spec.md` | 원본 | |
| `docs/api_call_workflow.md` | 원본 | |
| `docs/code_review_notes.md` | 원본 | |
| `README.md` | 공개본 신규 | 당시 내부 README를 대체 |
| `docs/PROVENANCE.md` | 공개본 신규 | 이 문서 |
| `docs/LIMITS.md` | 공개본 신규 | |
| `docs/AI_USE_AND_RESPONSIBILITY.md` | 공개본 신규 | |
| `SECURITY.md` | 공개본 신규 | |

### 테스트와 설정

| 파일 | 분류 | 비고 |
|---|---|---|
| `tests/**` | 공개본 신규 | 당시에는 테스트가 없었음. 아래 참조 |
| `.env.example`, `requirements.txt`, `.gitignore`, `.gitattributes` | 공개본 신규 | |
| `.github/workflows/ci.yml` | 공개본 신규 | 당시에는 CI가 없었음 |

## 테스트가 신규인 것에 대해

당시 이 파이프라인에는 자동화된 테스트가 없었습니다. 검증은 실행 후 품질 메타를 눈으로 확인하는 방식이었습니다.

공개본에 테스트를 붙인 이유는 두 가지입니다. 원본 데이터가 없는 상태에서 읽는 사람이 무언가를 직접 돌려볼 수 있어야 하고, 이 저장소의 핵심 주장인 "키 충돌 0이면 손실 없음"이 말이 아니라 코드로 확인 가능해야 하기 때문입니다.

**테스트가 있다는 사실을 당시 개발 품질로 주장하지 않습니다.** 당시에 테스트가 없었다는 것이 이 문서가 기록하는 사실입니다.

## 이 저장소에 없는 것

당시 작업 트리에는 있었으나 인계 패키지에 포함되지 않아 여기 없는 참조는 [LIMITS.md](./LIMITS.md)의 부재 참조 표에 있습니다.
