# API 호출 워크플로우 & 필수 파라미터 요약 (2025-12-29)

## 1) 목적/대상/근거
- 목적: **사람 + GPT(에이전트)**가 동일 규칙으로 API 호출/파싱을 재현할 수 있도록 정리.
- 대상: KMA_CROP_DETAIL, RDA_BASIC_DAILY, RDA_CROP_DAILY.
- 근거 문서:
  - `docs/01-API-정리_기상청_작물별 농업주산지 상세날씨 조회서비스.txt`
  - `docs/02-API-정리_농촌진흥청 국립농업과학원_농업기상 기본 관측데이터 조회_일별.txt`
  - `docs/03-API-정리_농촌진흥청 국립농업과학원_농업기상 농작물 주산지 농업기상분석정보.txt`

---

## 2) 공통 호출 규칙(프로젝트 표준)
- 인증키: `.env`의 `AGRIWEATHER_SERVICE_KEY` 사용(절대 노출 금지).
- 페이지: **Page_No=1 시작**, **Page_Size=1000 기본**.
- 대용량 기간: **날짜 청크**로 분할, 저RPS 유지.
- idempotency: manifest 기준(SUCCESS/NO_DATA 스킵, ERROR만 재시도).

## 2-1) 백필 최종일자(브론즈 기준)
- KMA_CROP_DETAIL: **2025-12-18**
- RDA_BASIC_DAILY: **2025-12-19**
- RDA_CROP_DAILY: **2025-12-18**

---

## 3) API별 필수 파라미터 (문서 교차검증)

### KMA_CROP_DETAIL (getDayStatistics)
- 요청주소: `http://apis.data.go.kr/1360000/FmlandWthrInfoService/getDayStatistics`
-**요청은 `PA_CROP_SPE_ID`가 기준**이며 **작물명(`paCropName`)은 응답 필드**.

요청변수:
| param | 필수 | 포맷/타입 | 예시 | 제약/비고 | 근거 |
| --- | --- | --- | --- | --- | --- |
| ServiceKey | Y | string | - | 인증키 | 01-API-정리_기상청_작물별 농업주산지 상세날씨 조회서비스.txt |
| pageNo | Y | int | 1 | 페이지 번호 | 01-API-정리_기상청_작물별 농업주산지 상세날씨 조회서비스.txt |
| numOfRows | Y | int | 10 | 한 페이지 결과 수 | 01-API-정리_기상청_작물별 농업주산지 상세날씨 조회서비스.txt |
| dataType | N | XML/JSON | XML | 응답자료형식 | 01-API-정리_기상청_작물별 농업주산지 상세날씨 조회서비스.txt |
| ST_YMD | Y | YYYYMMDD | 20161201 | 일통계 시작일 | 01-API-정리_기상청_작물별 농업주산지 상세날씨 조회서비스.txt |
| ED_YMD | Y | YYYYMMDD | 20161201 | 일통계 종료일 | 01-API-정리_기상청_작물별 농업주산지 상세날씨 조회서비스.txt |
| AREA_ID | Y | string | 4122000000 | 지역 아이디 | 01-API-정리_기상청_작물별 농업주산지 상세날씨 조회서비스.txt |
| PA_CROP_SPE_ID | Y | string | PA130201 | 작물별 특성 아이디 | 01-API-정리_기상청_작물별 농업주산지 상세날씨 조회서비스.txt |

문서 제약/메모:
- 조회 가능한 시작 일자: **20010101**
- `numOfRows` 최대치: **6000(예상)**

---

### RDA_BASIC_DAILY (getWeatherMonDayList3)
- 엔드포인트: `GET /getWeatherMonDayList3`

요청변수:
| param | 필수 | 포맷/타입 | 예시 | 제약/비고 | 근거 |
| --- | --- | --- | --- | --- | --- |
| serviceKey | Y | string | - | 인증키 | 02-API-정리_농촌진흥청 국립농업과학원_농업기상 기본 관측데이터 조회_일별.txt |
| Page_No | Y | int | 1 | 페이지 번호 | 02-API-정리_농촌진흥청 국립농업과학원_농업기상 기본 관측데이터 조회_일별.txt |
| Page_Size | Y | int | 20 | 한 페이지 결과 수 | 02-API-정리_농촌진흥청 국립농업과학원_농업기상 기본 관측데이터 조회_일별.txt |
| search_Year | Y | YYYY | 2018 | 관측년도 | 02-API-정리_농촌진흥청 국립농업과학원_농업기상 기본 관측데이터 조회_일별.txt |
| search_Month | Y | MM | 01 | 관측월 | 02-API-정리_농촌진흥청 국립농업과학원_농업기상 기본 관측데이터 조회_일별.txt |
| obsr_Spot_Nm | N | string | 이천시 장호원 | 관측지점명 | 02-API-정리_농촌진흥청 국립농업기상 기본 관측데이터 조회_일별.txt |
| obsr_Spot_Cd | N | string | 017414F020 | 관측지점코드 | 02-API-정리_농촌진흥청 국립농업기상 기본 관측데이터 조회_일별.txt |

---

### RDA_CROP_DAILY (getWeatherPlpdDayList)
- 엔드포인트: `GET /getWeatherPlpdDayList`
- 문서 제약: **최대 1년** 범위로 조회.

요청변수:
| param | 필수 | 포맷/타입 | 예시 | 제약/비고 | 근거 |
| --- | --- | --- | --- | --- | --- |
| serviceKey | Y | string | - | 인증키 | 03-API-정리_농촌진흥청 국립농업과학원_농업기상 농작물 주산지 농업기상분석정보.txt |
| Page_No | Y | int | 1 | 페이지 번호 | 03-API-정리_농촌진흥청 국립농업과학원_농업기상 농작물 주산지 농업기상분석정보.txt |
| Page_Size | Y | int | 1000 | 한 페이지 결과 수 | 03-API-정리_농촌진흥청 국립농업과학원_농업기상 농작물 주산지 농업기상분석정보.txt |
| obsr_Spot_Code | Y | string | 017421F029 | 관측지점 코드 | 03-API-정리_농촌진흥청 국립농업과학원_농업기상 농작물 주산지 농업기상분석정보.txt |
| begin_Date | Y | YYYYMMDD | 20250101 | 시작일자 | 03-API-정리_농촌진흥청 국립농업과학원_농업기상 농작물 주산지 농업기상분석정보.txt |
| end_Date | Y | YYYYMMDD | 20250131 | 종료일자 | 03-API-정리_농촌진흥청 국립농업과학원_농업기상 농작물 주산지 농업기상분석정보.txt |

사전 조회(관측지점 코드 확보):
- `GET /getWeatherPlpdCropList` (농작물 코드 `frc_Code` 확보)
  - 필수: serviceKey, Page_No, Page_Size
- `GET /getWeatherPlpdObsrCodeList` (관측지점 코드 `obsr_Spot_Code` 확보)
  - 필수: serviceKey, Page_No, Page_Size, frc_Code

---

## 4) 워크플로우(ASCII)

### 공통 흐름
```text
START
→ load .env (AGRIWEATHER_SERVICE_KEY)
→ for each date_chunk:
    page = 1
    do:
        call API (pageNo/Page_No, numOfRows/Page_Size)
        save raw (XML/JSON)
        parse to bronze (csv)
        update manifest
      while page <= total_pages
END
```

### RDA_CROP_DAILY 전용 선행 단계
```text
getWeatherPlpdCropList → frc_Code 목록 확보
getWeatherPlpdObsrCodeList(frc_Code) → obsr_Spot_Code 목록 확보
obsr_Spot_Code별로 getWeatherPlpdDayList 호출 (최대 1년 범위)
```

---

## 5) 요청 검증 체크리스트
- total_Count / rcdcnt / pageNo(Page_No) 일치 확인
- 날짜 포맷(YYYYMMDD, YYYYMM) 검증
- 최대 범위 제한(최대 1년 등) 준수
- 중복/누락 방지: manifest 기록 확인

---

## 6) Agent-ready 요약 (YAML)
```yaml
KMA_CROP_DETAIL:
  endpoint: http://apis.data.go.kr/1360000/FmlandWthrInfoService/getDayStatistics
  required_params: [ServiceKey, pageNo, numOfRows, ST_YMD, ED_YMD, AREA_ID, PA_CROP_SPE_ID]
  optional_params: [dataType]
  constraints:
    - start_date_min: 20010101
    - numOfRows_max: 6000 (documented, 예상)

RDA_BASIC_DAILY:
  endpoint: /getWeatherMonDayList3
  required_params: [serviceKey, Page_No, Page_Size, search_Year, search_Month]
  optional_params: [obsr_Spot_Nm, obsr_Spot_Cd]

RDA_CROP_DAILY:
  endpoint: /getWeatherPlpdDayList
  required_params: [serviceKey, Page_No, Page_Size, obsr_Spot_Code, begin_Date, end_Date]
  constraints:
    - date_range_max: 1 year
  prereq:
    - /getWeatherPlpdCropList (serviceKey, Page_No, Page_Size)
    - /getWeatherPlpdObsrCodeList (serviceKey, Page_No, Page_Size, frc_Code)
```
