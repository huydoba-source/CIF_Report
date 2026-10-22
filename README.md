# CIF Compliance Report — Streamlit

Web app xử lý file **CifExport** hàng tuần và xuất báo cáo lên Google Sheets.

**Luồng:** Tải file CSV → kiểm tra cấu trúc → *Xử lý & Xuất báo cáo* (thanh tiến trình + log realtime) → mở báo cáo / tải bản sao CSV.

## Cấu trúc

| File | Vai trò |
|---|---|
| `app.py` | Giao diện Streamlit |
| `cif_pipeline.py` | Logic xử lý (lọc → đối chiếu SS26 → ghi Sheets). Chạy CLI được: `python cif_pipeline.py file.csv key.json` |
| `make_secrets.py` | Chuyển file JSON service account thành nội dung `secrets.toml` |
| `.streamlit/config.toml` | Theme + giới hạn upload 1GB |
| `.streamlit/secrets.toml.example` | Mẫu cấu hình secrets |
| `upload_csv.py` | Script cũ (giữ để tham khảo) |

## ⚠️ Bảo mật

File `*.json` (service account) và `*.csv` đã được đưa vào `.gitignore`. **Tuyệt đối không commit chúng lên GitHub** — private key trong JSON cho phép bất kỳ ai ghi vào Google Sheets của bạn. Thông tin này được cấu hình qua **Secrets** của Streamlit Cloud.

## Chạy local

```bash
pip install -r requirements.txt
python make_secrets.py vnlegalbot-fj11-ae5b2283d48b.json > .streamlit/secrets.toml
streamlit run app.py
```

## Deploy lên Streamlit Community Cloud

1. Push thư mục này lên GitHub (kiểm tra `git status` không có file `.json`/`.csv`).
2. Vào [share.streamlit.io](https://share.streamlit.io) → **Create app** → chọn repo, branch, main file `app.py`.
3. **Advanced settings → Secrets**: dán nội dung in ra từ lệnh `python make_secrets.py <file>.json`.
   Tuỳ chọn thêm:
   ```toml
   spreadsheet_id = "13YODZ_HdDkXMAD3Z__HFSXGab64JiyNzpVtKkV8ZVBk"
   app_password = "mat-khau-noi-bo"   # bật màn hình đăng nhập
   ```
4. **Deploy.** Spreadsheet đích phải được share quyền **Editor** cho `client_email` của service account.

> Nếu repo để public, nên đặt `app_password` hoặc giới hạn người xem trong *App settings → Sharing*, vì bất kỳ ai có link đều có thể kích hoạt việc ghi lên Google Sheets.
