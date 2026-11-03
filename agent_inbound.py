"""Answer inbound Vobiz calls with a LiveKit voice agent."""

import logging
from pathlib import Path

from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    TurnHandlingOptions,
    cli,
    inference,
)
from livekit.agents.beta import EndCallTool

load_dotenv(Path(__file__).resolve().parent / ".env.local")

logger = logging.getLogger("vobiz-inbound")

# Must match AGENT_NAME in setup_inbound.py.
AGENT_NAME = "voice-assistant"


class VoiceAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a friendly voice AI assistant answering a phone call. "
                "Keep replies to one or two short sentences, and do not use lists, markdown or "
                "emojis. Say you are an AI assistant if you are asked. "
                "When the caller is finished, say goodbye and end the call."
            ),
            tools=[EndCallTool()],
        )


server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}

    session: AgentSession = AgentSession(
        stt=inference.STT("deepgram/nova-3", language="multi"),
        llm=inference.LLM("openai/gpt-4.1-mini"),
        tts=inference.TTS("cartesia/sonic-3", voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"),
        turn_handling=TurnHandlingOptions(turn_detection=inference.TurnDetector()),
    )

    await session.start(agent=VoiceAssistant(), room=ctx.room)

    # sip.callIDFull equals bridge_uuid in the Vobiz CDR, so log it to join the two records.
    for participant in ctx.room.remote_participants.values():
        if call_id := participant.attributes.get("sip.callIDFull"):
            logger.info("inbound call connected", extra={"sip_call_id": call_id})

    # The caller is already in the room, so the agent speaks first.
    await session.generate_reply(
        instructions="Greet the caller, say you are an AI assistant, and ask how you can help."
    )


if __name__ == "__main__":
    cli.run_app(server)
