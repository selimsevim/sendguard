#!/usr/bin/env python3
"""Exit 0 if SFMC SFTP password login works, 1 otherwise."""
import os
import sys

import paramiko
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
t = paramiko.Transport((os.environ["SFMC_SFTP_HOST"], 22))
t.get_security_options().key_types = ("ssh-rsa",)
try:
    t.connect(username=os.environ["SFMC_SFTP_USER"], password=os.environ["SFMC_SFTP_PASSWORD"])
    sftp = paramiko.SFTPClient.from_transport(t)
    print("LOGIN OK, root listing:", sftp.listdir("."))
    t.close()
except Exception as e:
    print("LOGIN FAIL:", type(e).__name__, e)
    sys.exit(1)
