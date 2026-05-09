"""
screens/online_screen.py

Màn hình chọn chế độ Online:
  - Nhập tên player
  - Nhập địa chỉ server (IP:port)
  - Chọn Host (tạo phòng) hoặc Join (vào phòng)
  - Hiển thị trạng thái kết nối và chờ partner
"""

import pygame
from utils.assets import safe_load_image, safe_load_font
from utils.network_client import NetworkClient


class OnlineScreen:
    """Lobby & matchmaking screen cho chế độ 2 người online."""

    # Màu sắc
    C_WHITE    = (255, 255, 255)
    C_YELLOW   = (255, 225, 60)
    C_GRAY     = (180, 180, 180)
    C_DARK     = (40, 40, 40)
    C_GREEN    = (80, 220, 100)
    C_RED      = (220, 80, 80)
    C_BLUE     = (80, 160, 255)
    C_ORANGE   = (255, 160, 60)
    C_BLACK    = (0, 0, 0)
    C_BG_PANEL = (0, 0, 0, 140)

    def __init__(self, screen: pygame.Surface, window_size: tuple):
        self.screen = screen
        self.window_width, self.window_height = window_size

        # Fonts
        try:
            self.font_title  = safe_load_font(pygame, 'fonts/arial.ttf', 52)
            self.font_label  = safe_load_font(pygame, 'fonts/arial.ttf', 28)
            self.font_small  = safe_load_font(pygame, 'fonts/arial.ttf', 22)
            self.font_status = safe_load_font(pygame, 'fonts/arial.ttf', 24)
        except Exception:
            self.font_title  = pygame.font.SysFont('arial', 52, bold=True)
            self.font_label  = pygame.font.SysFont('arial', 28)
            self.font_small  = pygame.font.SysFont('arial', 22)
            self.font_status = pygame.font.SysFont('arial', 24)

        # Background
        try:
            bg_raw = safe_load_image(pygame, 'Images', 'Background', 'Background.jpg')
            bw, bh = bg_raw.get_size()
            scale = max(window_size[0] / bw, window_size[1] / bh)
            self.background = pygame.transform.smoothscale(
                bg_raw, (int(bw * scale), int(bh * scale))
            )
        except Exception:
            self.background = None

        # ── Input fields ──────────────────────────────────
        cx = self.window_width // 2
        field_w, field_h = 360, 42

        self.fields = {
            "name": {
                "label": "Tên của bạn",
                "value": "",
                "rect": pygame.Rect(cx - field_w // 2, int(self.window_height * 0.30), field_w, field_h),
                "active": False,
                "max_len": 20,
            },
            "server": {
                "label": "url",
                "value": "exemplify-sedation-darkish.ngrok-free.dev",
                "rect": pygame.Rect(cx - field_w // 2, int(self.window_height * 0.42), field_w, field_h),
                "active": False,
                "max_len": 64,
            },
        }
        self._active_field: str | None = None

        # ── Buttons ───────────────────────────────────────
        btn_w, btn_h = 160, 48
        gap = 24
        total = btn_w * 2 + gap
        bx = cx - total // 2
        by = int(self.window_height * 0.55)

        self.btn_connect = pygame.Rect(bx, by, btn_w, btn_h)
        self.btn_back    = pygame.Rect(bx + btn_w + gap, by, btn_w, btn_h)
        self.btn_start   = pygame.Rect(cx - btn_w // 2, by + btn_h + 20, btn_w, btn_h)

        # ── State machine ─────────────────────────────────
        # "idle"       → chưa kết nối
        # "connecting" → đang kết nối
        # "waiting"    → đã kết nối, chờ partner
        # "ready"      → cả 2 đã vào, có thể bắt đầu
        # "error"      → lỗi kết nối
        self.state: str = "idle"
        self.status_msg: str = ""
        self.status_color = self.C_GRAY

        # NetworkClient (sẽ được tạo khi Connect)
        self.client: NetworkClient | None = None

        # Cursor blink
        self._cursor_timer = 0

        # Dot animation
        self._dot_timer = 0
        self._dots = 0

    # ─────────────────────────────────────────────────────
    # Public
    # ─────────────────────────────────────────────────────

    def run(self) -> tuple[str, "NetworkClient | None"]:
        """
        Chạy màn hình lobby.
        Trả về ('start', client) hoặc ('back', None).
        """
        clock = pygame.time.Clock()

        while True:
            dt = clock.tick(60)
            self._cursor_timer = (self._cursor_timer + 1) % 60
            self._dot_timer += 1
            if self._dot_timer >= 20:
                self._dot_timer = 0
                self._dots = (self._dots + 1) % 4

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._cleanup()
                    return "back", None

                if event.type == pygame.KEYDOWN:
                    result = self._handle_key(event)
                    if result:
                        return result

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    result = self._handle_click(event.pos)
                    if result:
                        return result

            # Kiểm tra sự kiện mạng
            net_result = self._poll_network()
            if net_result:
                return net_result

            self._draw()
            pygame.display.flip()

    # ─────────────────────────────────────────────────────
    # Input handling
    # ─────────────────────────────────────────────────────

    def _handle_key(self, event: pygame.event.Event):
        if event.key == pygame.K_ESCAPE:
            self._cleanup()
            return "back", None

        if event.key == pygame.K_TAB:
            keys = list(self.fields.keys())
            if self._active_field in keys:
                idx = (keys.index(self._active_field) + 1) % len(keys)
                self._set_active_field(keys[idx])
            return None

        if self._active_field:
            field = self.fields[self._active_field]
            if event.key == pygame.K_BACKSPACE:
                field["value"] = field["value"][:-1]
            elif event.key == pygame.K_RETURN:
                self._set_active_field(None)
            elif event.unicode and len(field["value"]) < field["max_len"]:
                # Chỉ cho phép ký tự in được
                if event.unicode.isprintable():
                    field["value"] += event.unicode

        return None

    def _handle_click(self, pos: tuple):
        # Kích hoạt input field
        for key, field in self.fields.items():
            if field["rect"].collidepoint(pos):
                self._set_active_field(key)
                return None
            else:
                field["active"] = False

        # Nút Connect / Disconnect
        if self.btn_connect.collidepoint(pos):
            if self.state in ("idle", "error"):
                self._do_connect()
            elif self.state in ("connecting", "waiting", "ready"):
                self._cleanup()
                self.state = "idle"
                self.status_msg = ""
            return None

        # Nút Back
        if self.btn_back.collidepoint(pos):
            self._cleanup()
            return "back", None

        # Nút Start (chỉ xuất hiện khi ready)
        if self.state == "ready" and self.btn_start.collidepoint(pos):
            return "start", self.client

        return None

    def _set_active_field(self, key):
        self._active_field = key
        for k, f in self.fields.items():
            f["active"] = (k == key)

    # ─────────────────────────────────────────────────────
    # Network logic
    # ─────────────────────────────────────────────────────

    def _do_connect(self):
        name   = self.fields["name"]["value"].strip() or ""
        server = self.fields["server"]["value"].strip() or "exemplify-sedation-darkish.ngrok-free.dev"

        if not server.startswith("ws://") and not server.startswith("wss://"):
            server = "wss://" + server

        self.state = "connecting"
        self.status_msg = "Connecting..."
        self.status_color = self.C_ORANGE

        try:
            self.client = NetworkClient(url=server)
            self.client.start()
            self.client.join(name)
        except Exception as e:
            self.state = "error"
            self.status_msg = f"Error: {e}"
            self.status_color = self.C_RED
            self.client = None

    def _poll_network(self):
        if not self.client:
            return None

        # Đang kết nối → kiểm tra đã nhận assigned chưa
        if self.state == "connecting":
            if self.client.player_id is not None:
                self.state = "waiting"
                pid = self.client.player_id
                role = "Host" if pid == 0 else "Guest"
                room = self.client.room_id or "?"
                self.status_msg = f"[{role}] Phòng: {room}  —  Waiting Player..."
                self.status_color = self.C_BLUE
            elif not self.client.connected:
                # Không kết nối được sau 1 vòng poll
                pass

        # Đang chờ partner
        if self.state == "waiting":
            events = self.client.pop_events()
            for ev in events:
                if ev.get("type") == "partner_joined":
                    self.state = "ready"
                    pname = ev.get("name", "Partner")
                    self.client.partner_name = pname
                    self.status_msg = f"{pname} đã vào! Nhấn START để bắt đầu."
                    self.status_color = self.C_GREEN

        if self.state == "ready":
            # Vẫn poll events để xử lý nếu partner ngắt
            events = self.client.pop_events()
            #for ev in events:
            #    if ev.get("type") == "game_event" and ev.get("event") == "partner_disconnected":
            #        self.state = "waiting"
            #        self.status_msg = "Partner đã ngắt kết nối. Đang chờ..."
            #       self.status_color = self.C_ORANGE

        return None

    def _cleanup(self):
        if self.client:
            self.client.stop()
            self.client = None

    # ─────────────────────────────────────────────────────
    # Drawing
    # ─────────────────────────────────────────────────────

    def _draw(self):
        # Background
        if self.background:
            bg_rect = self.background.get_rect()
            bg_rect.center = (self.window_width // 2, self.window_height // 2)
            self.screen.blit(self.background, bg_rect)
        else:
            self.screen.fill((20, 20, 40))

        # Panel bán trong
        panel_w = int(self.window_width * 0.55)
        panel_h = int(self.window_height * 0.75)
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 150))
        panel_rect = panel.get_rect(center=(self.window_width // 2, self.window_height // 2))
        self.screen.blit(panel, panel_rect)

        cx = self.window_width // 2

        # Tiêu đề
        title_surf = self.font_title.render("ONLINE MODE", True, self.C_YELLOW)
        title_rect = title_surf.get_rect(centerx=cx, top=int(self.window_height * 0.12))
        self.screen.blit(title_surf, title_rect)

        # Input fields
        for key, field in self.fields.items():
            # Label
            label_surf = self.font_small.render(field["label"], True, self.C_GRAY)
            label_rect = label_surf.get_rect(left=field["rect"].left, bottom=field["rect"].top - 4)
            self.screen.blit(label_surf, label_rect)

            # Box
            border_color = self.C_YELLOW if field["active"] else self.C_GRAY
            pygame.draw.rect(self.screen, (20, 20, 30), field["rect"], border_radius=6)
            pygame.draw.rect(self.screen, border_color, field["rect"], 2, border_radius=6)

            # Text + cursor
            display_text = field["value"]
            if not field["active"] and len(display_text) > 25:
                display_text = display_text[:22] + "..."
            if field["active"] and self._cursor_timer < 30:
                display_text += "|"
            text_surf = self.font_label.render(display_text, True, self.C_WHITE)
            text_rect = text_surf.get_rect(
                midleft=(field["rect"].left + 10, field["rect"].centery)
            )
            self.screen.blit(text_surf, text_rect)

        # Buttons
        self._draw_button(
            self.btn_connect,
            label=self._connect_btn_label(),
            color=self._connect_btn_color(),
        )
        self._draw_button(self.btn_back, label="Back", color=(100, 100, 120))

        # Start button (khi ready)
        if self.state == "ready":
            self._draw_button(self.btn_start, label="START", color=(40, 180, 80), font=self.font_label)

        # Status message
        dots = "." * self._dots if self.state in ("connecting", "waiting") else ""
        status_text = self.status_msg + dots
        if status_text:
            status_surf = self.font_status.render(status_text, True, self.status_color)
            status_rect = status_surf.get_rect(centerx=cx, top=int(self.window_height * 0.72))
            self.screen.blit(status_surf, status_rect)

    def _connect_btn_label(self) -> str:
        if self.state == "idle":
            return "Connect"
        if self.state == "error":
            return "Try Again"
        return "Disconnect"

    def _connect_btn_color(self) -> tuple:
        if self.state in ("idle", "error"):
            return (60, 120, 200)
        return (160, 60, 60)

    def _draw_button(self, rect: pygame.Rect, label: str, color: tuple, font=None):
        if font is None:
            font = self.font_label
        mouse = pygame.mouse.get_pos()
        hover = rect.collidepoint(mouse)
        bg = tuple(min(255, c + 30) for c in color) if hover else color
        pygame.draw.rect(self.screen, bg, rect, border_radius=8)
        pygame.draw.rect(self.screen, self.C_WHITE, rect, 2, border_radius=8)
        text_surf = font.render(label, True, self.C_WHITE)
        text_rect = text_surf.get_rect(center=rect.center)
        self.screen.blit(text_surf, text_rect)