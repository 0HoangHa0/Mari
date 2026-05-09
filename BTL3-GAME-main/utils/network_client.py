"""
utils/network_client.py

WebSocket client chạy trên thread riêng.
Game loop gọi get_partner_state() / send_state() / send_event() mà không block.

Usage:
    from utils.network_client import NetworkClient

    nc = NetworkClient("ws://localhost:8765")
    nc.start()
    nc.join("MyName")

    # Trong game loop:
    nc.send_state({...})
    state = nc.get_partner_state()   # None nếu chưa có
    events = nc.pop_events()         # list of incoming events

    nc.stop()
"""

import json
import queue
import threading
import time
import logging
from typing import Optional, Callable

log = logging.getLogger("NetworkClient")

try:
    import websocket as ws_lib   # websocket-client
    _HAS_WEBSOCKET = True
except ImportError:
    _HAS_WEBSOCKET = False
    log.warning("websocket-client not installed. Run: pip install websocket-client")


class NetworkClient:
    def __init__(self, url: str = "ws://localhost:8765"):
        self.url = url

        # Trạng thái kết nối
        self.connected = False
        self.player_id: Optional[int] = None   # 0 hoặc 1
        self.room_id: Optional[str] = None
        self.my_name: Optional[str] = None
        self.partner_name: Optional[str] = None
        self.partner_joined = False

        # Data exchange
        self._partner_state: Optional[dict] = None
        self._state_lock = threading.Lock()
        self._send_queue: queue.Queue = queue.Queue(maxsize=60)
        self._incoming_events: queue.Queue = queue.Queue()

        # WebSocket object
        self._ws: Optional["ws_lib.WebSocketApp"] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Callbacks (gọi từ network thread)
        self.on_assigned: Optional[Callable] = None
        self.on_partner_joined: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None

        # Ping/pong keepalive
        self._last_ping = 0.0
        self._ping_interval = 20.0   # giây

        # Checkpoint state
        self.checkpoint_status: dict = {}   # {checkpoint_id: {"p0": bool, "p1": bool, "unlocked": bool}}

    # ─────────────────────────────────────────
    # Public API (gọi từ game thread)
    # ─────────────────────────────────────────

    def start(self):
        """Bắt đầu kết nối background thread."""
        if not _HAS_WEBSOCKET:
            raise RuntimeError("websocket-client not installed. Run: pip install websocket-client")
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Dừng kết nối."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    def join(self, name: str):
        """Gửi yêu cầu join room."""
        self.my_name = name
        self._enqueue({"type": "join", "name": name})

    def send_state(self, state: dict):
        """Gửi trạng thái player (không block)."""
        msg = {"type": "state", **state}
        # Bỏ qua nếu queue đầy (ưu tiên frame mới hơn)
        try:
            self._send_queue.put_nowait(msg)
        except queue.Full:
            try:
                self._send_queue.get_nowait()   # loại bỏ cũ nhất
                self._send_queue.put_nowait(msg)
            except (queue.Empty, queue.Full):
                pass

    def send_event(self, event_name: str, data: dict = None):
        """Gửi game event."""
        self._enqueue({
            "type": "event",
            "event": event_name,
            "data": data or {},
        })

    def get_partner_state(self) -> Optional[dict]:
        """Lấy state mới nhất của partner (thread-safe)."""
        with self._state_lock:
            return dict(self._partner_state) if self._partner_state else None

    def pop_events(self) -> list:
        """Lấy tất cả incoming events (game_event, partner_event, checkpoint_status)."""
        events = []
        while True:
            try:
                events.append(self._incoming_events.get_nowait())
            except queue.Empty:
                break
        return events

    def is_ready(self) -> bool:
        """True khi cả 2 người đã vào phòng."""
        return self.connected and self.partner_joined

    # ─────────────────────────────────────────
    # Internal (network thread)
    # ─────────────────────────────────────────

    def _enqueue(self, msg: dict):
        try:
            self._send_queue.put_nowait(msg)
        except queue.Full:
            pass

    def _run_loop(self):
        """Background thread: kết nối và gửi/nhận."""
        while self._running:
            log.info(f"Connecting to {self.url} ...")
            try:
                self._ws = ws_lib.WebSocketApp(
                    self.url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(ping_interval=0)   # tự quản ping
            except Exception as e:
                log.error(f"Connection error: {e}")

            self.connected = False
            self.partner_joined = False
            if self._running:
                log.info("Reconnecting in 3s...")
                time.sleep(3)

    def _on_open(self, ws):
        self.connected = True
        log.info("Connected to server")
        # Khởi động sender thread
        threading.Thread(target=self._sender_loop, args=(ws,), daemon=True).start()
        # Nếu đã có tên, join ngay
        if self.my_name:
            self._enqueue({"type": "join", "name": self.my_name})

    def _sender_loop(self, ws):
        """Gửi messages từ queue."""
        while self.connected and self._running:
            # Ping keepalive
            now = time.time()
            if now - self._last_ping > self._ping_interval:
                self._last_ping = now
                try:
                    ws.send(json.dumps({"type": "ping"}))
                except Exception:
                    break

            try:
                msg = self._send_queue.get(timeout=0.02)
                ws.send(json.dumps(msg))
            except queue.Empty:
                pass
            except Exception as e:
                log.warning(f"Send error: {e}")
                break

    def _on_message(self, ws, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type", "")

        if msg_type == "assigned":
            self.player_id = msg.get("player_id")
            self.room_id = msg.get("room_id")
            log.info(f"Assigned as Player {self.player_id} in room {self.room_id}")
            if self.on_assigned:
                self.on_assigned(self.player_id, self.room_id)

        elif msg_type == "partner_joined":
            self.partner_name = msg.get("name", "Partner")
            self.partner_joined = True
            log.info(f"Partner '{self.partner_name}' joined!")
            self._incoming_events.put({"type": "partner_joined", "name": self.partner_name})
            if self.on_partner_joined:
                self.on_partner_joined(self.partner_name)

        elif msg_type == "partner_state":
            with self._state_lock:
                self._partner_state = {k: v for k, v in msg.items() if k != "type"}

        elif msg_type == "partner_event":
            self._incoming_events.put(msg)

        elif msg_type == "checkpoint_status":
            cid = msg.get("checkpoint_id", "default")
            self.checkpoint_status[cid] = {
                "p0": msg.get("player0_ready", False),
                "p1": msg.get("player1_ready", False),
                "unlocked": msg.get("unlocked", False),
            }
            self._incoming_events.put(msg)

        elif msg_type == "game_event":
            self._incoming_events.put(msg)
            event = msg.get("event", "")
            if event == "partner_disconnected":
                self.partner_joined = False
                self.partner_name = None
                with self._state_lock:
                    self._partner_state = None
                log.info("Partner disconnected!")
                if self.on_disconnected:
                    self.on_disconnected()

        elif msg_type == "pong":
            pass   # keepalive OK

        elif msg_type == "error":
            log.warning(f"Server error: {msg.get('message')}")

    def _on_error(self, ws, error):
        log.warning(f"WebSocket error: {error}")

    def _on_close(self, ws, code, msg):
        self.connected = False
        self.partner_joined = False
        log.info(f"Connection closed (code={code})")