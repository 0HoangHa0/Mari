"""
screens/online_game_screen.py

Kế thừa GameScreen, thêm:
  1. Render player 2 (partner) từ network state
  2. Gửi state local player lên server mỗi frame
  3. Hiệu ứng HUD 2 người (2 thanh máu, tên, score)
  4. Checkpoint co-op: cả 2 cùng đứng vào vùng checkpoint
     → server xác nhận → map mở rộng thêm (scroll phải)
  5. Màn hình "Chờ partner" nếu partner ngắt kết nối
  6. Thông báo khi partner chết / respawn
"""

import pygame
import time
from typing import Optional

from screens.game_screen import GameScreen, DamageText
from utils.network_client import NetworkClient
from utils.assets import safe_load_image, resource_path


# ─── Hằng số ───────────────────────────────────────────────────────────────
SEND_INTERVAL = 0.5    # Gửi state mỗi frame (60fps = 60 lần/giây, đồng bộ nhanh nhất)
CHECKPOINT_RADIUS = 48     # Pixel radius quanh checkpoint trigger
MAP_ADVANCE_TILES  = 20    # Số tile map mở rộng thêm mỗi lần unlock
PARTNER_ALPHA      = 200   # Độ mờ của sprite partner


# ─── Damage text cho partner (màu cam, phân biệt với đỏ của local) ──────────
class PartnerDamageText(pygame.sprite.Sprite):
    """Damage text hiển thị thiệt hại của partner (màu cam)."""

    def __init__(self, damage_amount: int, world_x: float, world_y: float, font: pygame.font.Font):
        super().__init__()
        self.damage_amount = damage_amount
        self.font = font
        self.x = float(world_x)
        self.y = float(world_y)
        self.lifetime = 60
        self.age = 0
        self.vy = -1.5
        self._update_image()

    def _update_image(self):
        alpha = max(0, 255 - int(self.age * 255 / self.lifetime))
        text_surf = self.font.render(f"-{self.damage_amount}", True, (255, 140, 0))  # màu cam
        self.image = pygame.Surface(text_surf.get_size(), pygame.SRCALPHA)
        text_surf.set_alpha(alpha)
        self.image.blit(text_surf, (0, 0))
        self.rect = self.image.get_rect(center=(int(self.x), int(self.y)))

    def update(self):
        self.age += 1
        self.y += self.vy
        self._update_image()
        if self.age >= self.lifetime:
            self.kill()


# ─── Sprite partner ────────────────────────────────────────────────────────
class PartnerSprite(pygame.sprite.Sprite):
    """Sprite hiển thị vị trí & trạng thái của player 2."""

    def __init__(self, images: dict, name: str, player_id: int):
        super().__init__()
        self.images = images           # {"idle_r", "idle_l", "run_r", "run_l", "jump_r", "jump_l"}
        self.name = name
        self.player_id = player_id
        self.image = images.get("idle_r", next(iter(images.values())))
        self.rect = self.image.get_rect()

        self.world_x = 0.0
        self.world_y = 0.0
        self.health  = 100
        self.score   = 0
        self.anim    = "idle_r"
        self.visible = True
        self.last_update = time.time()
        self.is_attacking = False   # hiệu ứng tấn công từ event "attack"
        self.attack_timer = 0

        # Tên tag
        try:
            self._font = pygame.font.SysFont("arial", 18, bold=True)
        except Exception:
            self._font = pygame.font.Font(None, 18)

    def apply_state(self, state: dict):
        self.world_x = float(state.get("x", self.world_x))
        self.world_y = float(state.get("y", self.world_y))
        self.health  = int(state.get("health", self.health))
        self.score   = int(state.get("score", self.score))
        self.anim    = state.get("anim", "idle_r")
        self.last_update = time.time()

        # Tick down attack timer
        if self.attack_timer > 0:
            self.attack_timer -= 1
        else:
            self.is_attacking = False

        # Chọn sprite: ưu tiên attack animation nếu đang tấn công
        has_sword = state.get("has_sword", False)
        if self.is_attacking and has_sword:
            anim_key = "attack_r" if self.anim.endswith("r") else "attack_l"
            img = self.images.get(anim_key, self.images.get(self.anim, self.images.get("idle_r")))
        else:
            img = self.images.get(self.anim, self.images.get("idle_r"))
        if img:
            self.image = img.copy()
            self.image.set_alpha(PARTNER_ALPHA)

    def update_screen_pos(self, camera_x: float, camera_y: float):
        self.rect.x = int(self.world_x - camera_x)
        self.rect.y = int(self.world_y - camera_y)

    def draw_name_tag(self, surface: pygame.Surface, camera_x: float, camera_y: float):
        tag = self._font.render(f"▲ {self.name}", True, (100, 220, 255))
        tx = int(self.world_x - camera_x) + self.rect.width // 2 - tag.get_width() // 2
        ty = int(self.world_y - camera_y) - tag.get_height() - 4
        surface.blit(tag, (tx, ty))


# ─── Checkpoint zone ───────────────────────────────────────────────────────
class CheckpointZone:
    """Điểm checkpoint cần cả 2 người đứng vào để mở rộng map."""

    def __init__(self, world_x: int, world_y: int, checkpoint_id: str, width=64, height=96):
        self.world_x = world_x
        self.world_y = world_y
        self.width  = width
        self.height = height
        self.checkpoint_id = checkpoint_id
        self.rect = pygame.Rect(world_x, world_y, width, height)

        # Trạng thái
        self.player_inside  = False   # local player
        self.partner_inside = False   # partner (từ network)
        self.unlocked = False

        # Animation
        self._pulse = 0.0

    def check_player(self, px: float, py: float, pw: int, ph: int) -> bool:
        player_rect = pygame.Rect(int(px), int(py), pw, ph)
        return bool(self.rect.colliderect(player_rect))

    def draw(self, surface: pygame.Surface, camera_x: float, camera_y: float, font: pygame.font.Font):
        if self.unlocked:
            return  # Đã mở, không cần vẽ nữa

        sx = int(self.world_x - camera_x)
        sy = int(self.world_y - camera_y)

        # Nhấp nháy vàng / xanh lá
        self._pulse = (self._pulse + 0.08) % (2 * 3.14159)
        import math
        alpha = int(80 + 60 * math.sin(self._pulse))

        surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        if self.player_inside and self.partner_inside:
            color = (80, 255, 80, alpha)
        elif self.player_inside or self.partner_inside:
            color = (255, 200, 0, alpha)
        else:
            color = (100, 180, 255, alpha)

        surf.fill(color)
        surface.blit(surf, (sx, sy))
        pygame.draw.rect(surface, (255, 255, 255), (sx, sy, self.width, self.height), 2)

        # Icon & nhãn
        icon_text = "✓✓" if (self.player_inside and self.partner_inside) else \
                    "✓?" if (self.player_inside or self.partner_inside) else "??"
        label = font.render(icon_text, True, (255, 255, 255))
        surface.blit(label, (sx + self.width // 2 - label.get_width() // 2,
                              sy + self.height // 2 - label.get_height() // 2))

        # Hướng dẫn
        hint = font.render("Cả 2 vào đây → map mở rộng!", True, (220, 220, 220))
        surface.blit(hint, (sx - hint.get_width() // 4, sy - 22))


# ─── OnlineGameScreen ──────────────────────────────────────────────────────
class OnlineGameScreen(GameScreen):
    """
    GameScreen mở rộng cho 2 người online.
    Yêu cầu client: NetworkClient đã kết nối và partner đã join.
    """

    def __init__(self, screen: pygame.Surface, window_size: tuple,
                 client: NetworkClient, player_name: str = "Player"):
        super().__init__(screen, window_size)

        self.client = client
        self.player_name = player_name
        self.my_player_id = client.player_id  # 0 hoặc 1

        # ── Partner sprite ────────────────────────────────
        partner_images = self._load_partner_images()
        partner_name = client.partner_name or "Partner"
        self.partner = PartnerSprite(partner_images, partner_name,
                                     1 - self.my_player_id)
        self.partner_alive = True
        self.partner_disconnected = False

        # ── Checkpoints ───────────────────────────────────
        # Tạo checkpoint zones dựa trên chiều dài map
        self.checkpoint_zones: list[CheckpointZone] = []
        self._create_checkpoints()

        # Checkpoint index đang active (map đã advance đến đâu)
        self.current_checkpoint_idx = 0
        # Map visible width (mở rộng thêm mỗi lần advance)
        self.visible_map_end_x = self._get_initial_visible_end()

        # ── Network timing ────────────────────────────────
        self._frame_count = 0
        self._last_state_at_checkpoint = False

        # ── Font & HUD ────────────────────────────────────
        try:
            self.hud2_font  = pygame.font.SysFont("arial", 20, bold=True)
            self.hud2_small = pygame.font.SysFont("arial", 16)
            self.mid_font   = pygame.font.SysFont("arial", 32, bold=True)
        except Exception:
            self.hud2_font  = pygame.font.Font(None, 22)
            self.hud2_small = pygame.font.Font(None, 18)
            self.mid_font   = pygame.font.Font(None, 34)

        # ── Notification system ───────────────────────────
        self._notifications: list[dict] = []   # {"text", "color", "ttl"}

        # ── Waiting screen flag ───────────────────────────
        self._show_waiting = False
        self._waiting_start = 0.0

        # ── Game over flag ────────────────────────────────
        self._game_over = False
        self._game_over_reason = ""

        # ── Sword pickup guard ────────────────────────────
        # Lưu id() các sword sprite đã được nhặt để tránh nhặt lại
        # khi event collect_sword từ partner chưa kịp xóa sprite
        self._collected_sword_ids: set = set()

        # ── Partner damage text (màu cam, world coords) ───
        self.partner_damage_text_group = pygame.sprite.Group()

    # ─────────────────────────────────────────────────────
    # Setup helpers
    # ─────────────────────────────────────────────────────

    def _load_partner_images(self) -> dict:
        """Load sprite cho partner (tái sử dụng ảnh player nhưng đổi màu hue)."""
        imgs = {}
        pairs = [
            ("idle_r",   "Main_Idle_right.png"),
            ("idle_l",   "Main_Idle_left.png"),
            ("run_r",    "Main_Run_right.png"),
            ("run_l",    "Main_Run_left.png"),
            ("jump_r",   "Main_Jump_right.png"),
            ("jump_l",   "Main_Jump_left.png"),
            ("fall_r",   "Main_falling_right.png"),
            ("fall_l",   "Main_falling_left.png"),
            ("attack_r", "main_attack_sword_right.png"),
            ("attack_l", "main_attack_sword_left.png"),
        ]
        for key, filename in pairs:
            try:
                img = safe_load_image(pygame, "Images", filename)
                # Tô màu xanh cyan để phân biệt với player 1
                tinted = self._tint_surface(img, (80, 200, 255))
                imgs[key] = tinted
            except Exception:
                surf = pygame.Surface((32, 64), pygame.SRCALPHA)
                surf.fill((80, 200, 255, 180))
                imgs[key] = surf
        return imgs

    def _tint_surface(self, surface: pygame.Surface, color: tuple) -> pygame.Surface:
        """Overlay màu bán trong suốt lên sprite để phân biệt."""
        tinted = surface.copy()
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((*color, 80))   # alpha = 80/255
        tinted.blit(overlay, (0, 0))
        return tinted

    def _create_checkpoints(self):
        """Tạo checkpoint zones trải đều theo chiều dài map."""
        # Mỗi checkpoint cách nhau ~20 tile (640px)
        tile_w = 32
        spacing_tiles = 20
        # Checkpoint bắt đầu sau 10 tile, kết thúc trước cuối map
        start_tile = 10
        num_checkpoints = max(1, (self.map_width_tiles - start_tile) // spacing_tiles)

        for i in range(num_checkpoints):
            cx_tile = start_tile + (i + 1) * spacing_tiles
            cx_px   = cx_tile * tile_w
            # Đặt checkpoint ở row tile gần đáy map
            cy_px   = max(0, self.world_height_px - 5 * tile_w)

            # Tìm mặt đất gần nhất (đơn giản: đặt tại đáy visible)
            zone = CheckpointZone(
                world_x=cx_px,
                world_y=cy_px - 96,
                checkpoint_id=f"cp_{i}",
                width=80,
                height=96,
            )
            self.checkpoint_zones.append(zone)

    def _get_initial_visible_end(self) -> int:
        """Toàn bộ map luôn hiển thị (không giới hạn theo checkpoint)."""
        return self.world_width_px  # mở hết map ngay từ đầu

    # ─────────────────────────────────────────────────────
    # Main loop override
    # ─────────────────────────────────────────────────────

    def run(self):
        clock = pygame.time.Clock()
        running = True

        while running:
            self._frame_count += 1

            # ── Events ──────────────────────────────────
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP:
                        if self._is_grounded():
                            self.vy = self.jump_velocity
                        self.keyboard_active = True
                    if event.key == pygame.K_f:
                        if self.has_sword and self.sword_health > 0 and self.attack_cooldown <= 0:
                            self.attack_duration = 20
                            self.attack_cooldown = 30
                            self._attack_enemies()
                            self.client.send_event("attack", {"x":self.player_x, "y":self.player_y})
                        self.keyboard_active = True
                    if event.key == pygame.K_ESCAPE:
                        running = False

                # Mouse panning (giống gốc)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.mouse_dragging = True
                    self.last_mouse_pos = event.pos
                    self.keyboard_active = False
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self.mouse_dragging = False
                    self.last_mouse_pos = None

            # ── Game logic (original) ────────────────────
            self._process_input_and_physics()

            # ── Checkpoint check ─────────────────────────
            self._check_checkpoints()

            # ── Network: gửi state ───────────────────────
            if self._frame_count % SEND_INTERVAL == 0:
                self._send_my_state()

            # ── Network: nhận events ─────────────────────
            self._process_network_events()

            # ── Partner sprite update ────────────────────
            pstate = self.client.get_partner_state()
            if pstate:
                self.partner.apply_state(pstate)
                self._check_partner_at_checkpoint(pstate)
            self.partner.update_screen_pos(self.camera_x, self.camera_y)

            # ── Partner timeout (disconnected) ────────────
            # Chỉ đánh dấu disconnected sau 30s không nhận bất kỳ data nào từ partner
            if time.time() - self.client.get_partner_last_recv() > 30.0 and not self.partner_disconnected:
                self.partner_disconnected = True

            # ── Draw ─────────────────────────────────────
            self._draw_online()
            if self._game_over:
                self._draw_game_over()
                pygame.display.flip()
                pygame.time.wait(3000)
                break
            pygame.display.flip()
            clock.tick(60)

        pygame.mixer.music.stop()

    # ─────────────────────────────────────────────────────
    # Input & physics (gọi các method gốc của GameScreen)
    # ─────────────────────────────────────────────────────

    def _process_input_and_physics(self):
        """Chạy toàn bộ logic physics & input của GameScreen gốc."""
        keys = pygame.key.get_pressed()

        # Di chuyển ngang
        dx = 0
        if keys[pygame.K_LEFT]:
            dx = -self.player_speed
            self.last_direction = -1
            self.keyboard_active = True
        if keys[pygame.K_RIGHT]:
            dx = self.player_speed
            self.last_direction = 1
            self.keyboard_active = True

        # Áp dụng di chuyển (gọi _move_player từ GameScreen)
        if dx != 0:
            self._move_player(dx, 0)

        # ── Giới hạn biên theo vị trí partner ───────────
        # Nhân vật không được đi ra ngoài tầm nhìn của partner
        pstate = self.client.get_partner_state()
        if pstate:
            partner_x = float(pstate.get("x", self.player_x))
            # Biên phải: player không vượt quá (partner_x + 1 màn hình)
            max_x = partner_x + self.window_width - self.player_w
            # Biên trái: player không bị bỏ lại quá (partner_x - 1 màn hình)
            min_x = partner_x - self.window_width
            if self.player_x > max_x:
                self.player_x = max_x
            if self.player_x < min_x:
                self.player_x = min_x

        # Gravity & vertical
        if not self._is_grounded():
            self.vy = min(self.vy + self.gravity, self.max_fall)
        else:
            if self.vy > 0:
                self.vy = 0
        if self.vy != 0:
            self._move_player(0, self.vy)

        # Camera
        if self.keyboard_active:
            self._update_camera_follow()

        # Mouse drag camera
        if self.mouse_dragging and self.last_mouse_pos:
            mx, my = pygame.mouse.get_pos()
            lx, ly = self.last_mouse_pos
            self.camera_x -= (mx - lx)
            self.camera_y -= (my - ly)
            self.last_mouse_pos = (mx, my)
            self._update_camera_follow()

        # Cooldowns
        if self.attack_duration > 0:
            self.attack_duration -= 1
        if self.attack_cooldown > 0:
            self.attack_cooldown -= 1
        if self.damage_cooldown > 0:
            self.damage_cooldown -= 1
        if self.lava_damage_cooldown > 0:
            self.lava_damage_cooldown -= 1

        # Update enemies, coins, etc. (gọi các method gốc)
        self._update_game_objects()

        # Notifications TTL
        self._notifications = [n for n in self._notifications if n["ttl"] > 0]
        for n in self._notifications:
            n["ttl"] -= 1
            
    def _clamp_camera(self):
        max_cx = max(0, self.world_width_px - self.window_width)
        max_cy = max(0, self.world_height_px - self.window_height)
        self.camera_x = max(0, min(self.camera_x, max_cx))
        self.camera_y = max(0, min(self.camera_y, max_cy))

    def _update_game_objects(self):
        """Cập nhật tất cả objects như GameScreen gốc."""
        # Skeletons
        for skel in self.skeleton_group:
            skel.update(
                self.player_x, self.player_y,
                self._iter_colliding_tile_rects,
                self.world_width_px, self.world_height_px
            )

        # Boss
        for boss in self.boss_group:
            boss.update(
                self.player_x, self.player_y,
                self._iter_colliding_tile_rects,
                self.world_width_px, self.world_height_px,
                self.bullet_group,
            )

        # Bullets
        for bullet in self.bullet_group:
            bullet.update(self.world_width_px, self.world_height_px)

        # Damage / heal effects
        self.damage_text_group.update()
        self.heal_effect_group.update()
        self.partner_damage_text_group.update()

        # Player collisions
        self._check_stomp_skeletons()
        self._check_player_enemy_collision()
        self._check_player_item_collision()
        self._check_lava_collision()
        self._check_bullet_collision()

    # ─────────────────────────────────────────────────────
    # Checkpoint logic
    # ─────────────────────────────────────────────────────

    def _check_checkpoints(self):
        """Kiểm tra local player có đứng trong checkpoint không."""
        if self.current_checkpoint_idx >= len(self.checkpoint_zones):
            return

        zone = self.checkpoint_zones[self.current_checkpoint_idx]
        if zone.unlocked:
            self.current_checkpoint_idx += 1
            return

        was_inside = zone.player_inside
        zone.player_inside = zone.check_player(
            self.player_x, self.player_y, self.player_w, self.player_h
        )

        if zone.player_inside and not was_inside:
            # Vừa bước vào → thông báo server
            self._add_notification("📍 Đã vào checkpoint! Chờ partner...", (255, 220, 60))
            # Gửi state với at_checkpoint=True
            self._send_my_state(at_checkpoint=True, checkpoint_id=zone.checkpoint_id)

    def _check_partner_at_checkpoint(self, pstate: dict):
        """Cập nhật trạng thái partner trong checkpoint."""
        if self.current_checkpoint_idx >= len(self.checkpoint_zones):
            return
        zone = self.checkpoint_zones[self.current_checkpoint_idx]
        if zone.unlocked:
            return
        partner_at = pstate.get("at_checkpoint", False)
        partner_cid = pstate.get("checkpoint_id", "")
        zone.partner_inside = (partner_at and partner_cid == zone.checkpoint_id)

    def _advance_map(self, checkpoint_id: str):
        """Mở rộng phần map visible và advance checkpoint."""
        for i, zone in enumerate(self.checkpoint_zones):
            if zone.checkpoint_id == checkpoint_id:
                zone.unlocked = True
                self.current_checkpoint_idx = i + 1
                # Mở thêm N tile
                self.visible_map_end_x = min(
                    self.world_width_px,
                    self.visible_map_end_x + MAP_ADVANCE_TILES * 32
                )
                self._add_notification(
                    f"🎉 Map mở rộng! ({MAP_ADVANCE_TILES} tile)",
                    (80, 255, 80), ttl=240
                )
                break

    # ─────────────────────────────────────────────────────
    # Network
    # ─────────────────────────────────────────────────────

    def _current_anim_key(self) -> str:
        """Xác định animation key hiện tại của local player để gửi cho partner.
        
        Quy ước: last_direction == -1 → đang quay phải, == 1 → đang quay trái
        """
        facing_right = (self.last_direction == -1)
        if not self._is_grounded():
            if self.vy < 0:
                return "jump_r" if facing_right else "jump_l"
            else:
                return "fall_r" if facing_right else "fall_l"
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_RIGHT]:
            return "run_r" if facing_right else "run_l"
        return "idle_r" if facing_right else "idle_l"

    def _send_my_state(self, at_checkpoint: bool = False, checkpoint_id: str = ""):
        """Đẩy state của local player lên server."""
        # at_checkpoint chỉ True khi vừa bước vào
        cp_id = checkpoint_id
        if not at_checkpoint and self.current_checkpoint_idx < len(self.checkpoint_zones):
            zone = self.checkpoint_zones[self.current_checkpoint_idx]
            if zone.player_inside and not zone.unlocked:
                at_checkpoint = True
                cp_id = zone.checkpoint_id

        self.client.send_state({
            "x": float(self.player_x),
            "y": float(self.player_y),
            "vx": 0.0,
            "vy": float(self.vy),
            "direction": self.last_direction,
            "anim": self._current_anim_key(),
            "has_sword": self.has_sword,
            "health": self.health,
            "score": self.score,
            "at_checkpoint": at_checkpoint,
            "checkpoint_id": cp_id,
        })

    def _process_network_events(self):
        """Xử lý events từ server."""
        for ev in self.client.pop_events():
            ev_type = ev.get("type", "")

            if ev_type == "checkpoint_status":
                cid = ev.get("checkpoint_id", "")
                unlocked = ev.get("unlocked", False)
                # Cập nhật partner_inside
                for zone in self.checkpoint_zones:
                    if zone.checkpoint_id == cid:
                        zone.partner_inside = ev.get("player1_ready", False) \
                            if self.my_player_id == 0 else ev.get("player0_ready", False)
                        break
                if unlocked:
                    self._advance_map(cid)

            elif ev_type == "game_event":
                event_name = ev.get("event", "")
                if event_name == "map_advance":
                    cid = ev.get("data", {}).get("checkpoint_id", "")
                    self._advance_map(cid)
                elif event_name == "partner_disconnected":
                    self.partner_disconnected = True
                    self._add_notification("Partner đã ngắt kết nối!", (255, 80, 80), ttl=600)
                elif event_name == "died":
                    # Server notified that one player died — end the game for both
                    self._game_over = True
                    self._game_over_reason = " Đồng đội đã chết! GAME OVER"

            elif ev_type == "partner_event":
                pev = ev.get("event", "")
                data = ev.get("data", {})

                if pev == "attack":
                    # Hiển thị animation tấn công cho partner
                    self.partner.is_attacking = True
                    self.partner.attack_timer = 20   # 20 frame = ~0.33s ở 60fps

                elif pev == "player_damaged":
                    # Partner bị thương → hiện damage text màu cam tại vị trí partner
                    amount = int(data.get("amount", 0))
                    wx = float(data.get("x", self.partner.world_x + self.partner.rect.width // 2))
                    wy = float(data.get("y", self.partner.world_y))
                    if amount > 0:
                        pdt = PartnerDamageText(amount, wx, wy, self.ui_font)
                        self.partner_damage_text_group.add(pdt)

                elif pev == "collect_coin":
                    self._remove_nearest_object(self.coin_group, data.get("x", 0), data.get("y", 0))
                    self._add_notification(f" {self.partner.name} nhặt xu!", (255, 230, 100))

                elif pev == "collect_sword":
                    # Partner nhặt kiếm → chỉ xóa sprite khỏi màn hình,
                    # KHÔNG set self.has_sword (kiếm đó là của partner, không phải mình)
                    sx, sy = data.get("x", 0), data.get("y", 0)
                    for sword in list(self.sword_group):
                        if abs(sword.rect.x - sx) + abs(sword.rect.y - sy) < 128:
                            self._collected_sword_ids.add(id(sword))
                            sword.kill()
                            break
                    self._add_notification(f"⚔ {self.partner.name} nhặt kiếm!", (255, 200, 60))

                elif pev == "collect_star":
                    self._remove_nearest_object(self.star_group, data.get("x", 0), data.get("y", 0))

                elif pev == "collect_key":
                    self._remove_nearest_object(self.key_group, data.get("x", 0), data.get("y", 0))

                elif pev == "kill_enemy":
                    spawn_x = data.get("spawn_x")
                    if spawn_x is not None:
                        # Tìm đúng quái theo spawn_x (ID ổn định, không đổi khi di chuyển)
                        for skel in list(self.skeleton_group):
                            if int(skel.start_x) == int(spawn_x):
                                skel.kill()
                                break
                        for boss in list(self.boss_group):
                            if int(boss.start_x) == int(spawn_x):
                                boss.kill()
                                break
                    else:
                        # Fallback cho event cũ dùng x/y
                        self._remove_nearest_object(
                            self.skeleton_group,
                            data.get("x", 0), data.get("y", 0),
                            threshold=300
                        )
                        self._remove_nearest_object(
                            self.boss_group,
                            data.get("x", 0), data.get("y", 0),
                            threshold=300
                        )
                    self._add_notification(f"{self.partner.name} tiêu diệt quái!", (255, 200, 60))

                elif pev == "died":
                    # Partner reported death — trigger shared game over
                    self._game_over = True
                    self._game_over_reason = f" {self.partner.name} died! GAME OVER"

            elif ev_type == "partner_joined":
                pname = ev.get("name", "Partner")
                self.partner.name = pname
                self._add_notification(f"{pname} đã tham gia!", (80, 220, 255), ttl=300)
                
    def _attack_enemies(self):
        """Override để gửi kill_enemy event khi giết quái.

        Dùng start_x (vị trí spawn cố định) làm ID ổn định để máy kia
        tìm đúng con quái cần xóa, bất kể nó đang đi tuần ở đâu.
        """
        # Snapshot: python-id -> spawn_x (bất biến suốt vòng đời skeleton/boss)
        alive_snapshot = {
            id(s): int(s.start_x)
            for s in self.skeleton_group
            if s.health > 0
        }
        boss_snapshot = {
            id(b): int(b.start_x)
            for b in self.boss_group
            if b.hits < b.max_hits
        }

        # Gọi logic gốc (kill() các skeleton/boss chết, trừ chúng khỏi group)
        super()._attack_enemies()

        # So sánh group trước/sau → gửi event cho mỗi con vừa bị kill
        alive_after_ids = {id(s) for s in self.skeleton_group}
        for skel_id, spawn_x in alive_snapshot.items():
            if skel_id not in alive_after_ids:
                self.client.send_event("kill_enemy", {"spawn_x": spawn_x})

        boss_after_ids = {id(b) for b in self.boss_group}
        for boss_id, spawn_x in boss_snapshot.items():
            if boss_id not in boss_after_ids:
                self.client.send_event("kill_enemy", {"spawn_x": spawn_x})

    def _check_stomp_skeletons(self):
        """Override để gửi kill_enemy event khi stomp chết skeleton."""
        alive_snapshot = {
            id(s): int(s.start_x)
            for s in self.skeleton_group
            if s.health > 0
        }
        super()._check_stomp_skeletons()
        alive_after_ids = {id(s) for s in self.skeleton_group}
        for skel_id, spawn_x in alive_snapshot.items():
            if skel_id not in alive_after_ids:
                self.client.send_event("kill_enemy", {"spawn_x": spawn_x})

    # ─────────────────────────────────────────────────────
    # Notification helpers
    # ─────────────────────────────────────────────────────

    def _add_notification(self, text: str, color: tuple, ttl: int = 180):
        self._notifications.append({"text": text, "color": color, "ttl": ttl})
        # Giữ tối đa 5 thông báo
        if len(self._notifications) > 5:
            self._notifications.pop(0)

    # ─────────────────────────────────────────────────────
    # Drawing
    # ─────────────────────────────────────────────────────

    def _draw_online(self):
        """Vẽ toàn bộ màn hình online."""
        # Vẽ nền (giống GameScreen._draw)
        self._draw_parallax_background()
        self._draw_tile_layer()

        # Vẽ items, enemies (gốc)
        self._draw_game_objects()

        # Vẽ partner
        self._draw_partner()

        # Checkpoint zones KHÔNG hiển thị trong online (ẩn đi)
        # self._draw_checkpoints()

        # Vẽ local player (sprite)
        self._draw_local_player()

        # Vẽ effects (local player: đỏ | partner: cam)
        for spr in self.damage_text_group:
            self.screen.blit(spr.image, (spr.rect.x - int(self.camera_x), spr.rect.y - int(self.camera_y)))
        for spr in self.heal_effect_group:
            self.screen.blit(spr.image, (spr.rect.x - int(self.camera_x), spr.rect.y - int(self.camera_y)))
        for spr in self.partner_damage_text_group:
            self.screen.blit(spr.image, (spr.rect.x - int(self.camera_x), spr.rect.y - int(self.camera_y)))

        # HUD 2 người
        self._draw_dual_hud()

        # Notifications KHÔNG hiển thị trong online (ẩn đi)
        # self._draw_notifications()

        # Waiting overlay
        if self.partner_disconnected and not self.client.partner_joined:
            self._draw_waiting_overlay()

    def _draw_game_objects(self):
        """Draw coins, swords, stars, keys, enemies, bullets."""
        cam = (int(self.camera_x), int(self.camera_y))

        for group in [self.coin_group, self.sword_group, self.box_group,
            self.star_group, self.key_group,
            self.skeleton_group, self.boss_group, self.bullet_group]:
            for spr in group:
                sx = spr.rect.x - cam[0]
                sy = spr.rect.y - cam[1]
                self.screen.blit(spr.image, (sx, sy))

    def _draw_local_player(self):
        """Vẽ sprite local player (kế thừa logic chọn ảnh từ GameScreen)."""
        img = self._get_player_sprite()
        sx = int(self.player_x - self.camera_x)
        sy = int(self.player_y - self.camera_y)
        self.screen.blit(img, (sx, sy))

        # Tên local player
        try:
            tag = self.hud2_small.render(f"▲ {self.player_name} (You)", True, (255, 255, 150))
            self.screen.blit(tag, (sx + self.player_w // 2 - tag.get_width() // 2, sy - 20))
        except Exception:
            pass

    def _get_player_sprite(self) -> pygame.Surface:
        grounded = self._is_grounded()
        keys = pygame.key.get_pressed()
        facing_right = (self.last_direction == -1)

        if self.attack_duration > 0 and self.has_sword:
            return self.player_sword_attack_right if facing_right else self.player_sword_attack_left
        if not grounded:
            if self.vy < 0:
                if self.has_sword:
                    return self.player_sword_jump_right if facing_right else self.player_sword_jump_left
                return self.player_jump_right if facing_right else self.player_jump_left
            else:              # đang rơi xuống
                if self.has_sword:
                    return self.player_sword_falling_right if facing_right else self.player_sword_falling_left
                return self.player_fall_right if facing_right else self.player_fall_left
        # đang đứng trên đất
        if keys[pygame.K_LEFT] or keys[pygame.K_RIGHT]:
            if self.has_sword:
                return self.player_sword_run_right if facing_right else self.player_sword_run_left
            return self.player_run_right if facing_right else self.player_run_left
        if self.has_sword:
            return self.player_sword_right if facing_right else self.player_sword_left
        return self.player_image

    def _draw_partner(self):
        """Vẽ sprite partner."""
        pstate = self.client.get_partner_state()
        if not pstate:
            return
        self.partner.update_screen_pos(self.camera_x, self.camera_y)
        self.screen.blit(self.partner.image, self.partner.rect)
        self.partner.draw_name_tag(self.screen, self.camera_x, self.camera_y)

    def _draw_checkpoints(self):
        for zone in self.checkpoint_zones:
            if not zone.unlocked:
                zone.draw(self.screen, self.camera_x, self.camera_y, self.hud2_small)

    def _draw_dual_hud(self):
        # ── Player 1 (local) ─────────────────────────────
        self._draw_health_bar(
            x=16, y=16,
            health=self.health, max_health=self.max_health,
            name=self.player_name + " (P1)",
            color=(80, 200, 100),
        )
        score_surf = self.hud2_font.render(f"Score: {self.score}", True, (255, 255, 150))
        self.screen.blit(score_surf, (16, 58))

        # ── Player 2 (partner) ───────────────────────────
        pstate = self.client.get_partner_state()
        p2_health = pstate.get("health", 0) if pstate else 0
        p2_score  = pstate.get("score", 0) if pstate else 0
        p2_name   = self.partner.name + " (P2)"

        bar_x = self.window_width - 260
        self._draw_health_bar(
            x=bar_x, y=16,
            health=p2_health, max_health=self.max_health,
            name=p2_name,
            color=(80, 180, 255),
        )
        score2 = self.hud2_font.render(f"Score: {p2_score}", True, (180, 220, 255))
        self.screen.blit(score2, (bar_x, 58))

        # ── Checkpoint indicator KHÔNG hiển thị trong online ────────
        # (ẩn để giảm thông tin nhiễu)

    def _draw_health_bar(self, x: int, y: int, health: int, max_health: int,
                        name: str, color: tuple):
        bar_w, bar_h = 200, 16
        ratio = max(0.0, health / max_health)

        # Label
        label = self.hud2_small.render(name, True, (220, 220, 220))
        self.screen.blit(label, (x, y - 18))

        # Background
        pygame.draw.rect(self.screen, (60, 60, 60), (x, y, bar_w, bar_h), border_radius=4)
        # Fill
        fill_w = int(bar_w * ratio)
        if fill_w > 0:
            pygame.draw.rect(self.screen, color, (x, y, fill_w, bar_h), border_radius=4)
        # Border
        pygame.draw.rect(self.screen, (200, 200, 200), (x, y, bar_w, bar_h), 1, border_radius=4)
        # Text
        hp_txt = self.hud2_small.render(f"{health}/{max_health}", True, (255, 255, 255))
        self.screen.blit(hp_txt, (x + bar_w // 2 - hp_txt.get_width() // 2, y + 1))

    def _draw_notifications(self):
        base_y = 90
        for i, notif in enumerate(reversed(self._notifications[-5:])):
            alpha = min(255, notif["ttl"] * 3)
            surf = self.hud2_font.render(notif["text"], True, notif["color"])
            surf.set_alpha(alpha)
            self.screen.blit(surf, (16, base_y + i * 26))

    def _draw_waiting_overlay(self):
        overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
    #    self.screen.blit(overlay, (0, 0))

    #    cx, cy = self.window_width // 2, self.window_height // 2
    #    msg1 = self.mid_font.render("⏳ Partner mất kết nối...", True, (255, 220, 60))
    #    msg2 = self.hud2_font.render("Đang chờ partner kết nối lại", True, (200, 200, 200))
    #    msg3 = self.hud2_small.render("Nhấn ESC để thoát về menu", True, (180, 180, 180))

    #    self.screen.blit(msg1, (cx - msg1.get_width() // 2, cy - 40))
    #    self.screen.blit(msg2, (cx - msg2.get_width() // 2, cy + 10))
    #    self.screen.blit(msg3, (cx - msg3.get_width() // 2, cy + 50))

    def _draw_game_over(self):
        """Draw game over screen cho chế độ online 2 người."""
        # Vẽ nền parallax
        self._draw_parallax_background()

        # Overlay mờ
        overlay = pygame.Surface((self.window_width, self.window_height))
        overlay.set_alpha(185)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        cx = self.window_width // 2
        cy = self.window_height // 2

        # ── Tiêu đề GAME OVER ──────────────────────────────────────────
        try:
            big_font = pygame.font.SysFont("arial", 64, bold=True)
            med_font = pygame.font.SysFont("arial", 30, bold=True)
            sml_font = pygame.font.SysFont("arial", 22)
        except Exception:
            big_font = pygame.font.Font(None, 64)
            med_font = pygame.font.Font(None, 30)
            sml_font = pygame.font.Font(None, 22)

        # Shadow + title
        shadow = big_font.render("GAME OVER", True, (80, 0, 0))
        title  = big_font.render("GAME OVER", True, (230, 50, 50))
        self.screen.blit(shadow, (cx - shadow.get_width() // 2 + 3, cy - 110 + 3))
        self.screen.blit(title,  (cx - title.get_width()  // 2,     cy - 110))

        # ── Divider ─────────────────────────────────────────────────────
        pygame.draw.line(self.screen, (180, 60, 60),
                         (cx - 200, cy - 60), (cx + 200, cy - 60), 2)

        # ── Điểm P1 (local player) ─────────────────────────────────────
        p1_label = med_font.render(f"▲ {self.player_name}  (You)", True, (255, 255, 150))
        p1_score = med_font.render(f"Score: {self.score}", True, (255, 255, 150))
        self.screen.blit(p1_label, (cx - p1_label.get_width() // 2, cy - 45))
        self.screen.blit(p1_score, (cx - p1_score.get_width() // 2, cy - 10))

        # ── Divider nhỏ ─────────────────────────────────────────────────
        pygame.draw.line(self.screen, (80, 120, 180),
                         (cx - 160, cy + 28), (cx + 160, cy + 28), 1)

        # ── Điểm P2 (partner) ──────────────────────────────────────────
        pstate = self.client.get_partner_state()
        p2_score_val = pstate.get("score", 0) if pstate else 0
        p2_name = self.partner.name

        p2_label = med_font.render(f"▲ {p2_name}  (Partner)", True, (160, 220, 255))
        p2_score = med_font.render(f"Score: {p2_score_val}", True, (160, 220, 255))
        self.screen.blit(p2_label, (cx - p2_label.get_width() // 2, cy + 38))
        self.screen.blit(p2_score, (cx - p2_score.get_width() // 2, cy + 72))

        # ── Tổng điểm chung ─────────────────────────────────────────────
        pygame.draw.line(self.screen, (180, 180, 180),
                         (cx - 200, cy + 108), (cx + 200, cy + 108), 2)
        total = self.score + p2_score_val
        total_surf = med_font.render(f"Total Team Score: {total}", True, (255, 220, 100))
        self.screen.blit(total_surf, (cx - total_surf.get_width() // 2, cy + 116))

        # ── Hint thoát ──────────────────────────────────────────────────
        hint = sml_font.render("Thoát sau 3 giây...", True, (140, 140, 140))
        self.screen.blit(hint, (cx - hint.get_width() // 2, cy + 160))

    # ─────────────────────────────────────────────────────
    # Helpers (delegate to GameScreen methods)
    # ─────────────────────────────────────────────────────

    def _spawn_local_damage_text(self, amount: int, world_x: float, world_y: float):
        """Tạo damage text cho local player (đỏ) và gửi event sang partner để hiển thị bên kia."""
        dt = DamageText(amount, world_x, world_y, self.ui_font)
        self.damage_text_group.add(dt)
        # Gửi event để máy partner cũng hiển thị damage text tại vị trí này
        self.client.send_event("player_damaged", {
            "amount": amount,
            "x": float(world_x),
            "y": float(world_y),
        })

    def _check_player_enemy_collision(self):
        if self.damage_cooldown > 0:
            return
        player_rect = pygame.Rect(
            int(self.player_x + self.hitbox_inset),
            int(self.player_y + self.hitbox_inset),
            self.player_w - 2 * self.hitbox_inset,
            self.player_h - 2 * self.hitbox_inset,
        )
        dmg = 0
        for skel in self.skeleton_group:
            if player_rect.colliderect(skel.rect):
                dmg = 5
                break
        for boss in self.boss_group:
            if player_rect.colliderect(boss.rect):
                dmg = 10
                break
        if dmg:
            self.health = max(0, self.health - dmg)
            self.damage_cooldown = self.damage_cooldown_time
            if self.damage_sound:
                self.damage_sound.play()
            # Hiện damage text ngay + đồng bộ sang partner
            self._spawn_local_damage_text(
                dmg,
                self.player_x + self.player_w // 2,
                self.player_y,
            )
            self._send_my_state()
            if self.health <= 0:
                self.client.send_event("died")
                self._respawn()

    def _check_player_item_collision(self):
        px = int(self.player_x)
        py = int(self.player_y)
        player_rect = pygame.Rect(px, py, self.player_w, self.player_h)

        # Coins
        for coin in list(self.coin_group):
            if player_rect.colliderect(coin.rect):
                self.score += 100
                coin.kill()
                if self.coin_sound:
                    self.coin_sound.play()
                self.client.send_event("collect_coin", {
                    "x": coin.rect.x, "y": coin.rect.y
                })

        # Sword
        for sword in list(self.sword_group):
            if id(sword) in self._collected_sword_ids:
                continue
            if player_rect.colliderect(sword.rect):
                self.has_sword = True
                self.sword_health = self.sword_max_health
                sword.kill()
                self._collected_sword_ids.discard(id(sword))
                self.client.send_event("collect_sword", {
                    "x": sword.rect.x, "y": sword.rect.y
                })
        # Stars
        for star in list(self.star_group):
            if player_rect.colliderect(star.rect):
                self.score += 500
                star.kill()
                if self.star_sound:
                    self.star_sound.play()
                self.client.send_event("collect_star", {
                    "x": star.rect.x, "y": star.rect.y
                })

        # Keys
        for key in list(self.key_group):
            if player_rect.colliderect(key.rect):
                self.keys_collected += 1
                key.kill()
                self.client.send_event("collect_key", {
                    "x": key.rect.x, "y": key.rect.y
                })

    def _remove_nearest_object(self, group, x: int, y: int, threshold: int = 64):
        best = None
        best_dist = threshold
        for obj in group:
            dist = abs(obj.rect.x - x) + abs(obj.rect.y - y)
            if dist < best_dist:
                best_dist = dist
                best = obj
        if best:
            best.kill()

    def _check_lava_collision(self):
        if self.lava_damage_cooldown > 0:
            return
        player_rect = pygame.Rect(int(self.player_x), int(self.player_y), self.player_w, self.player_h)
        col_min = max(0, player_rect.left // 32)
        col_max = min(self.map_width_tiles - 1, player_rect.right // 32)
        row_min = max(0, player_rect.top // 32)
        row_max = min(self.map_height_tiles - 1, player_rect.bottom // 32)

        for col in range(col_min, col_max + 1):
            for row in range(row_min, row_max + 1):
                try:
                    gid = self.tmx_data.get_tile_gid(col, row, self.layer_index)
                    if gid in self.lava_gids:
                        self.health = max(0, self.health - 3)
                        self.lava_damage_cooldown = self.lava_damage_interval
                        if self.lava_sound:
                            self.lava_sound.play()
                        self._spawn_local_damage_text(
                            3,
                            self.player_x + self.player_w // 2,
                            self.player_y,
                        )
                        self._send_my_state()
                        if self.health <= 0:
                            self.client.send_event("died")
                            self._respawn()
                        return
                except Exception:
                    pass

    def _check_bullet_collision(self):
        if self.damage_cooldown > 0:
            return
        player_rect = pygame.Rect(int(self.player_x), int(self.player_y), self.player_w, self.player_h)
        for bullet in list(self.bullet_group):
            if player_rect.colliderect(bullet.rect):
                self.health = max(0, self.health - 5)
                self.damage_cooldown = self.damage_cooldown_time
                bullet.kill()
                if self.damage_sound:
                    self.damage_sound.play()
                self._spawn_local_damage_text(
                    5,
                    self.player_x + self.player_w // 2,
                    self.player_y,
                )
                self._send_my_state()
                break

    def _respawn(self):
        self._game_over = True
        self._game_over_reason = f"💀 {self.player_name} died!\nGAME OVER"

    def _draw_tile_layer(self):
        if self.layer is None:
            return

        for x, y, image in self.layer.tiles():
            if image is None:
                continue
            px = x * self.tile_width - int(self.camera_x)
            py = y * self.tile_height - int(self.camera_y)

            # Cull tile ngoài viewport
            if px + self.tile_width < 0 or px > self.window_width:
                continue
            if py + self.tile_height < 0 or py > self.window_height:
                continue

            self.screen.blit(image, (px, py))