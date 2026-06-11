#!/usr/bin/env python3
"""Poll the Fivetran connection until a NEW sync success or failure appears
(compared to the succeeded_at / failed_at baselines passed as args)."""
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
AUTH = (os.environ["FIVETRAN_API_KEY"], os.environ["FIVETRAN_API_SECRET"])
CONN = os.getenv("FIVETRAN_SFMC_CONNECTION_ID", "argument_dictate")
base_ok = sys.argv[1] if len(sys.argv) > 1 else None
base_fail = sys.argv[2] if len(sys.argv) > 2 else None

while True:
    try:
        d = requests.get(f"https://api.fivetran.com/v1/connections/{CONN}",
                         auth=AUTH, timeout=30).json()["data"]
        ok, fail = d.get("succeeded_at"), d.get("failed_at")
        if ok and ok != base_ok:
            print(f"SYNC SUCCEEDED at {ok}")
            break
        if fail and fail != base_fail:
            print(f"SYNC FAILED at {fail}")
            break
    except Exception as e:
        print(f"poll error (retrying): {e}", file=sys.stderr)
    time.sleep(60)
