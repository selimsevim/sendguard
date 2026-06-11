#!/usr/bin/env bash
# FALLBACK ONLY: load campaign_audience into BigQuery directly, shaped exactly
# like a Fivetran DE table, when the connector's daily DE import window is too
# far away. The real Fivetran daily import will overwrite this with identical
# data on its next DE window.
set -euo pipefail
cd "$(dirname "$0")/.."

MERGED=/tmp/campaign_audience_merged.csv
if [ ! -f "$MERGED" ]; then
  head -1 datagen/output/campaign_audience_part001.csv > "$MERGED"
  tail -n +2 -q datagen/output/campaign_audience_part00*.csv >> "$MERGED"
fi

bq --project_id=fivetran-499011 load --replace --source_format=CSV --skip_leading_rows=1 \
  salesforce_marketing_cloud.ext_campaign_audience_raw "$MERGED" \
  audience_row_id:STRING,subscriber_key:STRING,email:STRING,country:STRING,added_date:DATETIME

bq --project_id=fivetran-499011 query --use_legacy_sql=false "
CREATE OR REPLACE TABLE \`fivetran-499011.salesforce_marketing_cloud.ext_campaign_audience\` AS
SELECT audience_row_id, subscriber_key, email, country, added_date,
       FALSE AS _fivetran_deleted, CURRENT_TIMESTAMP() AS _fivetran_synced
FROM \`fivetran-499011.salesforce_marketing_cloud.ext_campaign_audience_raw\`;
DROP TABLE \`fivetran-499011.salesforce_marketing_cloud.ext_campaign_audience_raw\`;
SELECT COUNT(*) AS total_rows, COUNT(DISTINCT subscriber_key) AS unique_keys
FROM \`fivetran-499011.salesforce_marketing_cloud.ext_campaign_audience\`;"
