"""Create the LiveKit inbound trunk and dispatch rule for a Vobiz number."""

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from livekit import api

load_dotenv(Path(__file__).resolve().parent / ".env.local")

AGENT_NAME = "voice-assistant"  # must match AGENT_NAME in agent_inbound.py


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is not set in .env.local")
    return value


async def remove_existing(lkapi: api.LiveKitAPI, trunk_ids: list[str]) -> None:
    rules = await lkapi.sip.list_dispatch_rule(api.ListSIPDispatchRuleRequest())
    for rule in rules.items:
        if set(rule.trunk_ids) & set(trunk_ids):
            await lkapi.sip.delete_dispatch_rule(
                api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule.sip_dispatch_rule_id)
            )
            print(f"Deleted dispatch rule {rule.sip_dispatch_rule_id}")
    for trunk_id in trunk_ids:
        await lkapi.sip.delete_trunk(api.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id))
        print(f"Deleted inbound trunk {trunk_id}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="delete any inbound trunk that already claims this number, and its dispatch rules",
    )
    args = parser.parse_args()

    number = require_env("VOBIZ_INBOUND_NUMBER")
    subdomain = require_env("LIVEKIT_SIP_SUBDOMAIN")

    lkapi = api.LiveKitAPI()
    try:
        existing = await lkapi.sip.list_inbound_trunk(api.ListSIPInboundTrunkRequest())
        conflicts = [t.sip_trunk_id for t in existing.items if number in t.numbers]
        if conflicts and not args.replace:
            raise SystemExit(
                f"{number} is already on inbound trunk {', '.join(conflicts)}. "
                "Re-run with --replace to delete it and its dispatch rules."
            )
        if conflicts:
            await remove_existing(lkapi, conflicts)

        trunk = await lkapi.sip.create_inbound_trunk(
            api.CreateSIPInboundTrunkRequest(
                trunk=api.SIPInboundTrunkInfo(
                    name="Vobiz inbound", numbers=[number], krisp_enabled=True
                )
            )
        )
        # Each caller gets a new room, and the agent is dispatched into it.
        rule = await lkapi.sip.create_dispatch_rule(
            api.CreateSIPDispatchRuleRequest(
                dispatch_rule=api.SIPDispatchRuleInfo(
                    name="Vobiz inbound to agent",
                    trunk_ids=[trunk.sip_trunk_id],
                    rule=api.SIPDispatchRule(
                        dispatch_rule_individual=api.SIPDispatchRuleIndividual(room_prefix="call-")
                    ),
                    room_config=api.RoomConfiguration(
                        agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)]
                    ),
                )
            )
        )
    finally:
        await lkapi.aclose()

    print(f"Inbound trunk: {trunk.sip_trunk_id}")
    print(f"Dispatch rule: {rule.sip_dispatch_rule_id}")
    print()
    print("Set this as the Primary URI of your Vobiz inbound trunk (no sip: prefix):")
    print(f"  {subdomain}.sip.livekit.cloud")


if __name__ == "__main__":
    asyncio.run(main())
