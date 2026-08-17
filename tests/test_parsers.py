"""파서 3종 검증. 합성 fixture만 사용하며 네트워크에 접근하지 않는다.

가장 중요한 것은 `test_field_drift_is_silent` 다. 이 파이프라인 설계의
출발점이 된 실패를 코드로 고정해 둔 것이다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from src.kma_crop_detail.parse import FIELDS as KMA_FIELDS
from src.kma_crop_detail.parse import parse_xml_file
from src.rda_basic_daily.parse import parse_xml as parse_rda_basic
from src.rda_crop_daily.parse import parse_file as parse_rda_crop

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# --------------------------------------------------------------------------
# 기상청 작물별 상세날씨
# --------------------------------------------------------------------------


def test_kma_parses_all_declared_fields():
    rows = parse_xml_file(FIXTURES / "kma_crop_detail_ok.xml")

    assert len(rows) == 2
    assert set(rows[0]) == set(KMA_FIELDS)
    assert rows[0]["ymd"] == "2025-12-01"
    assert rows[0]["areaId"] == "4123"
    assert rows[0]["dayAvgTa"] == "3.4"
    assert rows[0]["wmCd"] == "W02"


def test_kma_keeps_leading_zero_in_code_column():
    """`paCropSpeId` 를 숫자로 다루면 0007 이 7 이 되어 코드북 매칭이 실패한다."""
    rows = parse_xml_file(FIXTURES / "kma_crop_detail_ok.xml")

    assert rows[0]["paCropSpeId"] == "0007"


def test_kma_preserves_hyphen_marker_for_later_normalization():
    """파서는 하이픈을 그대로 넘긴다. 결측 정규화는 Silver 단계의 책임이다."""
    rows = parse_xml_file(FIXTURES / "kma_crop_detail_ok.xml")

    assert rows[1]["dayAvgTa"] == "-"


def test_kma_records_source_file_for_lineage():
    rows = parse_xml_file(FIXTURES / "kma_crop_detail_ok.xml")

    assert all(r["_source_file"] == "kma_crop_detail_ok.xml" for r in rows)


def test_field_drift_is_silent():
    """명세와 실제 응답의 필드명이 다르면 **예외 없이 빈 값**이 된다.

    이것이 이 프로젝트에서 실제로 겪은 실패다. 파서는 정상 종료하고 로그도
    깨끗한데 해당 컬럼만 전부 비었다. 값 분포를 직접 확인하기 전까지는
    드러나지 않는다.

    파서를 고쳐서 이 상황을 예외로 만들지 않았다. 원천 스키마는 실제로
    바뀌고, 예외로 처리하면 수집 자체가 멈춘다. 대신 이 성질을 테스트로
    고정해 두고, 값이 비었는지는 품질 메타가 판정하게 했다.
    """
    rows = parse_xml_file(FIXTURES / "kma_crop_detail_field_drift.xml")

    assert len(rows) == 1
    # 다른 필드는 정상이다. 그래서 더 눈에 띄지 않는다.
    assert rows[0]["dayAvgTa"] == "1.1"
    # 명세 기준 이름으로 조회하면 비어 있다.
    assert rows[0]["wmCount"] == ""
    assert rows[0]["wmCd"] == ""


# --------------------------------------------------------------------------
# 농촌진흥청 농업기상 기본 관측 일자료
# --------------------------------------------------------------------------


def _stage(tmp_path: Path, fixture: str, name: str) -> Path:
    """파일명에서 관측소와 연월을 읽는 파서라 이름을 맞춰 복사한다."""
    target = tmp_path / name
    shutil.copy(FIXTURES / fixture, target)
    return target


def test_rda_basic_parses_item(tmp_path):
    path = _stage(tmp_path, "rda_basic_daily_ok.xml", "712851A001_2025-12.xml")

    rows = parse_rda_basic(path)

    assert len(rows) == 1
    assert rows[0]["station_code"] == "712851A001"
    assert rows[0]["date"] == "2025-12-01"
    assert rows[0]["endpoint"] == "getWeatherMonDayList3"


def test_rda_basic_derives_chunk_window_from_filename(tmp_path):
    """수집 단위를 파일명에서 복원한다. manifest 없이도 범위를 알 수 있어야 한다."""
    path = _stage(tmp_path, "rda_basic_daily_ok.xml", "712851A001_2025-02.xml")

    rows = parse_rda_basic(path)

    assert rows[0]["chunk_start"] == "2025-02-01"
    assert rows[0]["chunk_end"] == "2025-02-28", "윤년이 아닌 2월은 28일이다"


def test_rda_basic_handles_leap_february(tmp_path):
    path = _stage(tmp_path, "rda_basic_daily_ok.xml", "712851A001_2024-02.xml")

    rows = parse_rda_basic(path)

    assert rows[0]["chunk_end"] == "2024-02-29"


def test_rda_basic_empty_response_yields_no_rows(tmp_path):
    """HTTP 200 이지만 결과가 없는 응답. 예외가 아니라 0행이어야 한다."""
    path = _stage(tmp_path, "rda_basic_daily_no_data.xml", "712851A001_2025-12.xml")

    rows = parse_rda_basic(path)

    assert rows == []


# --------------------------------------------------------------------------
# 농촌진흥청 농작물 주산지 농업기상
# --------------------------------------------------------------------------


def test_rda_crop_extracts_requested_columns_in_order():
    cols = ["obsr_Spot_Code", "obsr_Datetm", "temp", "frfr_Tp"]

    rows = parse_rda_crop(FIXTURES / "rda_crop_daily_ok.xml", cols)

    assert rows[0] == ["S001", "2025-12-01", "3.4", "0.5"]


def test_rda_crop_fills_missing_column_with_empty_string():
    """두 번째 item 에는 frfr_Tp 가 없다. 길이가 어긋나면 CSV 열이 밀린다."""
    cols = ["obsr_Spot_Code", "obsr_Datetm", "temp", "frfr_Tp"]

    rows = parse_rda_crop(FIXTURES / "rda_crop_daily_ok.xml", cols)

    assert len(rows) == 2
    assert rows[1] == ["S001", "2025-12-02", "2.2", ""]
    assert all(len(r) == len(cols) for r in rows)


@pytest.mark.parametrize("cols", [[], ["nonexistent_column"]])
def test_rda_crop_tolerates_unknown_columns(cols):
    rows = parse_rda_crop(FIXTURES / "rda_crop_daily_ok.xml", cols)

    assert len(rows) == 2
    assert all(len(r) == len(cols) for r in rows)
