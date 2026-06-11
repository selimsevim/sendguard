# SendGuard -- ADK web UI on Cloud Run
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The agent package and the forked Fivetran MCP server it spawns over stdio
COPY agent/ agent/
COPY fivetran-mcp/ fivetran-mcp/

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

# adk web serves every agent package found in agent/ (i.e. "sendguard")
CMD ["sh", "-c", "adk web --host 0.0.0.0 --port ${PORT:-8080} agent"]
