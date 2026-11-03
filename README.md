# CIF Compliance Report — Streamlit

Web app that processes the weekly **CifExport** file and publishes the report to Google Sheets.

**Flow:** Upload CSV → validate structure → *Process & Publish* (progress bar + real-time log) → open the report / download a CSV copy.

## Structure

| File | Purpose |
|---|---|
| `app.py` | Streamlit user interface |
| `cif_pipeline.py` | Processing logic (filter → match against SS26 → write to Sheets). Also runs as a CLI: `python cif_pipeline.py file.csv key.json` |
| `make_secrets.py` | Converts the service account JSON key into `secrets.toml` content |
| `.streamlit/config.toml` | Theme + 1GB upload limit |
| `.streamlit/secrets.toml.example` | Secrets template |
| `upload_csv.py` | Legacy script (kept for reference, not needed by the app) |

## ⚠️ Security

`*.json` (service account key) and `*.csv` files are listed in `.gitignore`. **Never commit them to GitHub** — the private key in the JSON file lets anyone write to your Google Sheets. These credentials are configured through Streamlit Cloud **Secrets** instead.

## Run locally

```bash
pip install -r requirements.txt
python make_secrets.py vnlegalbot-fj11-ae5b2283d48b.json > .streamlit/secrets.toml
streamlit run app.py
```

## Deploy to Streamlit Community Cloud

1. Push this folder to GitHub (make sure `git status` shows no `.json`/`.csv` files).
2. Go to [share.streamlit.io](https://share.streamlit.io) → **Create app** → pick the repo, branch and main file `app.py`.
3. **Advanced settings → Secrets**: paste the output of `python make_secrets.py <file>.json`.
   Optional extras:
   ```toml
   spreadsheet_id = "13YODZ_HdDkXMAD3Z__HFSXGab64JiyNzpVtKkV8ZVBk"
   app_password = "internal-password"   # enables the sign-in screen
   ```
4. **Deploy.** The target spreadsheet must be shared with **Editor** access to the service account's `client_email`.

> If the repo is public, set `app_password` or restrict viewers under *App settings → Sharing*, since anyone with the link can trigger writes to Google Sheets.
