"""품질 메타 불변식 검증.

이 저장소의 핵심 주장은 "키 충돌이 0이면 중복 제거가 안전했다"는 것이다.
그 주장이 성립하는 근거는 다음 한 줄이다.

    키 충돌 = 키 중복 − 행 중복

읽는 사람이 원본 데이터 없이도 이 성질을 직접 확인할 수 있어야 한다고 보고,
실제 `process_dataset` 을 소형 합성 CSV로 돌려서 검증한다. 재구현이 아니라
운영 코드를 그대로 호출한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.common.silverize import DatasetSpec, process_dataset

RUN_ID = "19700101_000000"

BASE_SPEC = dict(
    dataset_id="TEST_DS",
    output_subdir="TEST_DS",
    pk_cols=["ymd", "areaId", "paCropSpeId"],
    date_col="ymd",
    date_format="%Y-%m-%d %H:%M:%S",
    code_cols=["areaId", "paCropSpeId"],
    name_cols=[],
    numeric_cols=["dayAvgTa"],
    drop_cols=[],
    outlier_rules={},
    codebook=None,
    coalesce_map=None,
)

HEADER = "ymd,areaId,paCropSpeId,dayAvgTa\n"


def _write_csv(tmp_path: Path, rows: list[str]) -> Path:
    path = tmp_path / "bronze.csv"
    path.write_text(HEADER + "".join(r + "\n" for r in rows), encoding="utf-8")
    return path


def _run(tmp_path: Path, rows: list[str]) -> tuple[dict, pd.DataFrame]:
    csv_path = _write_csv(tmp_path, rows)
    out_root = tmp_path / "silver"
    spec = DatasetSpec(input_csv=str(csv_path), **BASE_SPEC)

    meta = process_dataset(spec, out_root, RUN_ID)

    written = pd.read_parquet(out_root / "TEST_DS")
    return meta, written


def test_invariant_holds_when_only_exact_duplicates(tmp_path):
    """완전 동일 행만 겹치면 키 충돌이 0이고 제거된 만큼만 줄어든다.

    실제 파이프라인에서 세 원천 모두 이 상태였다. 300만 행에서 97만 행을
    지우고도 손실이 없다고 말할 수 있는 근거가 이것이다.
    """
    rows = [
        "2025-12-01 00:00:00,A01,C1,10.0",
        "2025-12-01 00:00:00,A01,C1,10.0",  # 1번과 완전 동일
        "2025-12-02 00:00:00,A02,C2,11.0",
        "2025-12-03 00:00:00,A03,C3,12.0",
    ]

    meta, _ = _run(tmp_path, rows)

    assert meta["row_count_in"] == 4
    assert meta["key_dup_rows"] == 1
    assert meta["row_dup_rows"] == 1
    assert meta["key_conflict_rows"] == 0
    assert meta["row_count_out"] == meta["row_count_in"] - meta["row_dup_rows"]


def test_conflicting_rows_are_not_dropped(tmp_path):
    """키는 같고 값이 다르면 충돌로 세고 **지우지 않는다**.

    이것이 안전 성질이다. 키 중복과 행 중복을 뭉뚱그려 키 기준으로 지웠다면
    아래 99.0 행이 조용히 사라졌을 것이고 로그에는 아무 표시도 남지 않는다.
    """
    rows = [
        "2025-12-01 00:00:00,A01,C1,10.0",
        "2025-12-01 00:00:00,A01,C1,10.0",  # 완전 동일
        "2025-12-02 00:00:00,A02,C2,11.0",
        "2025-12-02 00:00:00,A02,C2,99.0",  # 키 동일, 값 다름
        "2025-12-03 00:00:00,A03,C3,12.0",
    ]

    meta, written = _run(tmp_path, rows)

    assert meta["key_dup_rows"] == 2
    assert meta["row_dup_rows"] == 1
    assert meta["key_conflict_rows"] == 1
    assert meta["row_count_out"] == 4

    survivors = sorted(written.loc[written["areaId"] == "A02", "dayAvgTa"].tolist())
    assert survivors == [11.0, 99.0], "충돌하는 두 값이 모두 남아야 한다"


@pytest.mark.parametrize(
    "rows",
    [
        pytest.param([], id="empty"),
        pytest.param(["2025-12-01 00:00:00,A01,C1,10.0"], id="single"),
        pytest.param(
            [
                "2025-12-01 00:00:00,A01,C1,10.0",
                "2025-12-01 00:00:00,A01,C1,10.0",
                "2025-12-01 00:00:00,A01,C1,20.0",
            ],
            id="mixed",
        ),
    ],
)
def test_invariant_equation_always_holds(tmp_path, rows):
    """어떤 입력에서도 키 충돌 = 키 중복 − 행 중복 이 성립한다."""
    meta, _ = _run(tmp_path, rows)

    assert meta["key_conflict_rows"] == max(
        meta["key_dup_rows"] - meta["row_dup_rows"], 0
    )
    assert meta["row_count_out"] == meta["row_count_in"] - meta["row_dup_rows"]


def test_missing_key_rows_are_counted_and_removed(tmp_path):
    """식별자가 없는 행은 세고 제거한다. 조용히 통과시키지 않는다."""
    rows = [
        "2025-12-01 00:00:00,A01,C1,10.0",
        "2025-12-02 00:00:00,,C2,11.0",  # areaId 없음
    ]

    meta, _ = _run(tmp_path, rows)

    assert meta["key_null_rows"] == 1
    assert meta["row_count_out"] == 1


def test_hyphen_is_normalized_to_missing(tmp_path):
    """원천이 결측을 하이픈으로 표기한다. 문자열로 남으면 숫자 컬럼을 오염시킨다."""
    rows = [
        "2025-12-01 00:00:00,A01,C1,-",
        "2025-12-02 00:00:00,A02,C2,11.0",
    ]

    _, written = _run(tmp_path, rows)

    assert written["dayAvgTa"].isna().sum() == 1
    assert pd.api.types.is_numeric_dtype(written["dayAvgTa"])


def test_code_columns_keep_leading_zeros(tmp_path):
    """코드 컬럼을 숫자로 바꾸면 선행 0이 사라져 코드북 매칭이 조용히 실패한다."""
    rows = ["2025-12-01 00:00:00,0042,0007,10.0"]

    _, written = _run(tmp_path, rows)

    assert written["areaId"].iloc[0] == "0042"
    assert written["paCropSpeId"].iloc[0] == "0007"


def test_dq_meta_file_is_written_per_run(tmp_path):
    """품질 메타는 실행 단위로 파일에 남는다. 메모리에만 있으면 사후 검증이 안 된다."""
    csv_path = _write_csv(tmp_path, ["2025-12-01 00:00:00,A01,C1,10.0"])
    out_root = tmp_path / "silver"
    spec = DatasetSpec(input_csv=str(csv_path), **BASE_SPEC)

    process_dataset(spec, out_root, RUN_ID)

    dq_path = out_root / "_dq" / "TEST_DS" / f"run_id={RUN_ID}" / "dq_meta.json"
    assert dq_path.exists()

    saved = json.loads(dq_path.read_text(encoding="utf-8"))
    for field in (
        "row_count_in",
        "row_count_out",
        "key_null_rows",
        "key_dup_rows",
        "row_dup_rows",
        "key_conflict_rows",
        "date_parse_failed",
        "outlier_counts",
        "codebook_unmatched_rows",
    ):
        assert field in saved, field
