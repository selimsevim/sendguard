#!/usr/bin/env python3
"""Full dress rehearsal: drive the complete validate->hold->repair->release
flow with scripted human approvals, printing the whole transcript."""
import asyncio

from google.adk.runners import InMemoryRunner
from google.genai import types

from sendguard.agent import root_agent

TURNS = [
    "Campaign CAMP-2026-SUMMER-LAUNCH is scheduled to send to audience DE "
    "campaign_audience. Validate and clear it.",
    "Yes, approved. Proceed with the repair plan: build the repaired audience, "
    "push it back to SFMC via Activations, verify, and report back.",
    "Approved. Proceed.",
    "Yes, release the send.",
]


async def main():
    runner = InMemoryRunner(agent=root_agent)
    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id="rehearsal")
    for turn in TURNS:
        print(f"\n{'='*80}\nUSER: {turn}\n{'='*80}")
        async for event in runner.run_async(
                user_id="rehearsal", session_id=session.id,
                new_message=types.Content(role="user", parts=[types.Part(text=turn)])):
            if not (event.content and event.content.parts):
                continue
            for p in event.content.parts:
                if p.text:
                    print(f"\n[AGENT] {p.text.strip()}")
                if p.function_call:
                    print(f"  -> {p.function_call.name}({dict(p.function_call.args or {})})")
                if p.function_response:
                    out = str(p.function_response.response)
                    print(f"  <- {out[:240]}")


if __name__ == "__main__":
    asyncio.run(main())
