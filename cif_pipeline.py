"""
CIF Weekly Report pipeline.

Same logic as upload_csv.py, extracted into a UI-independent module:
  1. Connect to the Google Sheet
  2. Load 'SS26 Compliance list' -> lookup map (column A -> Q, AD)
  3. Scan the CSV in chunks, keep 'Cif completed for my zone' == 'no', collect unique CIF Codes
  4. Match against the lookup map
  5. Create the 'CIF Report - dd-Mon-YYYY' sheet and write the data in batches
  6. Format the header

The UI (Streamlit) talks to the pipeline through a `Reporter` with 3 callbacks:
log / progress / stage — so this module does not depend on Streamlit and can run as a CLI.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

import gspread
import pandas as pd

# ==========================================
# DEFAULT CONFIGURATION
# ==========================================
DEFAULT_SPREADSHEET_ID = "13YODZ_HdDkXMAD3Z__HFSXGab64JiyNzpVtKkV8ZVBk"
LOOKUP_SHEET_NAME = "SS26 Compliance list"
FILTER_COLUMN = "Cif completed for my zone"
FILTER_VALUE = "no"
LOOKUP_COL_Q = 16   # column Q (0-based)
LOOKUP_COL_AD = 29  # column AD (0-based)
REPORT_HEADER = ["CIF Code", "Compliance Data (Q)", "Compliance Data (AD)"]
NOT_FOUND = "Not found"

CSV_CHUNK_SIZE = 25_000
SHEET_WRITE_BATCH = 10_000
TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

# Each stage owns a slice (%) of the overall progress bar
STAGES = [
    ("connect", "Connect to Google Sheets", 0, 5),
    ("lookup", "Load SS26 Compliance list", 5, 15),
    ("scan", "Scan & filter CIF file", 15, 70),
    ("match", "Match records", 70, 75),
    ("upload", "Write report to Google Sheets", 75, 97),
    ("format", "Format report", 97, 100),
]
STAGE_RANGE = {key: (start, end) for key, _, start, end in STAGES}


class Reporter(Protocol):
    def log(self, message: str, level: str = "info") -> None: ...
    def progress(self, percent: float, detail: str = "") -> None: ...
    def stage(self, key: str, status: str) -> None: ...  # status: running | done | error


class PipelineError(Exception):
    """Error carrying a user-friendly message for display."""


@dataclass
class CsvInspection:
    columns: list[str]
    id_column: str
    has_filter_column: bool
    size_bytes: int
    estimated_rows: int


@dataclass
class PipelineResult:
    sheet_name: str
    sheet_url: str
    total_rows: int
    filtered_rows: int
    unique_ids: int
    matched: int
    not_found: int
    elapsed_seconds: float
    report_rows: list[list[str]] = field(repr=False, default_factory=list)


# ==========================================
# FILE INSPECTION (header only, no full parse)
# ==========================================
def inspect_csv(data: bytes) -> CsvInspection:
    header = pd.read_csv(io.BytesIO(data), nrows=0, encoding="utf-8-sig")
    columns = [str(c) for c in header.columns]
    if not columns:
        raise PipelineError("The CSV file has no header row.")
    # Count line breaks to estimate the row count — far faster than parsing the CSV
    estimated_rows = max(data.count(b"\n") - 1, 0)
    return CsvInspection(
        columns=columns,
        id_column=columns[0],
        has_filter_column=FILTER_COLUMN in columns,
        size_bytes=len(data),
        estimated_rows=estimated_rows,
    )


# ==========================================
# MAIN PIPELINE
# ==========================================
def _stage_progress(key: str, fraction: float) -> float:
    start, end = STAGE_RANGE[key]
    return start + (end - start) * min(max(fraction, 0.0), 1.0)


def _to_col_letter(n: int) -> str:
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def run_pipeline(
    csv_bytes: bytes,
    credentials: dict,
    reporter: Reporter,
    spreadsheet_id: str = DEFAULT_SPREADSHEET_ID,
    lookup_sheet_name: str = LOOKUP_SHEET_NAME,
) -> PipelineResult:
    started = time.perf_counter()
    current_stage = "connect"

    def begin(key: str) -> None:
        nonlocal current_stage
        current_stage = key
        reporter.stage(key, "running")
        reporter.progress(_stage_progress(key, 0))

    def finish(key: str) -> None:
        reporter.stage(key, "done")
        reporter.progress(_stage_progress(key, 1))

    try:
        # ---------- 1. Connect ----------
        begin("connect")
        reporter.log("Connecting to Google Sheet...")
        try:
            gc = gspread.service_account_from_dict(credentials)
            sh = gc.open_by_key(spreadsheet_id)
        except gspread.exceptions.SpreadsheetNotFound:
            raise PipelineError(
                "Spreadsheet not found. Check the ID and share Editor access with the "
                f"service account: {credentials.get('client_email', '')}"
            )
        reporter.log(f"Connected: “{sh.title}”", "success")
        finish("connect")

        # ---------- 2. Lookup map ----------
        begin("lookup")
        reporter.log(f"Loading '{lookup_sheet_name}' to build the Lookup Map...")
        try:
            fixed_data = sh.worksheet(lookup_sheet_name).get_all_values()
        except gspread.exceptions.WorksheetNotFound:
            raise PipelineError(f"Sheet '{lookup_sheet_name}' was not found in the Spreadsheet.")

        lookup_map: dict[str, tuple[str, str]] = {}
        for row in fixed_data[1:]:  # Skip the header row
            if row:
                key = str(row[0]).strip()
                if key:
                    val_q = row[LOOKUP_COL_Q] if len(row) > LOOKUP_COL_Q else ""
                    val_ad = row[LOOKUP_COL_AD] if len(row) > LOOKUP_COL_AD else ""
                    lookup_map[key] = (val_q, val_ad)
        reporter.log(f"-> Lookup Map holds {len(lookup_map):,} codes from {len(fixed_data) - 1:,} rows.", "success")
        finish("lookup")

        # ---------- 3. Scan CSV ----------
        begin("scan")
        reporter.log(f"Reading the CSV file and filtering CIF Codes ({FILTER_COLUMN} = '{FILTER_VALUE}')...")
        inspection = inspect_csv(csv_bytes)
        if not inspection.has_filter_column:
            raise PipelineError(f"The CSV file is missing the required column '{FILTER_COLUMN}'.")
        reporter.log(f"Key column: '{inspection.id_column}' · Size: {inspection.size_bytes / 1_048_576:,.1f} MB")

        # Read only the 2 required columns, kept as strings (avoids 374887 -> 374887.0)
        reader = pd.read_csv(
            io.BytesIO(csv_bytes),
            usecols=[inspection.id_column, FILTER_COLUMN],
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
            chunksize=CSV_CHUNK_SIZE,
        )
        # dict preserves first-seen order -> stable report between runs
        unique_ids: dict[str, None] = {}
        total_rows = filtered_rows = 0
        for idx, chunk in enumerate(reader, start=1):
            total_rows += len(chunk)
            mask = chunk[FILTER_COLUMN].str.strip().str.lower() == FILTER_VALUE
            ids = chunk.loc[mask, inspection.id_column].str.strip()
            filtered_rows += int(mask.sum())
            for uid in ids:
                if uid and uid.lower() != "nan":
                    unique_ids[uid] = None

            fraction = total_rows / max(inspection.estimated_rows, 1)
            reporter.progress(_stage_progress("scan", min(fraction, 0.99)), f"{total_rows:,} rows")
            reporter.log(
                f"Chunk #{idx}: scanned {total_rows:,} rows · {filtered_rows:,} 'no' rows · "
                f"{len(unique_ids):,} unique codes"
            )
        reporter.log(f"-> Found {len(unique_ids):,} unique CIF Codes to report.", "success")
        finish("scan")

        # ---------- 4. Match ----------
        begin("match")
        reporter.log("Matching records to build the report...")
        report_rows = [REPORT_HEADER]
        matched = 0
        for uid in unique_ids:
            hit = lookup_map.get(uid)
            if hit:
                matched += 1
                report_rows.append([uid, *("" if pd.isna(v) else str(v) for v in hit)])
            else:
                report_rows.append([uid, NOT_FOUND, NOT_FOUND])
        not_found = len(unique_ids) - matched
        reporter.log(f"-> Matched {matched:,} codes · {not_found:,} codes not in the Compliance list.", "success")
        finish("match")

        # ---------- 5. Write to Google Sheets ----------
        begin("upload")
        now = datetime.now(TIMEZONE)
        sheet_name = f"CIF Report - {now.strftime('%d-%b-%Y')}"
        if sheet_name in {s.title for s in sh.worksheets()}:
            sheet_name += f" ({now.strftime('%H%M%S')})"

        n_cols = len(REPORT_HEADER)
        reporter.log(f"Creating new sheet '{sheet_name}' and writing {len(report_rows):,} rows...")
        report_sheet = sh.add_worksheet(title=sheet_name, rows=len(report_rows) + 10, cols=5)

        total = len(report_rows)
        last_col = _to_col_letter(n_cols)
        for start in range(0, total, SHEET_WRITE_BATCH):
            batch = report_rows[start:start + SHEET_WRITE_BATCH]
            first_row = start + 1
            report_sheet.update(
                range_name=f"A{first_row}:{last_col}{first_row + len(batch) - 1}",
                values=batch,
                value_input_option="USER_ENTERED",
            )
            done_rows = start + len(batch)
            reporter.progress(_stage_progress("upload", done_rows / total), f"{done_rows:,}/{total:,} rows")
            reporter.log(f"-> Wrote rows {first_row:,} to {done_rows:,}")
        finish("upload")

        # ---------- 6. Format ----------
        begin("format")
        reporter.log("Formatting the header...")
        report_sheet.format(f"A1:{last_col}1", {
            "backgroundColor": {"red": 74 / 255, "green": 134 / 255, "blue": 232 / 255},
            "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True},
            "horizontalAlignment": "CENTER",
        })
        report_sheet.freeze(rows=1)
        finish("format")

        elapsed = time.perf_counter() - started
        reporter.log(f"✅ CIF Weekly Report created successfully in {elapsed:,.1f}s!", "success")
        return PipelineResult(
            sheet_name=sheet_name,
            sheet_url=f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={report_sheet.id}",
            total_rows=total_rows,
            filtered_rows=filtered_rows,
            unique_ids=len(unique_ids),
            matched=matched,
            not_found=not_found,
            elapsed_seconds=elapsed,
            report_rows=report_rows,
        )

    except PipelineError as exc:
        reporter.stage(current_stage, "error")
        reporter.log(f"❌ {exc}", "error")
        raise
    except gspread.exceptions.APIError as exc:
        reporter.stage(current_stage, "error")
        reporter.log(f"❌ Google API error: {exc}", "error")
        raise PipelineError(f"Google Sheets API returned an error: {exc}") from exc
    except Exception as exc:
        reporter.stage(current_stage, "error")
        reporter.log(f"❌ Unexpected error: {exc!r}", "error")
        raise


# ==========================================
# COMMAND-LINE ENTRY POINT (equivalent to the old upload_csv.py)
# ==========================================
class _PrintReporter:
    def log(self, message: str, level: str = "info") -> None:
        print(message)

    def progress(self, percent: float, detail: str = "") -> None:
        pass

    def stage(self, key: str, status: str) -> None:
        pass


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 3:
        print("Usage: python cif_pipeline.py <file.csv> <service_account.json>")
        sys.exit(1)
    with open(sys.argv[1], "rb") as f_csv, open(sys.argv[2], encoding="utf-8") as f_key:
        run_pipeline(f_csv.read(), json.load(f_key), _PrintReporter())
