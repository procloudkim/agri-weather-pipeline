# Run Logging Spec (2025-12-26)

> 이 문서는 2025-12-26 원본 명세다. 파일명은 그때 기준이며 기록이므로 고치지 않았다. 이 저장소의 경로 대응은 [`PROVENANCE.md`](./PROVENANCE.md)의 대응표에 있다.

## 1) Purpose
- Document how the "user-friendly detail" requirements are applied during execution.
- Scope: local Bronze -> Silver runs using `pipeline_v1/run_local_backfill.ps1` and
  direct dataset runs via `pipeline_v1/local_silverize.py`.

## 2) Where the requirements are applied
### A) Execution-level logging (batch run)
**Trigger**
- Run: `powershell -ExecutionPolicy Bypass -File pipeline_v1/run_local_backfill.ps1`

**Behavior**
- Creates a run-scoped log file and writes start/end timestamps.
- Logs dataset START/END and elapsed time per dataset.
- Logs overall elapsed time.

**Output**
- `output_silver/_logs/run_id=YYYYMMDD_HHMMSS/run_log.md`

**Example log lines**
- `[YYYY-MM-DD HH:MM:SS] run_id=YYYYMMDD_HHMMSS`
- `[YYYY-MM-DD HH:MM:SS] START dataset=KMA_CROP_DETAIL`
- `[YYYY-MM-DD HH:MM:SS] END dataset=KMA_CROP_DETAIL elapsed=00:23:45.6789012`
- `[YYYY-MM-DD HH:MM:SS] FINISH elapsed=02:03:53.1234567`

### B) Dataset-level logging (per dataset)
**Trigger**
- Called by `run_local_backfill.ps1` or directly via:
  `python pipeline_v1/local_silverize.py --dataset-id <ID> --output-root <DIR> --run-id <RUN_ID>`

**Behavior**
- Prints progress with timestamps to console for:
  - start, read_complete, transform_complete, write_complete, finished.
- Uses `dataset_id` in the log prefix.

**Output (console)**
- `[YYYY-MM-DDTHH:MM:SS] [KMA_CROP_DETAIL] start`
- `[YYYY-MM-DDTHH:MM:SS] [KMA_CROP_DETAIL] read_complete seconds=...`
- `[YYYY-MM-DDTHH:MM:SS] [KMA_CROP_DETAIL] transform_complete seconds=...`
- `[YYYY-MM-DDTHH:MM:SS] [KMA_CROP_DETAIL] write_complete seconds=...`
- `[YYYY-MM-DDTHH:MM:SS] [KMA_CROP_DETAIL] finished`

### C) DQ meta enrichment (per dataset)
**Trigger**
- Always produced by `pipeline_v1/local_silverize.py`.

**Behavior**
- Adds timing fields to `dq_meta.json`:
  - `started_at`, `finished_at`, `duration_seconds`
  - `read_seconds`, `transform_seconds`, `write_seconds`

**Output**
- `output_silver/_dq/<DATASET>/run_id=<RUN_ID>/dq_meta.json`

## 3) How to interpret the timing
- **Start time**: `started_at` in dq_meta or the run_id timestamp.
- **End time**: `finished_at` in dq_meta or final log line.
- **Dataset elapsed**: `duration_seconds` in dq_meta.
- **Run elapsed**: `FINISH elapsed=...` in run_log.md.

## 4) What this does NOT change
- No change to Silver content or partitioning.
- Only adds logs and timing metadata.

## 5) Quick verification
- Run log exists:
  - `output_silver/_logs/run_id=YYYYMMDD_HHMMSS/run_log.md`
- DQ meta contains timing fields:
  - `output_silver/_dq/<DATASET>/run_id=<RUN_ID>/dq_meta.json`
