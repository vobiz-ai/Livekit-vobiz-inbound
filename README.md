# Vobiz + LiveKit — Inbound Voice Agent

Answer inbound PSTN calls on a Vobiz number with a LiveKit Agents voice assistant: Vobiz hands the call to LiveKit over SIP, a dispatch rule creates a room, and your Python agent joins it and starts talking.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)](https://www.python.org/)
[![Docs](https://img.shields.io/badge/Docs-docs.vobiz.ai-0A7CFF.svg)](https://docs.vobiz.ai)

## Overview

This repository is a minimal, complete example of the *inbound* half of a telephony voice agent. A caller dials a phone number you own on Vobiz. Vobiz terminates the PSTN leg and forwards the call over SIP to your LiveKit project's SIP endpoint. LiveKit matches the called number against an inbound trunk, a dispatch rule places the SIP participant into a freshly created room, and the same rule asks LiveKit to dispatch a named agent worker into that room. Your agent process — already running and registered — picks up the job, joins, and greets the caller.

The example ships two Python files that map directly onto those two halves. `setup_inbound.py` is a one-off provisioning script that talks to the LiveKit server API to create the inbound trunk and the dispatch rule. `agent_inbound.py` is the long-running worker that holds the conversation, wiring Deepgram for speech-to-text, OpenAI for the language model and text-to-speech, and Silero for voice-activity detection into a single `AgentSession`.

It is aimed at developers who already have a Vobiz SIP trunk and a number, and who want the shortest path from "a call arrives" to "an AI answers". Everything is intentionally small: there is no database, no web server, and no call-control API in the loop. The telephony configuration lives in Vobiz, the routing configuration lives in LiveKit, and the conversational logic lives in one class you can edit.

For placing calls in the other direction — dialling out from an agent to a phone number over the same Vobiz trunk — see the companion repository [`LiveKit-Vobiz-Outbound`](https://github.com/vobiz-ai/LiveKit-Vobiz-Outbound). The two are designed to be read together: outbound provisions a LiveKit *outbound* trunk with your Vobiz SIP credentials and dispatches an agent to a room before creating the SIP participant; inbound provisions an *inbound* trunk keyed on your number and lets the dispatch rule create the room for you. A single project can run both side by side against the same Vobiz trunk.

## What you can build with it

- **An always-on support line.** Point a published number at the agent so callers reach a voice assistant instead of a queue, at any hour.
- **Front-line triage before a human.** Let the agent collect the caller's name, account reference, and reason for calling, then route onward with the context already gathered.
- **A multilingual reception desk.** The STT stage is configured with Deepgram's `nova-3` model in `multi` language mode, so callers can speak in different languages on the same number.
- **An after-hours overflow number.** Publish a second Vobiz number that only forwards to LiveKit outside business hours, and let the agent take messages.
- **Voice access to an internal system.** Extend `VoiceAssistant` with LiveKit Agents function tools so the caller can check an order, a booking, or a ticket by voice.
- **A repeatable test harness for SIP routing.** Because the trunk and dispatch rule are created from code, you can tear down and re-provision inbound routing as often as you like while testing.

## How it works

An inbound call crosses three systems. Vobiz owns the number and the PSTN interconnect; LiveKit owns the SIP ingress, the room, and the agent dispatch; your Python worker owns the conversation.

```
  ┌──────────┐   PSTN    ┌─────────────┐    SIP     ┌────────────────────────┐
  │  Caller  │──────────▶│    Vobiz    │───────────▶│  LiveKit SIP endpoint  │
  └──────────┘  dials    │  SIP trunk  │  Primary   │ <project>.sip.livekit  │
                your DID │  + number   │    URI     │        .cloud          │
                         └─────────────┘            └───────────┬────────────┘
                                                                │ number matches
                                                                │ inbound trunk
                                                                ▼
                                              ┌──────────────────────────────┐
                                              │  Dispatch rule (individual)  │
                                              │  room_prefix = "call-"       │
                                              │  room_config.agents =        │
                                              │    [ "voice-assistant" ]     │
                                              └───────────────┬──────────────┘
                                                              │ creates room,
                                                              │ dispatches agent
                                                              ▼
   ┌───────────────────────────────────────────────────────────────────────┐
   │  LiveKit room  "call-…"                                               │
   │   ├── SIP participant  (the caller's audio)                           │
   │   └── Agent participant  → agent_inbound.py                           │
   │         Silero VAD → Deepgram STT → OpenAI LLM → OpenAI TTS           │
   └───────────────────────────────────────────────────────────────────────┘
```

Step by step:

1. The caller dials the number linked to your Vobiz SIP trunk.
2. Vobiz forwards the INVITE to the **Primary URI** configured on that trunk — your LiveKit project's SIP endpoint, printed for you at the end of `setup_inbound.py`.
3. LiveKit looks at the called number and matches it against the inbound trunk created by `setup_inbound.py`, which was registered with `numbers=[VOBIZ_INBOUND_NUMBER]`.
4. The dispatch rule attached to that trunk is a `SIPDispatchRuleIndividual` with `room_prefix="call-"`, so every caller lands in their own room named with that prefix.
5. The same rule carries a `RoomConfiguration` containing `RoomAgentDispatch(agent_name="voice-assistant")`. That is what turns a plain SIP room into an agent call: LiveKit dispatches the worker registered under the name `voice-assistant`.
6. `agent_inbound.py`, running as a worker with `WorkerOptions(agent_name="voice-assistant")`, receives the job and its `entrypoint` is invoked with the room's `JobContext`.
7. The entrypoint builds an `AgentSession` (Silero VAD, Deepgram STT, OpenAI LLM, OpenAI TTS), starts it against `ctx.room`, and then calls `session.generate_reply(...)` so the agent speaks first rather than waiting for the caller.

Two details are worth internalising because they are the usual source of "the call connects but nothing happens":

- **The agent name is a contract.** `agent_name` in `WorkerOptions` must equal the `agent_name` in the dispatch rule's `RoomAgentDispatch`. Both are `voice-assistant` in this example. Setting `agent_name` at all means the worker is *explicitly* dispatched — it will not automatically join rooms it was not dispatched to.
- **The agent greets first.** For an inbound call the SIP participant is already in the room by the time the agent joins, so the entrypoint does not wait for a participant to connect; it generates a greeting immediately. The `generate_reply` call is wrapped in a `try/except RuntimeError` because a caller who hangs up during setup will close the session underneath it.

## Architecture

| File | Responsibility |
|------|----------------|
| `setup_inbound.py` | One-off provisioning. Deletes any inbound trunk already claiming your number (and its dispatch rules), creates a fresh `SIPInboundTrunkInfo` named `Vobiz Inbound`, creates the individual dispatch rule with agent dispatch, and prints the LiveKit SIP endpoint you must paste into the Vobiz trunk's Primary URI. |
| `agent_inbound.py` | The long-running worker. Defines `VoiceAssistant(Agent)` with the system instructions, builds the `AgentSession` pipeline, starts it against the room, and generates the opening greeting. Registered under `agent_name="voice-assistant"`. |
| `.env.example` | Template for the credentials and numbers. Copy it to `.env.local` — that is the filename both scripts load. |
| `requirements.txt` | Python dependencies: `livekit-agents`, `livekit-plugins-openai`, `livekit-plugins-deepgram`, `livekit-plugins-silero`, `aiohttp`, `python-dotenv`. |
| `.gitignore` | Keeps `.env` and `.env.local` out of version control. |

Inside `agent_inbound.py` the conversational pipeline is assembled from four components:

| Stage | Implementation | Configured as |
|-------|----------------|---------------|
| Voice activity detection | Silero | `silero.VAD.load()` |
| Speech-to-text | Deepgram | `model="nova-3"`, `language="multi"` |
| Language model | OpenAI | `model="gpt-4o-mini"` |
| Text-to-speech | OpenAI | `model="tts-1"`, `voice="alloy"` |

These are set in code rather than read from the environment, so change them by editing the `AgentSession(...)` call.

## Prerequisites

- **Python 3.9 or newer.** [`uv`](https://github.com/astral-sh/uv) is convenient for creating the environment and running the scripts, but a plain `venv` works just as well.
- **A Vobiz account** with a SIP trunk and at least one phone number linked to it. Sign up at [vobiz.ai](https://vobiz.ai); trunk setup is covered in the [Vobiz documentation](https://docs.vobiz.ai).
- **A LiveKit Cloud project** (or a self-hosted LiveKit deployment with SIP enabled). You need the project URL, API key, and API secret from [cloud.livekit.io](https://cloud.livekit.io).
- **A Deepgram API key** for speech-to-text.
- **An OpenAI API key** for the language model and text-to-speech.

No public tunnel (ngrok or similar) is required. Nothing in this repository listens for inbound HTTP; the media and signalling paths are SIP into LiveKit and WebRTC out to the agent, both of which are outbound connections from your machine.

## Setup

1. **Clone the repository and enter it.**

   ```bash
   git clone https://github.com/vobiz-ai/Livekit-vobiz-inbound.git
   cd Livekit-vobiz-inbound
   ```

2. **Create the environment and install dependencies.**

   ```bash
   uv venv
   uv pip install -r requirements.txt
   ```

   Or with the standard library:

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Create your environment file.** Both scripts load `.env.local` from beside the source file, so the file must be named `.env.local` and sit in the repository root.

   ```bash
   cp .env.example .env.local
   ```

   Fill in the LiveKit credentials, the Deepgram and OpenAI keys, and set `VOBIZ_INBOUND_NUMBER` to the number linked to your Vobiz trunk, in E.164 form.

4. **Provision the LiveKit inbound trunk and dispatch rule.**

   ```bash
   uv run python setup_inbound.py
   ```

   The script is idempotent by demolition: it first lists existing inbound trunks, and if any of them already claims your number it deletes the dispatch rules pointing at them and then the trunks themselves, before creating a clean pair. Read the output — the final block prints the SIP endpoint you need in the next step.

5. **Point Vobiz at LiveKit.** In the Vobiz dashboard, open **SIP Trunks → your trunk** and set the **Primary URI** to the LiveKit SIP endpoint printed by `setup_inbound.py`, in the form `sip:<project-id>.sip.livekit.cloud`. Confirm your phone number is linked to that trunk.

6. **Start the agent worker.**

   ```bash
   uv run python agent_inbound.py dev
   ```

Only step 4 needs repeating, and only when the number or the dispatch configuration changes.

## Configuration

Every variable below is read from `.env.local`. The first group is read directly by the code in this repository or by the LiveKit SDK it calls.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LIVEKIT_URL` | Yes | — | Your LiveKit project WebSocket URL, e.g. `wss://your-project.livekit.cloud`. `setup_inbound.py` also derives the SIP endpoint hostname from it by taking the first label of the host. |
| `LIVEKIT_API_KEY` | Yes | — | LiveKit API key. Read by `api.LiveKitAPI()` in the setup script and by the agent worker when it registers. |
| `LIVEKIT_API_SECRET` | Yes | — | LiveKit API secret, used alongside the key. |
| `VOBIZ_INBOUND_NUMBER` | Yes | `+15550003333` | The number callers dial, in E.164 form. `setup_inbound.py` registers it on the inbound trunk and uses it to find conflicting trunks. The in-code default is a placeholder — always set this explicitly. |
| `DEEPGRAM_API_KEY` | Yes | — | Deepgram key for speech-to-text. `agent_inbound.py` raises `ValueError` at start-up if it is missing. |
| `OPENAI_API_KEY` | Yes | — | OpenAI key for the language model and text-to-speech. Also raises `ValueError` if missing. |

The remaining entries in `.env.example` are there to describe your Vobiz trunk and to reserve names for future options. They are not read by the current code; the model and voice choices are hardcoded in the `AgentSession` constructor, and the SIP credentials belong to the Vobiz side of the configuration or to the outbound companion repository.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VOBIZ_SIP_DOMAIN` | No | — | Your Vobiz trunk domain, e.g. `your-trunk-id.sip.vobiz.ai`. Needed when registering an *outbound* LiveKit trunk; inbound routing does not use it. |
| `VOBIZ_USERNAME` | No | — | SIP username on the Vobiz trunk. Same note as above. |
| `VOBIZ_PASSWORD` | No | — | SIP password on the Vobiz trunk. Same note as above. |
| `VOBIZ_OUTBOUND_NUMBER` | No | — | Caller ID used when dialling out. Relevant to the outbound companion repository. |
| `TTS_PROVIDER` | No | `openai` | Reserved. The pipeline currently constructs `openai.TTS` unconditionally. |
| `OPENAI_TTS_MODEL` | No | `tts-1` | Reserved. The value in code is `tts-1`. |
| `OPENAI_TTS_VOICE` | No | `alloy` | Reserved. The value in code is `alloy`. |
| `OPENAI_STT_MODEL` | No | `whisper-1` | Reserved. Speech-to-text is handled by Deepgram `nova-3` in this example. |
| `OPENAI_LLM_MODEL` | No | `gpt-4o-mini` | Reserved. The value in code is `gpt-4o-mini`. |

Two constants live in the source rather than the environment. `AGENT_NAME` in `setup_inbound.py` and `agent_name` in `agent_inbound.py` are both `"voice-assistant"`; change one and you must change the other. The room prefix `"call-"` is set on the dispatch rule.

## Running it

**Provision routing (once, and after any change to the number):**

```bash
uv run python setup_inbound.py
```

Expected output walks through three numbered stages — the conflict check, the trunk creation, and the dispatch rule creation — then prints a summary containing the trunk ID, the dispatch rule ID, the agent name, and the line `IMPORTANT - Set Vobiz Primary URI to:` followed by your LiveKit SIP endpoint.

**Run the agent in development mode**, which reloads on file changes:

```bash
uv run python agent_inbound.py dev
```

**Run it in production mode**, without the reloader:

```bash
uv run python agent_inbound.py start
```

In either mode the worker registers with LiveKit and then waits. Nothing further is logged until a call arrives. When one does, you should see `[OK] Starting voice assistant for room: call-…` followed by `[OK] Generating greeting for caller...`, and the caller should hear the assistant introduce itself within a second or two.

Place a test call by dialling `VOBIZ_INBOUND_NUMBER` from any phone.

## LiveKit SIP surface used

The setup script uses the LiveKit server SIP API. These are the calls it makes and the fields it sets, all from `livekit.api` and `livekit.protocol.sip`:

| Call | Purpose | Fields set in this example |
|------|---------|----------------------------|
| `list_sip_inbound_trunk(ListSIPInboundTrunkRequest())` | Enumerate existing inbound trunks to find any that already claim the number. | — |
| `list_sip_dispatch_rule(ListSIPDispatchRuleRequest())` | Find dispatch rules bound to a conflicting trunk so they can be removed first. | — |
| `delete_sip_dispatch_rule(DeleteSIPDispatchRuleRequest(...))` | Remove a conflicting dispatch rule. | `sip_dispatch_rule_id` |
| `delete_sip_trunk(DeleteSIPTrunkRequest(...))` | Remove the conflicting trunk. | `sip_trunk_id` |
| `create_sip_inbound_trunk(CreateSIPInboundTrunkRequest(...))` | Create the trunk that accepts calls for your number. | `name="Vobiz Inbound"`, `numbers=[VOBIZ_INBOUND_NUMBER]`, `allowed_addresses=["0.0.0.0/0"]`, `krisp_enabled=True` |
| `create_sip_dispatch_rule(CreateSIPDispatchRuleRequest(...))` | Route matched calls into a per-caller room and dispatch the agent. | `name="Inbound Agent Dispatch"`, `trunk_ids=[trunk_id]`, `SIPDispatchRuleIndividual(room_prefix="call-")`, `room_config.agents=[RoomAgentDispatch(agent_name="voice-assistant")]` |

On the agent side the surface is `livekit.agents`: `Agent` (subclassed as `VoiceAssistant` to carry the `instructions`), `AgentSession` (the STT/LLM/TTS/VAD pipeline), `RoomInputOptions(close_on_disconnect=False)`, `JobContext` (delivered to `entrypoint`), and `agents.cli.run_app(WorkerOptions(entrypoint_fnc=..., agent_name=...))`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Caller hears ringing then a `408 Request Timeout`, and nothing appears in the agent log | The Vobiz trunk's Primary URI does not match your LiveKit SIP endpoint, so the INVITE never reaches LiveKit | Re-run `setup_inbound.py` and copy the endpoint from the `IMPORTANT - Set Vobiz Primary URI to:` line into the Vobiz dashboard, prefixed with `sip:` |
| Call connects, the room is created, but the agent never joins and the caller hears silence | The worker's `agent_name` and the dispatch rule's `RoomAgentDispatch(agent_name=...)` disagree, so LiveKit has no worker to dispatch | Both must be `voice-assistant`. If you renamed one, rename the other and re-run `setup_inbound.py` |
| Call reaches LiveKit but no dispatch rule matches | The number registered on the inbound trunk differs from the number Vobiz is presenting — often an E.164 formatting mismatch | Set `VOBIZ_INBOUND_NUMBER` to the exact E.164 form of the linked number and re-run `setup_inbound.py`; the script's conflict cleanup will replace the old trunk |
| `agent_inbound.py` exits immediately with `ValueError: DEEPGRAM_API_KEY not found in .env.local` or the OpenAI equivalent |  The environment file is missing, or is named `.env` rather than `.env.local` | `cp .env.example .env.local` and fill in the keys; both scripts load `.env.local` specifically |
| `setup_inbound.py` raises `AttributeError` on `LIVEKIT_URL.replace(...)` | `LIVEKIT_URL` is unset, so the value is `None` | Set `LIVEKIT_URL` in `.env.local` to your `wss://…livekit.cloud` project URL |
| The worker starts but never registers, or the setup script fails authenticating | `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` are wrong, or belong to a different project than `LIVEKIT_URL` | Copy all three values from the same project in the LiveKit Cloud console |
| The caller connects but the agent says nothing, and the log shows `[!] Could not generate greeting (session may be closing)` | The caller hung up, or the SIP leg dropped, while the session was still starting | Expected behaviour on an abandoned call. If it happens on every call, check for a media path problem on the Vobiz trunk |
| Callers are transcribed poorly in one language | STT is fixed to Deepgram `nova-3` with `language="multi"` | Set an explicit language on `deepgram.STT(...)` in `agent_inbound.py` if all your callers speak one language |

## Security notes

- `.env.local` holds LiveKit, Deepgram, and OpenAI credentials. It is covered by `.gitignore` alongside `.env`; keep it that way and never commit a filled-in copy. `.env.example` should only ever contain placeholders.
- The inbound trunk is created with `allowed_addresses=["0.0.0.0/0"]`, which accepts SIP traffic from any source address. That is convenient while you are getting the first call through. Before running this on a published number, narrow the list to the Vobiz signalling addresses for your trunk so that only Vobiz can deliver calls to it.
- Inbound call audio is transcribed by Deepgram and sent to OpenAI as text. Anything a caller says — account numbers, card details, health information — leaves your infrastructure. Set your agent's instructions so it does not solicit data you are not prepared to send to those providers, and review each provider's data-retention settings.
- The agent's opening line is your first point of disclosure. Many jurisdictions expect callers to be told they are speaking to an automated system; the default instructions in `VoiceAssistant` introduce it as a voice AI assistant, and that is worth keeping.
- Rotate the LiveKit API key and secret if they are ever pasted into a shared terminal or a support ticket; they grant full control over rooms, trunks, and dispatch rules on the project.

## Roadmap

> Planned improvements to this example. Ideas and pull requests are welcome —
> open an issue to discuss anything here.

- [ ] Read the STT, LLM, and TTS model names from the environment so the `TTS_PROVIDER` and `OPENAI_*` placeholders in `.env.example` become live configuration instead of reserved names.
- [ ] Restrict `allowed_addresses` on the inbound trunk to the Vobiz signalling ranges, sourced from an environment variable rather than the current `0.0.0.0/0`.
- [ ] Make `setup_inbound.py` update an existing trunk in place where possible, instead of deleting and recreating it, so trunk IDs survive re-provisioning.
- [ ] Persist a per-call transcript and outcome, keyed on the room name, so conversations can be reviewed after the caller hangs up.
- [ ] Add function tools to `VoiceAssistant` — a lookup against a backend system and a warm transfer to a human — with a worked example of each.
- [ ] Add tests: a unit test for the SIP endpoint derived from `LIVEKIT_URL`, and an integration test that provisions a trunk against a scratch LiveKit project and tears it down.
- [ ] Emit structured logs and basic metrics (calls answered, time to first word, session duration) so the worker can be monitored in a real deployment.

## Contributing

Issues and pull requests are welcome. If you are changing the SIP provisioning, please describe the LiveKit project state you tested against — trunks and dispatch rules are global to a project, and `setup_inbound.py` deletes conflicting ones.

Before opening a pull request, check that both scripts still import cleanly and that the setup script runs end to end against a scratch project:

```bash
python -m compileall agent_inbound.py setup_inbound.py
uv run python setup_inbound.py
```

Keep `.env.example` in step with any new variable the code reads, and make sure no real numbers, trunk IDs, or keys appear in the diff.

## License

Released under the [MIT License](./LICENSE) © Vobiz.

MIT is permissive: you may use, modify, and redistribute this code, including in
closed-source commercial products, provided the copyright notice and licence text
are retained. There is no warranty. If your organisation needs a different
licensing arrangement, contact [piyush@vobiz.ai](mailto:piyush@vobiz.ai).

## Built by Team Vobiz

[Vobiz](https://vobiz.ai) is a programmable voice and SIP-trunking platform for
voice APIs, SIP trunking, and AI voice agents. This repository is built and
maintained by the Vobiz team.

**Maintainer:** Piyush Sahoo — [piyush@vobiz.ai](mailto:piyush@vobiz.ai) · [LinkedIn](https://www.linkedin.com/in/piyush-s713/)

Questions, or want to talk through an integration? Open an issue on this repo,
or reach out directly at [piyush@vobiz.ai](mailto:piyush@vobiz.ai).

**Useful links:** [Docs](https://docs.vobiz.ai) · [API reference](https://docs.vobiz.ai/api-reference) · [Sign up](https://vobiz.ai)
