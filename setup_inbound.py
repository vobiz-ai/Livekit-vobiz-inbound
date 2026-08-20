"""
Setup LiveKit inbound trunk and dispatch rule for Vobiz calls.
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from livekit import api
from livekit.protocol import sip as sip_proto

load_dotenv(Path(__file__).resolve().parent / ".env.local")

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
VOBIZ_INBOUND_NUMBER = os.getenv("VOBIZ_INBOUND_NUMBER", "+15550003333")
AGENT_NAME = "voice-assistant"

async def main():
    lk = api.LiveKitAPI()
    
    project_id = LIVEKIT_URL.replace("wss://", "").replace("ws://", "").split(".")[0]
    sip_endpoint = f"{project_id}.sip.livekit.cloud"
    
    print("="*60)
    print("LIVEKIT INBOUND SETUP")
    print("="*60)
    print(f"\nProject: {project_id}")
    print(f"SIP Endpoint: {sip_endpoint}")
    print(f"Inbound Number: {VOBIZ_INBOUND_NUMBER}")
    
    try:
        print(f"\n[1] Checking for existing configuration for {VOBIZ_INBOUND_NUMBER}...")
        
        # 1. List all trunks to find conflicts
        trunks = await lk.sip.list_sip_inbound_trunk(api.ListSIPInboundTrunkRequest())
        trunks_to_delete = []
        
        for t in trunks.items:
            # Check if this trunk uses our target number
            if t.numbers and VOBIZ_INBOUND_NUMBER in t.numbers:
                print(f"    Found conflicting trunk: {t.sip_trunk_id} (Name: {t.name})")
                trunks_to_delete.append(t.sip_trunk_id)
        
        # 2. If conflicts found, clean up dependencies first
        if trunks_to_delete:
            print("    Resolving conflicts...")
            
            # Find dispatch rules linked to these trunks
            rules = await lk.sip.list_sip_dispatch_rule(api.ListSIPDispatchRuleRequest())
            for r in rules.items:
                if any(trunk_id in r.trunk_ids for trunk_id in trunks_to_delete):
                    print(f"    Deleting linked dispatch rule: {r.sip_dispatch_rule_id} (Name: {r.name})")
                    await lk.sip.delete_sip_dispatch_rule(
                        api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=r.sip_dispatch_rule_id)
                    )

            # Now delete the trunks
            for trunk_id in trunks_to_delete:
                print(f"    Deleting conflicting trunk: {trunk_id}")
                await lk.sip.delete_sip_trunk(
                    api.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id)
                )
            print("    Cleanup complete.")
        else:
            print("    No conflicting configuration found.")
        
        # Create Inbound Trunk
        print(f"\n[2] Creating inbound trunk for {VOBIZ_INBOUND_NUMBER}...")
        trunk = await lk.sip.create_sip_inbound_trunk(
            api.CreateSIPInboundTrunkRequest(
                trunk=api.SIPInboundTrunkInfo(
                    name="Vobiz Inbound",
                    numbers=[VOBIZ_INBOUND_NUMBER],
                    allowed_addresses=["0.0.0.0/0"],  # Accept from any IP
                    krisp_enabled=True,
                )
            )
        )
        trunk_id = trunk.sip_trunk_id
        print(f"    Created: {trunk_id}")
        
        # Create Dispatch Rule with agent dispatch
        print(f"\n[3] Creating dispatch rule for agent '{AGENT_NAME}'...")
        dispatch_rule = sip_proto.SIPDispatchRuleInfo(
            name="Inbound Agent Dispatch",
            trunk_ids=[trunk_id],
            rule=sip_proto.SIPDispatchRule(
                dispatch_rule_individual=sip_proto.SIPDispatchRuleIndividual(
                    room_prefix="call-",
                )
            ),
        )
        dispatch_rule.room_config.CopyFrom(
            api.RoomConfiguration(
                agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)]
            )
        )
        
        result = await lk.sip.create_sip_dispatch_rule(
            api.CreateSIPDispatchRuleRequest(dispatch_rule=dispatch_rule)
        )
        print(f"    Created: {result.sip_dispatch_rule_id}")
        
        # Summary
        print("\n" + "="*60)
        print("SETUP COMPLETE")
        print("="*60)
        print(f"""
Inbound Trunk: {trunk_id}
  Number: {VOBIZ_INBOUND_NUMBER}
  
Dispatch Rule: {result.sip_dispatch_rule_id}
  Agent: {AGENT_NAME}

IMPORTANT - Set Vobiz Primary URI to:
  {sip_endpoint}
""")
        
    finally:
        await lk.aclose()

if __name__ == "__main__":
    asyncio.run(main())
