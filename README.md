# LinkHarbor for Minecraft Bedrock (and plugin-free Java)

A single-file Python agent that pings your Minecraft server from the outside
and pushes the state to your [LinkHarbor](https://linkharbor.com) bio page —
a game-server card with Online/Offline, "3 / 20" players, version and MOTD,
plus push notifications when the player count changes.

Nothing to install on the server: it speaks the protocols the game client
uses for the server list.

* **Bedrock** (Bedrock Dedicated Server, Nukkit, PocketMine, Geyser): RakNet
  unconnected ping, UDP 19132.
* **Java** without a plugin (vanilla, Fabric, Forge, …): Server List Ping,
  TCP 25565 — add `--java`. Running Paper? The plugin in
  [integration-minecraft](https://github.com/linkharbor/integration-minecraft)
  gives you real join/leave events with player names instead.

Standard library only, Python 3.10+. Part of the
[LinkHarbor integrations](https://github.com/linkharbor/integrations)
family (one repo per game).

## Setup

```bash
git clone https://github.com/linkharbor/integration-minecraft-bedrock
cd integration-minecraft-bedrock

export LH_INGEST_URL="https://api.linkharbor.com/v1/ingest/123"   # dashboard → Integrations → Custom (API)
export LH_INGEST_SECRET="…"

python3 agent.py --host play.example.com --port 19132 \
  --address "play.example.com:19132" --url "https://discord.gg/xyz"

# Java server without a plugin:
python3 agent.py --java --host play.example.com --port 25565 --address "play.example.com"
```

Try `--once -v` first. Run it as a service with
`integration-minecraft-bedrock.service` (systemd; secrets go into
`/etc/integration-minecraft-bedrock.env`, `chmod 600`).

## Events sent

| Event | When | Template variables |
|---|---|---|
| `server.online` | first successful ping, or back after being unreachable | `{name}`, `{players_online}`, `{players_max}`, `{version}` |
| `server.offline` | the server stopped answering | `{name}` |
| `players.changed` | the player count changed | `{players_online}`, `{delta}` (+1 / -2), `{name}` |

The ping protocols don't say *who* joined, so there is no `player.joined`
with a name here (Java lists a sample of names on the card). The state is sent
with every event and every `--heartbeat` minutes (default 10).

Suggested push rule (dashboard → Integrations → Push rules → Custom (API) →
`players.changed`): batch window 10 min, title "🎮 {name}", body
"{players_online} players online", minimum pause 15 min.

## Options

```
--host HOST            server IP / hostname (required)
--port PORT            port (default 19132 Bedrock, 25565 Java)
--java                 query a Java server (Server List Ping)
--name NAME            card title (default: MOTD first line)
--address ADDRESS      address shown on the card
--url URL              link behind the card's button
--cta TEXT             button label (default "Join server")
--image-url URL        banner image (large layout)
--interval SECONDS     ping interval (default 60, min 5)
--heartbeat MINUTES    state-only update interval (default 10, 0 = only on change)
--once                 ping once, send, exit
-v                     verbose logging
```

## License

[MIT](LICENSE) — © 2026 EMI Solutions OÜ.
