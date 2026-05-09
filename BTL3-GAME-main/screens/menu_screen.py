import pygame

from utils.assets import safe_load_image, resource_path, safe_load_font


class MenuScreen:
    def __init__(self, screen, window_size):
        self.screen = screen
        self.window_width, self.window_height = window_size

        # Load background
        self.background = safe_load_image(pygame, 'Images', 'Background', 'Background.jpg')
        self.background_scaled = None

        # Load fonts
        try:
            self.title_font = safe_load_font(pygame, 'fonts/arial.ttf', 64)
            self.menu_font = safe_load_font(pygame, 'fonts/arial.ttf', 36)
        except Exception:
            self.title_font = pygame.font.SysFont('arial', 64)
            self.menu_font = pygame.font.SysFont('arial', 36)

        # ── Menu options (thêm Online) ──────────────────
        self.menu_options = ['New Game', 'Online Co-op', 'Option', 'About', 'Exit']
        self.selected_index = 0
        self.menu_rects = []

        # Colors
        self.color_normal   = (245, 245, 245)
        self.color_selected = (255, 225, 60)
        self.color_online   = (80, 210, 255)   # Màu đặc biệt cho Online
        self.color_title    = (255, 255, 255)
        self.color_outline  = (0, 0, 0)

        self._calculate_menu_positions()

    def _scale_background(self):
        bg_w, bg_h = self.background.get_size()
        scale = max(self.window_width / bg_w, self.window_height / bg_h)
        new_size = (int(bg_w * scale), int(bg_h * scale))
        self.background_scaled = pygame.transform.smoothscale(self.background, new_size)

    def _calculate_menu_positions(self):
        title_y = int(self.window_height * 0.2)
        menu_start_y = int(self.window_height * 0.42)
        menu_spacing = 56

        self.title_rect = None
        self.menu_rects = []
        for i, option in enumerate(self.menu_options):
            text_surface = self.menu_font.render(option, True, self.color_normal)
            text_rect = text_surface.get_rect()
            text_rect.centerx = self.window_width // 2
            text_rect.y = menu_start_y + i * menu_spacing
            self.menu_rects.append(text_rect)

    def run(self):
        if self.background_scaled is None:
            self._scale_background()

        clock = pygame.time.Clock()
        action = None

        while action is None:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return 'exit'

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP:
                        self.selected_index = (self.selected_index - 1) % len(self.menu_options)
                    elif event.key == pygame.K_DOWN:
                        self.selected_index = (self.selected_index + 1) % len(self.menu_options)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        action = self.menu_options[self.selected_index].lower().replace(' ', '_')

                if event.type == pygame.MOUSEMOTION:
                    self._update_selection_from_mouse(event.pos)

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    clicked_option = self._get_option_at_position(event.pos)
                    if clicked_option is not None:
                        action = clicked_option.lower().replace(' ', '_')

            self._draw()
            pygame.display.flip()
            clock.tick(60)

        return action

    def _update_selection_from_mouse(self, mouse_pos):
        for i, rect in enumerate(self.menu_rects):
            if rect.collidepoint(mouse_pos):
                self.selected_index = i
                break

    def _get_option_at_position(self, mouse_pos):
        for i, rect in enumerate(self.menu_rects):
            if rect.collidepoint(mouse_pos):
                return self.menu_options[i]
        return None

    def _blit_text_with_outline(self, text, font, color, rect, outline_color=None, thickness=2):
        if outline_color is None:
            outline_color = self.color_outline
        base_surface = font.render(text, True, color)
        outlined_surface = font.render(text, True, outline_color)
        if thickness > 0:
            for ox in range(-thickness, thickness + 1):
                for oy in range(-thickness, thickness + 1):
                    if ox == 0 and oy == 0:
                        continue
                    self.screen.blit(outlined_surface, (rect.x + ox, rect.y + oy))
        self.screen.blit(base_surface, rect)

    def _draw(self):
        # Background
        bg_rect = self.background_scaled.get_rect()
        bg_rect.center = (self.window_width // 2, self.window_height // 2)
        self.screen.blit(self.background_scaled, bg_rect)

        # Overlay
        overlay = pygame.Surface((int(self.window_width * 0.5), int(self.window_height * 0.75)), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 110))
        overlay_rect = overlay.get_rect(center=(self.window_width // 2, int(self.window_height * 0.5)))
        self.screen.blit(overlay, overlay_rect)

        # Title
        title_text = "GAME PLATFORM"
        title_surface = self.title_font.render(title_text, True, self.color_title)
        title_rect = title_surface.get_rect()
        title_rect.centerx = self.window_width // 2
        title_rect.y = int(self.window_height * 0.17)
        self._blit_text_with_outline(title_text, self.title_font, self.color_title, title_rect, thickness=3)

        # Menu options
        for i, option in enumerate(self.menu_options):
            is_selected = (i == self.selected_index)
            is_online = (option == 'Online Co-op')

            if is_selected:
                color = self.color_selected
            elif is_online:
                color = self.color_online
            else:
                color = self.color_normal

            text_surface = self.menu_font.render(option, True, color)
            text_rect = text_surface.get_rect()
            text_rect.centerx = self.window_width // 2
            text_rect.y = self.menu_rects[i].y

            # Arrow indicator
            if is_selected:
                indicator_size = 20
                indicator_x = text_rect.left - indicator_size - 10
                indicator_y = text_rect.centery
                points = [
                    (indicator_x, indicator_y - indicator_size // 2),
                    (indicator_x + indicator_size, indicator_y),
                    (indicator_x, indicator_y + indicator_size // 2)
                ]
                pygame.draw.polygon(self.screen, self.color_selected, points)

            # Online badge
            if is_online and not is_selected:
                badge_font = pygame.font.SysFont('arial', 16, bold=True)
                badge = badge_font.render("2P", True, (255, 255, 255))
                badge_bg = pygame.Rect(text_rect.right + 8, text_rect.centery - 10, 26, 20)
                pygame.draw.rect(self.screen, (60, 140, 210), badge_bg, border_radius=4)
                self.screen.blit(badge, (badge_bg.x + 3, badge_bg.y + 2))

            thickness = 2 if is_selected else 1
            self._blit_text_with_outline(option, self.menu_font, color, text_rect, thickness=thickness)