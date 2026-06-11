"""BigQuery tools for SendGuard.

Uses Application Default Credentials (`gcloud auth application-default login`
locally, the service account on Cloud Run). Every call returns a dict; errors
come back as {"error": ...} so the agent can narrate failures instead of dying.
"""

import os
from datetime import datetime, timezone

from google.cloud import bigquery

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "fivetran-499011")
LOCATION = os.getenv("BIGQUERY_LOCATION", "US")
SFMC_DATASET = os.getenv("BQ_SFMC_DATASET", "salesforce_marketing_cloud")
CENSUS_DATASET = os.getenv("BQ_CENSUS_DATASET", "CENSUS")

MAX_ROWS_RETURNED = 200

_client = None


def _bq() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=PROJECT, location=LOCATION)
    return _client


def run_bigquery_sql(sql: str) -> dict:
    """Run a SQL query against BigQuery and return the rows.

    Only the SFMC dataset (synced from Salesforce Marketing Cloud by Fivetran)
    and the CENSUS dataset are relevant. Returns at most 200 rows; write
    aggregate queries (COUNT, GROUP BY) rather than selecting raw rows.

    Args:
        sql: Standard SQL. Fully qualify tables, e.g.
             `fivetran-499011.salesforce_marketing_cloud.<table>`.

    Returns:
        dict with "rows" (list of dicts), "row_count", and "truncated".
    """
    try:
        job = _bq().query(sql)
        result = job.result(max_results=MAX_ROWS_RETURNED + 1)
        rows = [dict(r) for r in result]
        truncated = len(rows) > MAX_ROWS_RETURNED
        rows = rows[:MAX_ROWS_RETURNED]
        for r in rows:  # timestamps/dates are not JSON serializable
            for k, v in r.items():
                if isinstance(v, (datetime,)) or hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
        return {"rows": rows, "row_count": len(rows), "truncated": truncated}
    except Exception as e:
        return {"error": f"BigQuery query failed: {e}", "sql": sql}


def list_sfmc_tables() -> dict:
    """List tables in the Fivetran-synced SFMC dataset with row counts and
    last-modified times. Use this to find the synced data extension tables."""
    try:
        tables = []
        for t in _bq().list_tables(f"{PROJECT}.{SFMC_DATASET}"):
            full = _bq().get_table(t.reference)
            tables.append({
                "table": t.table_id,
                "rows": full.num_rows,
                "last_modified_utc": full.modified.astimezone(timezone.utc).isoformat(),
            })
        return {"dataset": SFMC_DATASET, "tables": tables}
    except Exception as e:
        return {"error": f"Could not list tables: {e}"}


def write_repaired_audience(audience_table: str, subscribers_table: str) -> dict:
    """Build the repaired audience and write it to CENSUS.agent_results
    (truncate + insert, preserving the table the Activations sync reads).

    Repairs applied:
      - duplicates removed (one row per subscriber_key)
      - members who are unsubscribed in the subscribers table removed
      - rows with NULL/empty email removed

    Args:
        audience_table: table name of the synced campaign audience DE in the
            SFMC dataset (e.g. "campaign_audience").
        subscribers_table: table name of the synced subscribers DE.

    Returns:
        dict with rows_written and a breakdown of what was removed.
    """
    aud = f"`{PROJECT}.{SFMC_DATASET}.{audience_table}`"
    sub = f"`{PROJECT}.{SFMC_DATASET}.{subscribers_table}`"
    target = f"`{PROJECT}.{CENSUS_DATASET}.agent_results`"
    sql = f"""
    BEGIN
      TRUNCATE TABLE {target};
      INSERT INTO {target} (subscriber_key, email, reason, created_at)
      WITH deduped AS (
        SELECT subscriber_key, email,
               ROW_NUMBER() OVER (PARTITION BY subscriber_key ORDER BY subscriber_key) AS rn
        FROM {aud}
        WHERE email IS NOT NULL AND email != ''
      )
      SELECT d.subscriber_key, d.email,
             'validated: deduplicated, consent-checked' AS reason,
             CURRENT_TIMESTAMP() AS created_at
      FROM deduped d
      JOIN {sub} s USING (subscriber_key)
      WHERE d.rn = 1 AND LOWER(s.status) != 'unsubscribed';
    END
    """
    try:
        _bq().query(sql).result()
        stats_sql = f"""
        SELECT
          (SELECT COUNT(*) FROM {aud}) AS audience_rows,
          (SELECT COUNT(*) FROM {target}) AS repaired_rows,
          (SELECT COUNT(*) - COUNT(DISTINCT subscriber_key) FROM {aud}) AS duplicate_rows,
          (SELECT COUNT(DISTINCT a.subscriber_key) FROM {aud} a
             JOIN {sub} s USING (subscriber_key)
             WHERE LOWER(s.status) = 'unsubscribed') AS unsubscribed_members
        """
        stats = [dict(r) for r in _bq().query(stats_sql).result()][0]
        return {"status": "repaired audience written to CENSUS.agent_results", **stats}
    except Exception as e:
        return {"error": f"Repair failed: {e}"}
