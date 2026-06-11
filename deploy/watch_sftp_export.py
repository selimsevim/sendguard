#!/usr/bin/env python3
"""Poll the SFMC SFTP Export folder until a file matching the pattern appears."""
import os
import sys
import time

import paramiko
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
PATTERN = sys.argv[1] if len(sys.argv) > 1 else "D3C9C234"
MAX_MINUTES = int(sys.argv[2]) if len(sys.argv) > 2 else 45

for i in range(MAX_MINUTES):
    try:
        t = paramiko.Transport((os.environ["SFMC_SFTP_HOST"], 22))
        t.get_security_options().key_types = ("ssh-rsa",)
        t.connect(username=os.environ["SFMC_SFTP_USER"],
                  password=os.environ["SFMC_SFTP_PASSWORD"])
        sftp = paramiko.SFTPClient.from_transport(t)
        hits = [f for f in sftp.listdir("Export") if PATTERN in f]
        t.close()
        if hits:
            print(f"EXPORT FILE APPEARED: {hits}")
            sys.exit(0)
    except Exception as e:
        print(f"poll error (retrying): {e}", file=sys.stderr)
    time.sleep(60)

print(f"TIMEOUT: no file matching '{PATTERN}' after {MAX_MINUTES} minutes")
sys.exit(1)
