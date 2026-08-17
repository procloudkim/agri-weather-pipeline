#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd


RUN_ID_FORMAT = "%Y%m%d_%H%M%S"
MISSING_MARKERS = ("-", "—", "–")


@dataclass(frozen=True)
class CodebookSpec:
    path: str
    join_map: dict[str, str]
    name_map: dict[str, str] | None = None


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    input_csv: str
    output_subdir: str
    pk_cols: list[str]
    date_col: str
    date_format: str | None
    code_cols: list[str]
    name_cols: list[str]
    numeric_cols: list[str]
    drop_cols: list[str]
    outlier_rules: dict[str, dict[str, float]]
    codebook: CodebookSpec | None = None
    coalesce_map: dict[str, str] | None = None


DATASETS: dict[str, DatasetSpec] = {
    "KMA_CROP_DETAIL": DatasetSpec(
        dataset_id="KMA_CROP_DETAIL",
        input_csv="Fin_KMA_CropArea_Weather_20251219/bronze/csv/crop_detail_all.csv",
        output_subdir="KMA_CROP_DETAIL",
        pk_cols=["ymd", "areaId", "paCropSpeId"],
        date_col="ymd",
        date_format="%Y-%m-%d %H:%M:%S",
        code_cols=["areaId", "paCropSpeId"],
        name_cols=["areaName", "paCropName", "paCropSpeName"],
        numeric_cols=[
            "dayAvgTa",
            "dayMaxTa",
            "dayMinTa",
            "dayAvgRhm",
            "dayMinRhm",
            "daySumRn",
            "dayAvgWs",
            "daySumSs",
        ],
        drop_cols=["_source_file"],
        outlier_rules={
            "dayAvgTa": {"abs_max": 60},
            "dayMaxTa": {"abs_max": 60},
            "dayMinTa": {"abs_max": 60},
            "dayAvgRhm": {"max": 100},
            "dayMinRhm": {"max": 100},
            "daySumRn": {"min": 0},
            "dayAvgWs": {"min": 0},
        },
        codebook=CodebookSpec(
            path="dqa/mappings/kma_region_codes.csv",
            join_map={
                "areaId": "지역_아이디",
                "paCropSpeId": "주산지_작물_특성_아이디",
            },
            name_map={
                "areaName": "지역_이름",
                "paCropName": "주산지_작물명",
                "paCropSpeName": "주산지_작물_특성_이름",
            },
        ),
    ),
    "RDA_BASIC_DAILY": DatasetSpec(
        dataset_id="RDA_BASIC_DAILY",
        input_csv="Fin_RDA_Basic_Obsr_Daily_20251219/bronze/csv/merged_daily.csv",
        output_subdir="RDA_BASIC_DAILY",
        pk_cols=["station_code", "date"],
        date_col="date",
        date_format=None,
        code_cols=["station_code", "stn_Cd"],
        name_cols=["stn_Name"],
        numeric_cols=[
            "temp",
            "hghst_Artmp",
            "lowst_Artmp",
            "hum",
            "wind",
            "max_Wind",
            "rn",
            "srqty",
            "sun_Time",
            "condens_Time",
            "widdir",
            "gr_Temp",
            "soil_Temp",
            "soil_Wt",
        ],
        drop_cols=["endpoint", "chunk_start", "chunk_end", "no"],
        outlier_rules={
            "temp": {"abs_max": 60},
            "hghst_Artmp": {"abs_max": 60},
            "lowst_Artmp": {"abs_max": 60},
            "gr_Temp": {"abs_max": 60},
            "soil_Temp": {"abs_max": 60},
            "hum": {"max": 100},
            "rn": {"min": 0},
            "wind": {"min": 0},
            "max_Wind": {"min": 0},
        },
        codebook=CodebookSpec(
            path="dqa/mappings/rda_station_codes.csv",
            join_map={"station_code": "obsr_Spot_Cd"},
            name_map={"stn_Name": "obsr_Spot_Nm"},
        ),
        coalesce_map={"station_code": "stn_Cd"},
    ),
    "RDA_CROP_DAILY": DatasetSpec(
        dataset_id="RDA_CROP_DAILY",
        input_csv="Fin_RDA_CropArea_Daily_20251219/bronze/csv/merged_crop_daily.csv",
        output_subdir="RDA_CROP_DAILY",
        pk_cols=["obsr_Spot_Code", "obsr_Datetm"],
        date_col="obsr_Datetm",
        date_format=None,
        code_cols=["obsr_Spot_Code"],
        name_cols=[],
        numeric_cols=[
            "tmprt",
            "tmprt_Top",
            "tmprt_Lwet",
            "afp",
            "sunshn_Time",
            "solrad_Qy",
            "arvlty",
            "frfr_Tp",
            "frfr_Tp_Top",
            "frfr_Tp_Lwet",
            "udgr_Tp",
            "udgr_Tp_Top",
            "udgr_Tp_Lwet",
            "soil_Mitr_Cmst",
            "soil_Mitr_Cmst_Top",
            "soil_Mitr_Cmst_Lwet",
        ],
        drop_cols=["no"],
        outlier_rules={
            "tmprt": {"abs_max": 60},
            "tmprt_Top": {"abs_max": 60},
            "tmprt_Lwet": {"abs_max": 60},
            "frfr_Tp": {"abs_max": 60},
            "frfr_Tp_Top": {"abs_max": 60},
            "frfr_Tp_Lwet": {"abs_max": 60},
            "udgr_Tp": {"abs_max": 60},
            "udgr_Tp_Top": {"abs_max": 60},
            "udgr_Tp_Lwet": {"abs_max": 60},
            "afp": {"min": 0},
        },
        codebook=CodebookSpec(
            path="dqa/mappings/rda_frc_obsr_codes.csv",
            join_map={"obsr_Spot_Code": "obsr_Spot_Code"},
            name_map={},
        ),
    ),
}


def _read_csv_with_fallback(path: Path, **kwargs) -> pd.DataFrame:
    encodings = ("utf-8-sig", "utf-8", "cp949", "euc-kr", "latin-1")
    last_exc: Exception | None = None
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except Exception as exc:
            last_exc = exc
    if last_exc:
        raise last_exc
    return pd.read_csv(path, **kwargs)


def _normalize_code(series: pd.Series) -> pd.Series:
    s = series.astype("string")
    s = s.str.strip().str.upper()
    s = s.replace(list(MISSING_MARKERS), pd.NA)
    s = s.replace("", pd.NA)
    return s


def _normalize_name(series: pd.Series) -> pd.Series:
    s = series.astype("string")
    s = s.str.strip()
    s = s.replace(list(MISSING_MARKERS), pd.NA)
    s = s.replace("", pd.NA)
    return s


def _parse_datetime(series: pd.Series, date_format: str | None) -> pd.Series:
    s = series.astype("string").str.strip()
    if date_format:
        parsed = pd.to_datetime(s, format=date_format, errors="coerce")
        if parsed.isna().all():
            parsed = pd.to_datetime(s, errors="coerce")
        return parsed
    return pd.to_datetime(s, errors="coerce")


def _apply_outlier_rules(df: pd.DataFrame, rules: dict[str, dict[str, float]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for col, rule in rules.items():
        if col not in df.columns:
            counts[col] = 0
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        mask = pd.Series(False, index=numeric.index)
        if "abs_max" in rule:
            mask = mask | (numeric.abs() > rule["abs_max"])
        if "min" in rule:
            mask = mask | (numeric < rule["min"])
        if "max" in rule:
            mask = mask | (numeric > rule["max"])
        counts[col] = int(mask.sum())
    return counts


def _log(message: str, dataset_id: str | None = None) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    prefix = f"[{ts}]"
    if dataset_id:
        prefix = f"{prefix} [{dataset_id}]"
    print(f"{prefix} {message}", flush=True)


def _load_codebook(spec: CodebookSpec) -> pd.DataFrame:
    path = Path(spec.path)
    if not path.exists():
        return pd.DataFrame()
    return _read_csv_with_fallback(path, dtype=str)


def _apply_codebook(df: pd.DataFrame, spec: CodebookSpec) -> tuple[pd.DataFrame, dict[str, int], int]:
    codebook = _load_codebook(spec)
    if codebook.empty:
        df["codebook_미매칭"] = False
        return df, {}, 0

    cb = codebook.copy()
    for left_col, right_col in spec.join_map.items():
        if right_col not in cb.columns:
            df["codebook_미매칭"] = False
            return df, {}, 0
        cb[left_col] = _normalize_code(cb[right_col])
    cb["cb_match"] = 1

    name_map = spec.name_map or {}
    for left_name, right_name in name_map.items():
        if right_name in cb.columns:
            cb[f"cb_{left_name}"] = _normalize_name(cb[right_name])

    keep_cols = list(spec.join_map.keys()) + ["cb_match"]
    keep_cols += [f"cb_{left_name}" for left_name in name_map.keys() if f"cb_{left_name}" in cb.columns]
    cb = cb[keep_cols].drop_duplicates(subset=list(spec.join_map.keys()))

    df = df.merge(cb, on=list(spec.join_map.keys()), how="left")
    df["codebook_미매칭"] = df["cb_match"].isna()

    name_qc_counts: dict[str, int] = {}
    for left_name in name_map.keys():
        cb_col = f"cb_{left_name}"
        if left_name not in df.columns or cb_col not in df.columns:
            continue
        left_vals = _normalize_name(df[left_name])
        right_vals = _normalize_name(df[cb_col])
        flag_col = f"{left_name}_코드북_불일치"
        mismatch = left_vals.notna() & right_vals.notna() & (left_vals != right_vals)
        df[flag_col] = mismatch
        name_qc_counts[flag_col] = int(mismatch.sum())

    drop_cols = ["cb_match"] + [f"cb_{left_name}" for left_name in name_map.keys()]
    df = df.drop(columns=[c for c in drop_cols if c in df.columns])
    return df, name_qc_counts, int(df["codebook_미매칭"].sum())


def process_dataset(spec: DatasetSpec, output_root: Path, run_id: str) -> dict:
    input_path = Path(spec.input_csv)
    if not input_path.exists():
        raise FileNotFoundError(f"Missing input CSV: {input_path}")

    started_at = datetime.now()
    perf_start = time.perf_counter()
    _log("start", spec.dataset_id)
    _log(f"input_csv={input_path}", spec.dataset_id)

    read_start = time.perf_counter()
    df = _read_csv_with_fallback(
        input_path,
        dtype=str,
        keep_default_na=False,
        na_values=["", *MISSING_MARKERS],
        low_memory=False,
    )
    read_seconds = time.perf_counter() - read_start
    _log(f"read_complete seconds={read_seconds:.2f}", spec.dataset_id)

    row_count_in = int(len(df))
    df = df.replace(list(MISSING_MARKERS), pd.NA)

    transform_start = time.perf_counter()
    if spec.drop_cols:
        df = df.drop(columns=[c for c in spec.drop_cols if c in df.columns], errors="ignore")

    for col in spec.code_cols:
        if col in df.columns:
            df[col] = _normalize_code(df[col])

    station_code_fixed_count = 0
    if spec.coalesce_map:
        for target, source in spec.coalesce_map.items():
            if target in df.columns and source in df.columns:
                left = _normalize_code(df[target])
                right = _normalize_code(df[source])
                use_right = left.isna() & right.notna()
                station_code_fixed_count += int(use_right.sum())
                df[target] = left.fillna(right)
                df[source] = right

    for col in spec.name_cols:
        if col in df.columns:
            df[col] = _normalize_name(df[col])

    if spec.date_col not in df.columns:
        raise ValueError(f"Missing date column {spec.date_col} in {spec.dataset_id}")

    df[spec.date_col] = _parse_datetime(df[spec.date_col], spec.date_format)
    date_parse_failed = int(df[spec.date_col].isna().sum())

    df["event_date"] = df[spec.date_col].dt.date
    df["year"] = df[spec.date_col].dt.year
    df["month"] = df[spec.date_col].dt.month
    df["day"] = df[spec.date_col].dt.day

    key_null_mask = df[spec.pk_cols].isna().any(axis=1)
    key_null_rows = int(key_null_mask.sum())
    df = df.loc[~key_null_mask].copy()

    key_dup_rows = int(df.duplicated(subset=spec.pk_cols).sum())
    row_dup_rows = int(df.duplicated().sum())
    key_conflict_rows = int(max(key_dup_rows - row_dup_rows, 0))
    df = df.drop_duplicates()

    name_qc_counts: dict[str, int] = {}
    codebook_unmatched_rows = 0
    if spec.codebook:
        df, name_qc_counts, codebook_unmatched_rows = _apply_codebook(df, spec.codebook)
    else:
        df["codebook_미매칭"] = False

    for col in spec.numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    outlier_counts = _apply_outlier_rules(df, spec.outlier_rules)

    transform_seconds = time.perf_counter() - transform_start
    _log(f"transform_complete seconds={transform_seconds:.2f}", spec.dataset_id)

    output_dir = output_root / spec.output_subdir
    output_dir.mkdir(parents=True, exist_ok=True)

    write_start = time.perf_counter()
    df.to_parquet(
        output_dir,
        index=False,
        engine="pyarrow",
        compression="snappy",
        partition_cols=["year", "month", "day"],
        max_partitions=20000,
    )
    write_seconds = time.perf_counter() - write_start
    _log(f"write_complete seconds={write_seconds:.2f}", spec.dataset_id)

    dq_meta = {
        "dataset_id": spec.dataset_id,
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "started_at": started_at.isoformat(timespec="seconds"),
        "input_csv": str(input_path),
        "output_dir": str(output_dir),
        "row_count_in": row_count_in,
        "row_count_out": int(len(df)),
        "key_null_rows": key_null_rows,
        "key_dup_rows": key_dup_rows,
        "row_dup_rows": row_dup_rows,
        "key_conflict_rows": key_conflict_rows,
        "date_parse_failed": date_parse_failed,
        "outlier_counts": outlier_counts,
        "codebook_unmatched_rows": codebook_unmatched_rows,
        "name_qc_mismatch_counts": name_qc_counts,
        "read_seconds": round(read_seconds, 2),
        "transform_seconds": round(transform_seconds, 2),
        "write_seconds": round(write_seconds, 2),
    }
    if station_code_fixed_count:
        dq_meta["station_code_fixed_count"] = station_code_fixed_count

    dq_dir = output_root / "_dq" / spec.dataset_id / f"run_id={run_id}"
    dq_dir.mkdir(parents=True, exist_ok=True)
    dq_path = dq_dir / "dq_meta.json"
    dq_path.write_text(json.dumps(dq_meta, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    finished_at = datetime.now()
    dq_meta["finished_at"] = finished_at.isoformat(timespec="seconds")
    dq_meta["duration_seconds"] = round(time.perf_counter() - perf_start, 2)
    dq_path.write_text(json.dumps(dq_meta, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    _log("finished", spec.dataset_id)
    return dq_meta


def main() -> int:
    try:
        import pyarrow  # noqa: F401
    except Exception:
        print("[ERROR] pyarrow is required. Install from requirements.txt first.", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(description="Local silver ETL for KMA/RDA datasets.")
    parser.add_argument("--dataset-id", required=True, choices=sorted(DATASETS.keys()))
    parser.add_argument("--output-root", default="output_silver")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime(RUN_ID_FORMAT)
    output_root = Path(args.output_root)

    spec = DATASETS[args.dataset_id]
    dq_meta = process_dataset(spec, output_root, run_id)
    print(json.dumps(dq_meta, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
