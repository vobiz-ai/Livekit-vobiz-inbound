# Vobiz + LiveKit: inbound voice agent

Answer calls to a Vobiz phone number with a [LiveKit Agents](https://docs.livekit.io/agents/) voice assistant.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![LiveKit Agents 1.8](https://img.shields.io/badge/LiveKit%20Agents-1.8-00C2FF.svg)](https://docs.livekit.io/agents/)

```
Caller --PSTN--> Vobiz trunk --SIP--> LiveKit inbound trunk --> dispatch rule --> room + agent
```

To place calls instead, see [LiveKit-Vobiz-Outbound](https://github.com/vobiz-ai/LiveKit-Vobiz-Outbound).

## Prerequisites

- Python 3.10 or newer
- A [LiveKit Cloud](https://cloud.livekit.io) project
- A [Vobiz](https://console.vobiz.ai) account with a phone number

The agent uses [LiveKit Inference](https://docs.livekit.io/agents/models/) for speech and language models, so you don't need separate model provider keys.

## Set up

### 1. Install

```bash
git clone https://github.com/vobiz-ai/Livekit-vobiz-inbound.git
cd Livekit-vobiz-inbound
uv venv && uv pip install -r requirements.txt
cp .env.example .env.local
```

Fill in `.env.local`. Copy `LIVEKIT_SIP_SUBDOMAIN` from the SIP URI on your [LiveKit project settings](https://cloud.livekit.io/projects/p_/settings/project) page. It can differ from the subdomain in `LIVEKIT_URL`.

### 2. Configure LiveKit

```bash
uv run python setup_inbound.py
```

This creates an inbound trunk for your number and a dispatch rule that sends each caller to a new room with the agent. It prints the LiveKit SIP host for the next step.

If the number is already on a LiveKit trunk, the script stops without changing anything. Run it with `--replace` to delete that trunk and its dispatch rules.

### 3. Configure Vobiz

In the [Vobiz Console](https://console.vobiz.ai):

1. Under **SIP Trunk > Origination URI**, add the host printed in step 2, with no `sip:` prefix, and set **Transport** to `UDP`.
2. Under **SIP Trunk > Inbound Trunk**, create a trunk and select that URI as the **Primary URI**.
3. Link your phone number to the trunk. If the number is attached to a voice application, detach it first.

### 4. Run the agent

```bash
uv run python agent_inbound.py dev
```

### 5. Test

Call your Vobiz number. The agent answers and introduces itself.

## Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `LIVEKIT_URL` | Yes | LiveKit project URL |
| `LIVEKIT_API_KEY` | Yes | LiveKit API key |
| `LIVEKIT_API_SECRET` | Yes | LiveKit API secret |
| `LIVEKIT_SIP_SUBDOMAIN` | Yes | The subdomain of your LiveKit SIP URI |
| `VOBIZ_INBOUND_NUMBER` | Yes | Your Vobiz number in E.164 format |

To change the voice, models or prompt, edit `agent_inbound.py`. The name `voice-assistant` appears in both Python files and must match.

## Match calls to Vobiz records

The agent logs each call's `sip_call_id`. It equals `bridge_uuid` in the Vobiz call record, so you can join the two.

## Security

- The trunk accepts calls from any address that presents your number. For production, restrict it with [`allowed_addresses`](https://docs.livekit.io/telephony/accepting-calls/inbound-trunk/), using the [Vobiz SIP signaling IPs](https://www.vobiz.ai/docs/concepts/ip-whitelisting). LiveKit has to enable this field on your project.
- Keep `.env.local` out of version control. It's already in `.gitignore`.
- Callers should know they're talking to an AI. The default greeting says so.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| The call fails and nothing reaches LiveKit | The Primary URI must be the printed host, with no `sip:` prefix and **Transport** set to `UDP` |
| No dispatch rule matches | The number on the LiveKit trunk must exactly match your Vobiz number, in E.164 format |
| The call connects but there's silence | Check that the worker is running and registered, on the same LiveKit project as `setup_inbound.py` |

## Learn more

- [Vobiz LiveKit integration guide](https://www.vobiz.ai/docs/integrations/livekit)
- [LiveKit SIP trunk setup](https://docs.livekit.io/telephony/start/sip-trunk-setup/)
- [Outbound calling example](https://github.com/vobiz-ai/LiveKit-Vobiz-Outbound)

## License

[MIT](./LICENSE) © Vobiz. Questions: open an issue or email [piyush@vobiz.ai](mailto:piyush@vobiz.ai).
