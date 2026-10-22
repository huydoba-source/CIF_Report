"""
CIF Weekly Report pipeline.

Logic giữ nguyên như upload_csv.py, nhưng được tách thành module độc lập với UI:
  1. Kết nối Google Sheet
  2. Tải 'SS26 Compliance list' -> lookup map (cột A -> Q, AD)
  3. Quét CSV theo chunk, lọc 'Cif completed for my zone' == 'no', lấy CIF Code duy nhất
  4. Đối chiếu với lookup map
  5. Tạo sheet 'CIF Report - dd-Mon-YYYY' và ghi dữ liệu theo batch
  6. Định dạng header

UI (Streamlit) giao tiếp với pipeline qua một `Reporter` gồm 3 callback:
log / progress / stage — nhờ vậy module này không phụ thuộc Streamlit và có thể chạy CLI.
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
# CẤU HÌNH MẶC ĐỊNH
# ==========================================
DEFAULT_SPREADSHEET_ID = "1jUQi_HsR3Tvd5iegmuEqK3MQCHwzpXXFygQj1NJi9Mg"
LOOKUP_SHEET_NAME = "SS26 Compliance list"
FILTER_COLUMN = "Cif completed for my zone"
FILTER_VALUE = "no"
LOOKUP_COL_Q = 16   # cột Q (0-based)
LOOKUP_COL_AD = 29  # cột AD (0-based)
REPORT_HEADER = ["CIF Code", "Compliance Data (Q)", "Compliance Data (AD)"]
NOT_FOUND = "Not found"

CSV_CHUNK_SIZE = 25_000
SHEET_WRITE_BATCH = 10_000
TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

# Mỗi stage chiếm một khoảng % trên thanh tiến trình tổng
STAGES = [
    ("connect", "Kết nối Google Sheets", 0, 5),
    ("lookup", "Tải SS26 Compliance list", 5, 15),
    ("scan", "Quét & lọc file CIF", 15, 70),
    ("match", "Đối chiếu dữ liệu", 70, 75),
    ("upload", "Ghi báo cáo lên Google Sheets", 75, 97),
    ("format", "Định dạng báo cáo", 97, 100),
]
STAGE_RANGE = {key: (start, end) for key, _, start, end in STAGES}


class Reporter(Protocol):
    def log(self, message: str, level: str = "info") -> None: ...
    def progress(self, percent: float, detail: str = "") -> None: ...
    def stage(self, key: str, status: str) -> None: ...  # status: running | done | error


class PipelineError(Exception):
    """Lỗi có thông điệp thân thiện để hiển thị cho người dùng."""


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
# KIỂM TRA FILE (chỉ đọc header, không parse toàn bộ file)
# ==========================================
def inspect_csv(data: bytes) -> CsvInspection:
    header = pd.read_csv(io.BytesIO(data), nrows=0, encoding="utf-8-sig")
    columns = [str(c) for c in header.columns]
    if not columns:
        raise PipelineError("File CSV không có dòng tiêu đề.")
    # Đếm ký tự xuống dòng để ước tính số dòng — nhanh hơn nhiều so với parse CSV
    estimated_rows = max(data.count(b"\n") - 1, 0)
    return CsvInspection(
        columns=columns,
        id_column=columns[0],
        has_filter_column=FILTER_COLUMN in columns,
        size_bytes=len(data),
        estimated_rows=estimated_rows,
    )


# ==========================================
# PIPELINE CHÍNH
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
        # ---------- 1. Kết nối ----------
        begin("connect")
        reporter.log("Đang kết nối tới Google Sheet...")
        try:
            gc = gspread.service_account_from_dict(credentials)
            sh = gc.open_by_key(spreadsheet_id)
        except gspread.exceptions.SpreadsheetNotFound:
            raise PipelineError(
                "Không tìm thấy Spreadsheet. Hãy kiểm tra ID và chia sẻ quyền Editor cho "
                f"service account: {credentials.get('client_email', '')}"
            )
        reporter.log(f"Đã kết nối: “{sh.title}”", "success")
        finish("connect")

        # ---------- 2. Lookup map ----------
        begin("lookup")
        reporter.log(f"Đang tải dữ liệu từ '{lookup_sheet_name}' để tạo từ điển (Lookup Map)...")
        try:
            fixed_data = sh.worksheet(lookup_sheet_name).get_all_values()
        except gspread.exceptions.WorksheetNotFound:
            raise PipelineError(f"Không tìm thấy sheet '{lookup_sheet_name}' trong Spreadsheet.")

        lookup_map: dict[str, tuple[str, str]] = {}
        for row in fixed_data[1:]:  # Bỏ qua dòng tiêu đề
            if row:
                key = str(row[0]).strip()
                if key:
                    val_q = row[LOOKUP_COL_Q] if len(row) > LOOKUP_COL_Q else ""
                    val_ad = row[LOOKUP_COL_AD] if len(row) > LOOKUP_COL_AD else ""
                    lookup_map[key] = (val_q, val_ad)
        reporter.log(f"-> Lookup Map gồm {len(lookup_map):,} mã từ {len(fixed_data) - 1:,} dòng.", "success")
        finish("lookup")

        # ---------- 3. Quét CSV ----------
        begin("scan")
        reporter.log(f"Đang đọc file CSV và lọc các CIF Code ({FILTER_COLUMN} = '{FILTER_VALUE}')...")
        inspection = inspect_csv(csv_bytes)
        if not inspection.has_filter_column:
            raise PipelineError(f"File CSV không có cột bắt buộc '{FILTER_COLUMN}'.")
        reporter.log(f"Cột khóa: '{inspection.id_column}' · Kích thước: {inspection.size_bytes / 1_048_576:,.1f} MB")

        # Chỉ đọc đúng 2 cột cần thiết, giữ nguyên dạng chuỗi (tránh 374887 -> 374887.0)
        reader = pd.read_csv(
            io.BytesIO(csv_bytes),
            usecols=[inspection.id_column, FILTER_COLUMN],
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
            chunksize=CSV_CHUNK_SIZE,
        )
        # dict giữ thứ tự xuất hiện -> báo cáo ổn định giữa các lần chạy
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
            reporter.progress(_stage_progress("scan", min(fraction, 0.99)), f"{total_rows:,} dòng")
            reporter.log(
                f"Chunk #{idx}: đã quét {total_rows:,} dòng · {filtered_rows:,} dòng 'no' · "
                f"{len(unique_ids):,} mã duy nhất"
            )
        reporter.log(f"-> Tìm thấy {len(unique_ids):,} CIF Code duy nhất cần báo cáo.", "success")
        finish("scan")

        # ---------- 4. Đối chiếu ----------
        begin("match")
        reporter.log("Đang đối chiếu dữ liệu để tạo báo cáo...")
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
        reporter.log(f"-> Khớp {matched:,} mã · {not_found:,} mã không có trong Compliance list.", "success")
        finish("match")

        # ---------- 5. Ghi lên Google Sheets ----------
        begin("upload")
        now = datetime.now(TIMEZONE)
        sheet_name = f"CIF Report - {now.strftime('%d-%b-%Y')}"
        if sheet_name in {s.title for s in sh.worksheets()}:
            sheet_name += f" ({now.strftime('%H%M%S')})"

        n_cols = len(REPORT_HEADER)
        reporter.log(f"Đang tạo Sheet mới '{sheet_name}' và đẩy {len(report_rows):,} dòng lên...")
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
            reporter.progress(_stage_progress("upload", done_rows / total), f"{done_rows:,}/{total:,} dòng")
            reporter.log(f"-> Đã ghi dòng {first_row:,} đến {done_rows:,}")
        finish("upload")

        # ---------- 6. Định dạng ----------
        begin("format")
        reporter.log("Đang định dạng Header...")
        report_sheet.format(f"A1:{last_col}1", {
            "backgroundColor": {"red": 74 / 255, "green": 134 / 255, "blue": 232 / 255},
            "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True},
            "horizontalAlignment": "CENTER",
        })
        report_sheet.freeze(rows=1)
        finish("format")

        elapsed = time.perf_counter() - started
        reporter.log(f"✅ Báo cáo CIF Weekly Report đã được tạo thành công trong {elapsed:,.1f}s!", "success")
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
        reporter.log(f"❌ Google API lỗi: {exc}", "error")
        raise PipelineError(f"Google Sheets API trả về lỗi: {exc}") from exc
    except Exception as exc:
        reporter.stage(current_stage, "error")
        reporter.log(f"❌ Lỗi không mong muốn: {exc!r}", "error")
        raise


# ==========================================
# CHẠY TỪ DÒNG LỆNH (tương đương upload_csv.py cũ)
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
        print("Cách dùng: python cif_pipeline.py <file.csv> <service_account.json>")
        sys.exit(1)
    with open(sys.argv[1], "rb") as f_csv, open(sys.argv[2], encoding="utf-8") as f_key:
        run_pipeline(f_csv.read(), json.load(f_key), _PrintReporter())
