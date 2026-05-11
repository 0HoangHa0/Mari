"""
WebSocket Game Server for 2-player co-op online mode.

Chạy bằng: python server/game_server.py [--port 8765]

Protocol (JSON qua WebSocket):
  Client → Server:
    {"type": "join",   "name": "PlayerName"}
    {"type": "state",  "x": float, "y": float, "vx": float, "vy": float,
                       "direction": int, "anim": str, "has_sword": bool,
                       "health": int, "score": int,
                       "at_checkpoint": bool, "checkpoint_id": str}
    {"type": "event",  "event": "attack"|"collect_coin"|"kill_enemy"|"died"|"respawn",
                       "data": {...}}
    {"type": "ping"}

  Server → Client:
    {"type": "assigned",    "player_id": 0|1, "room_id": str}
    {"type": "partner_joined", "name": str}
    {"type": "partner_state", ...}   # mirror của state từ người kia
    {"type": "partner_event", "event": str, "data": {...}}
    {"type": "checkpoint_status", "player0_ready": bool, "player1_ready": bool,
                                   "checkpoint_id": str, "unlocked": bool}
    {"type": "game_event",  "event": "map_advance"|"partner_disconnected", "data": {...}}
    {"type": "pong"}
    {"type": "error",   "message": str}
"""

import asyncio
import json
import logging
import argparse
import uuid
from typing import Dict, Optional

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
except ImportError:
    print("ERROR: websockets library not found. Install with: pip install websockets")
    raise

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("GameServer")


class Player:
    def __init__(self, ws: "WebSocketServerProtocol", player_id: int, name: str):
        self.ws = ws
        self.player_id = player_id          # 0 = host (Player 1), 1 = guest (Player 2)
        self.name = name
        self.last_state: dict = {}
        self.checkpoint_ready: Dict[str, bool] = {}  # checkpoint_id -> True nếu đã sẵn sàng

    async def send(self, msg: dict):
        try:
            await self.ws.send(json.dumps(msg))
        except Exception as e:
            log.warning(f"Send failed to player {self.player_id}: {e}")


class Room:
    """Một phòng chơi gồm đúng 2 người."""
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.players: Dict[int, Player] = {}   # {0: Player, 1: Player}
        self.checkpoint_status: Dict[str, set] = {}   # checkpoint_id -> {player_ids ready}

    def is_full(self) -> bool:
        return len(self.players) >= 2

    def get_partner(self, player_id: int) -> Optional[Player]:
        for pid, p in self.players.items():
            if pid != player_id:
                return p
        return None

    def add_player(self, player: Player):
        self.players[player.player_id] = player

    def remove_player(self, player_id: int):
        self.players.pop(player_id, None)

    async def broadcast_except(self, sender_id: int, msg: dict):
        partner = self.get_partner(sender_id)
        if partner:
            await partner.send(msg)

    async def broadcast_all(self, msg: dict):
        for p in self.players.values():
            await p.send(msg)

    # ---------- Checkpoint co-op logic ----------
    async def handle_checkpoint(self, player_id: int, checkpoint_id: str) -> bool:
        """
        Đánh dấu player đã tới checkpoint.
        Trả về True nếu CẢ HAI đã sẵn sàng → map advance.
        """
        if checkpoint_id not in self.checkpoint_status:
            self.checkpoint_status[checkpoint_id] = set()

        self.checkpoint_status[checkpoint_id].add(player_id)
        ready_set = self.checkpoint_status[checkpoint_id]

        p0_ready = 0 in ready_set
        p1_ready = 1 in ready_set
        both_ready = p0_ready and p1_ready

        status_msg = {
            "type": "checkpoint_status",
            "checkpoint_id": checkpoint_id,
            "player0_ready": p0_ready,
            "player1_ready": p1_ready,
            "unlocked": both_ready,
        }
        await self.broadcast_all(status_msg)

        if both_ready:
            # Reset cho checkpoint tiếp theo
            self.checkpoint_status[checkpoint_id] = set()
            advance_msg = {
                "type": "game_event",
                "event": "map_advance",
                "data": {"checkpoint_id": checkpoint_id},
            }
            await self.broadcast_all(advance_msg)
            log.info(f"Room {self.room_id}: Both players at checkpoint '{checkpoint_id}' → MAP ADVANCE")

        return both_ready


class GameServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        # ws -> Room
        self.ws_room: Dict["WebSocketServerProtocol", Room] = {}
        # ws -> Player
        self.ws_player: Dict["WebSocketServerProtocol", Player] = {}
        # Phòng đang chờ player thứ 2
        self.waiting_room: Optional[Room] = None

    def _find_or_create_room(self) -> tuple[Room, int]:
        """Tìm phòng đang chờ hoặc tạo mới. Trả về (room, player_id)."""
        if self.waiting_room and not self.waiting_room.is_full():
            room = self.waiting_room
            player_id = 1  # Guest
            self.waiting_room = None  # Phòng đã đủ người
            return room, player_id
        else:
            room = Room(str(uuid.uuid4())[:8])
            self.waiting_room = room
            return room, 0  # Host

    async def handle_connection(self, ws: "WebSocketServerProtocol"):
        player: Optional[Player] = None
        room: Optional[Room] = None

        log.info(f"New connection from {ws.remote_address}")

        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue

                msg_type = msg.get("type", "")

                # ── JOIN ──────────────────────────────────────────────
                if msg_type == "join":
                    if player is not None:
                        await ws.send(json.dumps({"type": "error", "message": "Already joined"}))
                        continue

                    name = str(msg.get("name", "Player"))[:32]
                    room, player_id = self._find_or_create_room()
                    player = Player(ws, player_id, name)
                    room.add_player(player)
                    self.ws_room[ws] = room
                    self.ws_player[ws] = player

                    await player.send({
                        "type": "assigned",
                        "player_id": player_id,
                        "room_id": room.room_id,
                        "name": name,
                    })

                    # Thông báo cho đối phương (nếu đã có)
                    partner = room.get_partner(player_id)
                    if partner:
                        await partner.send({
                            "type": "partner_joined",
                            "name": name,
                            "player_id": player_id,
                        })
                        await player.send({
                            "type": "partner_joined",
                            "name": partner.name,
                            "player_id": partner.player_id,
                        })
                        # Gửi ngược lại state mới nhất của partner cho player vừa join
                        if partner.last_state:
                            await player.send({
                                "type": "partner_state",
                                **partner.last_state,
                            })

                    log.info(f"Player '{name}' (id={player_id}) joined room {room.room_id}")

                # ── STATE ─────────────────────────────────────────────
                elif msg_type == "state":
                    if player is None or room is None:
                        continue
                    state = {k: v for k, v in msg.items() if k != "type"}
                    player.last_state = state

                    # Kiểm tra checkpoint
                    if state.get("at_checkpoint"):
                        checkpoint_id = str(state.get("checkpoint_id", "default"))
                        await room.handle_checkpoint(player.player_id, checkpoint_id)

                    await room.broadcast_except(player.player_id, {
                        "type": "partner_state",
                        **state,
                    })

                # ── EVENT ─────────────────────────────────────────────
                elif msg_type == "event":
                    if player is None or room is None:
                        continue
                    event_name = msg.get("event", "")
                    data = msg.get("data", {})
                    
                    # Handle "died" event: broadcast to both players as game_event
                    if event_name == "died":
                        died_msg = {
                            "type": "game_event",
                            "event": "died",
                            "data": {"player_id": player.player_id},
                        }
                        await room.broadcast_all(died_msg)
                        log.info(f"Room {room.room_id}: Player {player.player_id} ({player.name}) died!")
                    else:
                        # For other events, send to partner as partner_event
                        await room.broadcast_except(player.player_id, {
                            "type": "partner_event",
                            "event": event_name,
                            "data": data,
                        })

                # ── PING ──────────────────────────────────────────────
                elif msg_type == "ping":
                    if not ws.closed:
                        await ws.send(json.dumps({"type": "pong"}))

        except Exception as e:
            log.info(f"Connection closed: {e}")

        finally:
            # Cleanup
            if player and room:
                room.remove_player(player.player_id)
                # Thông báo đối phương
                partner = room.get_partner(player.player_id)
                if partner:
                    await partner.send({
                        "type": "game_event",
                        "event": "partner_disconnected",
                        "data": {"player_id": player.player_id},
                    })
                # Nếu phòng đang là waiting_room, dọn dẹp
                if self.waiting_room == room and not room.players:
                    self.waiting_room = None

            self.ws_room.pop(ws, None)
            self.ws_player.pop(ws, None)
            log.info(f"Cleaned up connection for player {player.player_id if player else '?'}")

    async def start(self):
        log.info(f"Starting Game Server on ws://{self.host}:{self.port}")
        async with websockets.serve(self.handle_connection, self.host, self.port):
            log.info("Server is running. Press Ctrl+C to stop.")
            await asyncio.Future()   # chạy mãi mãi


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="2-Player Co-op Game Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Port number (default: 8765)")
    args = parser.parse_args()

    server = GameServer(host=args.host, port=args.port)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        log.info("Server stopped.")