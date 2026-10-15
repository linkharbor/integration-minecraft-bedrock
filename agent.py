#!/usr/bin/env python3
"""LinkHarbor agent for Minecraft Bedrock servers (and Java servers without a plugin).

Pings the server from outside — no plugin, no mod, no server access needed —
and pushes the state to a LinkHarbor "Custom (API)" integration: a live
game-server card on your bio page (Online/Offline, "3 / 20" players, version,
MOTD) and push notifications when the player count changes.

Bedrock (Bedrock Dedicated Server, Nukkit, PocketMine, Geyser): the RakNet
"unconnected ping" on UDP 19132. Java (vanilla, Paper, Fabric, …): the
Server List Ping on TCP 25565 — use --java. Neither protocol exposes who
joined (only counts; Java lists a sample), so the events are count-based.
For Java servers with Paper, the plugin in integration-minecraft gives you
real join/leave events with names.

    export LH_INGEST_URL="https://api.linkharbor.com/v1/ingest/123"
    export LH_INGEST_SECRET="…"
    python3 agent.py --host play.example.com --port 19132 --address "play.example.com:19132"
    python3 agent.py --java --host play.example.com --port 25565

Events sent:
    server.online     answered after being unreachable (or on first run)
    server.offline    stopped answering
    players.changed   the player count changed (data.players_online, data.delta)

Standard library only, Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid

log = logging.getLogger("linkharbor")

RAKNET_MAGIC = bytes.fromhex("00ffff00fefefefefdfdfdfd12345678")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", required=True, help="server IP / hostname")
    p.add_argument("--port", type=int, default=0, help="port (default 19132 Bedrock, 25565 Java)")
    p.add_argument("--java", action="store_true", help="query a Java server (Server List Ping) instead of Bedrock")
    p.add_argument("--name", default="", help="card title (default: the server's MOTD, first line)")
    p.add_argument("--address", default="", help="address shown on the card")
    p.add_argument("--url", default="", help="link behind the card's button")
    p.add_argument("--cta", default="Join server", help="button label")
    p.add_argument("--image-url", default="", help="banner image (large layout)")
    p.add_argument("--interval", type=int, default=60, help="seconds between pings (default 60)")
    p.add_argument("--heartbeat", type=int, default=10, help="minutes between state-only updates (0 = only on change)")
    p.add_argument("--ingest-url", default=os.environ.get("LH_INGEST_URL", ""))
    p.add_argument("--ingest-secret", default=os.environ.get("LH_INGEST_SECRET", ""))
    p.add_argument("--once", action="store_true", help="ping once, send, exit")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args()
    if not a.port:
        a.port = 25565 if a.java else 19132
    if not a.ingest_url or not a.ingest_secret:
        p.error("set LH_INGEST_URL and LH_INGEST_SECRET (or --ingest-url / --ingest-secret)")
    return a


class Ingest:
    def __init__(self, url: str, secret: str) -> None:
        self.url, self.secret = url, secret

    def send(self, event: str | None, data: dict | None, state: dict) -> bool:
        body: dict = {"state": state}
        if event:
            body["event"] = event
            body["event_id"] = f"{event}-{uuid.uuid4()}"
        if data:
            body["data"] = data
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {self.secret}", "Content-Type": "application/json",
                     "User-Agent": "LinkHarbor-MinecraftPing/1.0"},
        )
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(req, timeout=10) as res:
                    log.debug("← %s %s", res.status, res.read(200).decode(errors="replace"))
                    return True
            except urllib.error.HTTPError as e:
                text = e.read(300).decode(errors="replace")
                if e.code == 401:
                    log.error("401 from LinkHarbor — wrong secret or integration disconnected")
                    return False
                if e.code < 500:
                    log.error("%s from LinkHarbor: %s", e.code, text)
                    return False
                log.warning("%s from LinkHarbor (attempt %d)", e.code, attempt)
            except Exception as e:
                log.warning("request failed (attempt %d): %s", attempt, e)
            time.sleep(2)
        return False


def strip_mc_colors(s: str) -> str:
    """Removes §x formatting codes."""
    out, skip = [], False
    for ch in s:
        if skip:
            skip = False
            continue
        if ch == "§":
            skip = True
            continue
        out.append(ch)
    return "".join(out).strip()


def ping_bedrock(host: str, port: int) -> dict | None:
    """RakNet unconnected ping → {motd, version, players, max_players, sub_motd}."""
    packet = b"\x01" + struct.pack(">Q", int(time.time() * 1000) & 0xFFFFFFFFFFFFFFFF) + RAKNET_MAGIC + struct.pack(">Q", 0x1234567890ABCDEF)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(3.0)
            s.sendto(packet, (host, port))
            data, _ = s.recvfrom(4096)
    except Exception as e:
        log.debug("bedrock ping failed: %s", e)
        return None
    if not data or data[0] != 0x1C or len(data) < 35:
        return None
    length = struct.unpack(">H", data[33:35])[0]
    text = data[35:35 + length].decode("utf-8", errors="replace")
    # MCPE;motd;protocol;version;online;max;serverId;subMotd;gamemode;gamemodeNum;portv4;portv6
    f = text.split(";")
    if len(f) < 6:
        return None
    try:
        return {
            "motd": strip_mc_colors(f[1]),
            "version": f[3],
            "players": int(f[4]),
            "max_players": int(f[5]),
            "sub_motd": strip_mc_colors(f[7]) if len(f) > 7 else "",
            "sample": [],
        }
    except ValueError:
        return None


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_varint(sock: socket.socket) -> int:
    n, shift = 0, 0
    while True:
        b = sock.recv(1)
        if not b:
            raise ConnectionError("eof")
        n |= (b[0] & 0x7F) << shift
        if not b[0] & 0x80:
            return n
        shift += 7


def ping_java(host: str, port: int) -> dict | None:
    """Server List Ping (protocol 47+) → same shape as ping_bedrock()."""
    try:
        with socket.create_connection((host, port), timeout=3.0) as s:
            s.settimeout(3.0)
            hb = host.encode()
            handshake = b"\x00" + _varint(47) + _varint(len(hb)) + hb + struct.pack(">H", port) + b"\x01"
            s.sendall(_varint(len(handshake)) + handshake + b"\x01\x00")
            _read_varint(s)           # packet length
            if _read_varint(s) != 0:  # packet id
                return None
            n = _read_varint(s)
            buf = b""
            while len(buf) < n:
                chunk = s.recv(n - len(buf))
                if not chunk:
                    break
                buf += chunk
            st = json.loads(buf.decode("utf-8", errors="replace"))
    except Exception as e:
        log.debug("java ping failed: %s", e)
        return None
    desc = st.get("description", "")
    if isinstance(desc, dict):
        desc = desc.get("text", "") + "".join(x.get("text", "") for x in desc.get("extra", []) if isinstance(x, dict))
    players = st.get("players", {}) or {}
    return {
        "motd": strip_mc_colors(str(desc)).split("\n")[0],
        "version": str((st.get("version") or {}).get("name", "")),
        "players": int(players.get("online", 0) or 0),
        "max_players": int(players.get("max", 0) or 0),
        "sub_motd": "",
        "sample": [str(p.get("name", "")) for p in players.get("sample", []) or [] if isinstance(p, dict)],
    }


def build_state(a: argparse.Namespace, info: dict | None, last_name: str) -> dict:
    s: dict = {"type": "game_server", "name": a.name or (info or {}).get("motd") or last_name or "Minecraft Server", "game": "Minecraft"}
    if a.address:
        s["address"] = a.address
    if a.url:
        s["url"] = a.url
    if a.cta:
        s["cta"] = a.cta
    if a.image_url:
        s["image_url"] = a.image_url
    if info is None:
        s.update(online=False, players_online=0, players=[])
        return s
    s.update(online=True, players_online=info["players"], players_max=info["max_players"],
             players=info["sample"][:50], version=info["version"])
    if info.get("sub_motd"):
        s["description"] = info["sub_motd"][:200]
    return s


def main() -> int:
    a = parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ingest = Ingest(a.ingest_url, a.ingest_secret)
    ping = ping_java if a.java else ping_bedrock

    online: bool | None = None
    last_count: int | None = None
    last_name = ""
    last_sent = 0.0
    heartbeat_s = a.heartbeat * 60

    while True:
        info = ping(a.host, a.port)
        now_online = info is not None
        if info:
            last_name = info["motd"] or last_name
        state = build_state(a, info, last_name)

        events: list[tuple[str, dict | None]] = []
        if online is None or now_online != online:
            events.append(("server.online" if now_online else "server.offline", None))
        elif now_online and last_count is not None and info["players"] != last_count:
            events.append(("players.changed", {"players_online": info["players"], "delta": info["players"] - last_count}))

        if events:
            for ev, data in events:
                log.info("%s %s", ev, data or "")
                ingest.send(ev, data, state)
            last_sent = time.time()
        elif heartbeat_s and time.time() - last_sent >= heartbeat_s:
            log.info("heartbeat: %s players online", state.get("players_online", 0))
            ingest.send(None, None, state)
            last_sent = time.time()

        online = now_online
        last_count = info["players"] if info else None
        if a.once:
            return 0
        time.sleep(max(5, a.interval))


if __name__ == "__main__":
    sys.exit(main())
