"""Convert a service account JSON key into secrets.toml content.

Usage:  python make_secrets.py vnlegalbot-xxxx.json > .streamlit/secrets.toml
Then paste the full output into Streamlit Cloud -> App settings -> Secrets.
"""

import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    key = json.load(f)

print("[gcp_service_account]")
for k, v in key.items():
    print(f"{k} = {json.dumps(v)}")
