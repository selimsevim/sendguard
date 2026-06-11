#!/usr/bin/env python3
"""End-to-end smoke test: run one SendGuard turn through ADK + Gemini + MCP."""
import asyncio
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from sendguard.agent import root_agent

PROMPT = sys.argv[1] if len(sys.argv) > 1 else (
    "Quick pipeline health check: how fresh is the Fivetran SFMC connection? "
    "Just check freshness and report, nothing else."
)


async def main():
    runner = InMemoryRunner(agent=root_agent)
    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id="smoke")
    async for event in runner.run_async(
            user_id="smoke", session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=PROMPT)])):
        if event.content and event.content.parts:
            for p in event.content.parts:
                if p.text:
                    print(f"[{event.author}] {p.text}")
                if p.function_call:
                    print(f"[{event.author}] -> tool: {p.function_call.name}({dict(p.function_call.args or {})})")
                if p.function_response:
                    out = str(p.function_response.response)
                    print(f"[{event.author}] <- {p.function_response.name}: {out[:300]}")


if __name__ == "__main__":
    asyncio.run(main())
