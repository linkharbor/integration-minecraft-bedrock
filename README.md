# LinkHarbor for Minecraft Bedrock (and Java without a plugin)

A single-file Python agent that pings your Minecraft server from outside and shows it on your [LinkHarbor](https://linkharbor.com) bio page: online or offline, "3 / 20" players, version and MOTD. When the player count changes, your followers can get a push notification.

Nothing is installed on the server. The agent speaks the same protocols the game client uses for the server list.

* Bedrock (Bedrock Dedicated Server, Nukkit, PocketMine, Geyser): RakNet unconnected ping on UDP 19132.
* Java without a plugin (vanilla, Fabric, Forge and others): Server List Ping on TCP 25565, add `--java`. If you run Paper, the plugin in [integration-minecraft](https://github.com/linkharbor/integration-minecraft) gives you join and leave events with player names.

Python 3.10 or newer, standard library only. Part of the [LinkHarbor integrations](https://github.com/linkharbor/integrations) family, one repo per game.

## Setup

```bash
git clone https://github.com/linkharbor/integration-minecraft-bedrock
cd integration-minecraft-bedrock

export LH_INGEST_URL="https://dock.at-harbor.com/v1/ingest/123"   # dashboard: Integrations, Custom (API)
export LH_INGEST_SECRET="…"

python3 agent.py --host play.example.com --port 19132 \
  --address "play.example.com:19132" --url "https://discord.gg/xyz"

# Java server without a plugin
python3 agent.py --java --host play.example.com --port 25565 --address "play.example.com"
```

Start with `--once -v`. Then run it as a service, see `integration-minecraft-bedrock.service` for systemd; the secrets go into `/etc/integration-minecraft-bedrock.env` with `chmod 600`.

## Events sent

| Event | When | Template variables |
|---|---|---|
| `server.online` | the first successful ping, or the server is back after being unreachable | `{name}`, `{players_online}`, `{players_max}`, `{version}` |
| `server.offline` | the server stopped answering | `{name}` |
| `players.changed` | the player count changed | `{players_online}`, `{delta}` (+1, -2), `{name}` |

The ping protocols do not say who joined, so there is no `player.joined` with a name here. Java servers return a sample of names, which the card shows. The state is sent with every event and every `--heartbeat` minutes (default 10).

Suggested push rule (dashboard, Integrations, Push rules, Custom (API), event `players.changed`): batch window 10 minutes, title "🎮 {name}", body "{players_online} players online", minimum pause 15 minutes.

## Options

```
--host HOST            server IP or hostname (required)
--port PORT            port (default 19132 for Bedrock, 25565 for Java)
--java                 query a Java server (Server List Ping)
--name NAME            card title (default: first line of the MOTD)
--address ADDRESS      address shown on the card
--url URL              link behind the card's button
--cta TEXT             button label (default "Join server")
--image-url URL        banner image for the large layout
--interval SECONDS     ping interval (default 60, minimum 5)
--heartbeat MINUTES    state-only update interval (default 10, 0 = only on change)
--once                 ping once, send, exit
-v                     verbose logging
```

## License

[MIT](LICENSE). © 2026 EMI Solutions OÜ.
