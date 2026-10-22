"""Chuyển file JSON service account thành nội dung secrets.toml.

Cách dùng:  python make_secrets.py vnlegalbot-xxxx.json > .streamlit/secrets.toml
Sau đó copy nguyên nội dung vào Streamlit Cloud -> App settings -> Secrets.
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    key = json.load(f)

print("[gcp_service_account]")
for k, v in key.items():
    print(f"{k} = {json.dumps(v)}")
