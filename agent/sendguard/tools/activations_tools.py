"""Blocking wait helper for Fivetran Activations sync runs.

The MCP fork exposes trigger/status tools, but polling from the model burns a
tool call per check. This native tool polls server-side and returns once the
run reaches a terminal state (or the timeout passes).
"""

import os
import time

import requests

ACTIVATIONS_BASE_URL = "https://app.getcensus.com/api/v1"


def wait_for_activation_sync(sync_run_id: int, timeout_minutes: int = 10) -> dict:
    """Wait for an Activations sync run to finish and return its final status.

    Polls the run every 10 seconds server-side; call this ONCE after
    trigger_activation_sync instead of polling get_activation_sync_run in a loop.

    Args:
        sync_run_id: the run id returned by trigger_activation_sync.
        timeout_minutes: give up after this many minutes (default 10).

    Returns:
        dict with final status, records_processed/updated/failed, duration --
        or {"error"/"timeout": ...}.
    """
    token = os.getenv("FIVETRAN_ACTIVATIONS_TOKEN", "")
    if not token:
        return {"error": "FIVETRAN_ACTIVATIONS_TOKEN is not configured"}
    if not token.startswith("secret-token:"):
        token = f"secret-token:{token}"
    deadline = time.time() + timeout_minutes * 60
    last = {}
    while time.time() < deadline:
        try:
            r = requests.get(f"{ACTIVATIONS_BASE_URL}/sync_runs/{sync_run_id}",
                             headers={"Authorization": f"Bearer {token}"}, timeout=30)
            r.raise_for_status()
            last = r.json().get("data", {})
            if last.get("status") in ("completed", "failed", "skipped"):
                return {
                    "status": last.get("status"),
                    "source_record_count": last.get("source_record_count"),
                    "records_updated": last.get("records_updated"),
                    "records_processed": last.get("records_processed"),
                    "records_failed": last.get("records_failed"),
                    "error_message": last.get("error_message"),
                    "completed_at": last.get("completed_at"),
                }
        except Exception as e:
            last = {"poll_error": str(e)}
        time.sleep(10)
    return {"timeout": f"sync run {sync_run_id} not finished after {timeout_minutes} min",
            "last_status": last.get("status"), "detail": last}
