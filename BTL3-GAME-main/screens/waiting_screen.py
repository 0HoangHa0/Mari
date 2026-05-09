import pygame

from utils.assets import safe_load_image, resource_path, safe_load_font


class WaitingScreen:
    def __init__(self, screen, window_size):
        self.screen = screen
        self.window_width, self.window_height = window_size

        self.background = safe_load_image(pygame, 'Images', 'Background', 'Background.jpg')
        self.btn_normal = safe_load_image(pygame, 'btn-play-normal.png')
        self.btn_hover = safe_load_image(pygame, 'btn-play-selected.png')

        self.background_scaled = None
        self.button_image = self.btn_normal
        self.button_rect = self.btn_normal.get_rect()
        self.button_rect.center = (self.window_width // 2, int(self.window_height * 0.75))

        try:
            self.title_font = safe_load_font(pygame, 'fonts/arial.ttf', 48)
        except Exception:
            self.title_font = pygame.font.SysFont('arial', 48)


    def _scale_background(self):
        bg_w, bg_h = self.background.get_size()
        scale = max(self.window_width / bg_w, self.window_height / bg_h)
        new_size = (int(bg_w * scale), int(bg_h * scale))
        self.background_scaled = pygame.transform.smoothscale(self.background, new_size)

    def run(self):
        if self.background_scaled is None:
            self._scale_background()

        clock = pygame.time.Clock()
        started = False

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
                if event.type == pygame.MOUSEMOTION:
                    self._update_button_hover(event.pos)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.button_rect.collidepoint(event.pos):
                        started = True
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    started = True

            if started:
                return True

            self._draw()
            pygame.display.flip()
            clock.tick(60)

    def _update_button_hover(self, mouse_pos):
        if self.button_rect.collidepoint(mouse_pos):
            self.button_image = self.btn_hover
        else:
            self.button_image = self.btn_normal

    def _draw(self):
        if self.background_scaled is None:
            self._scale_background()

        bg_rect = self.background_scaled.get_rect()
        bg_rect.center = (self.window_width // 2, self.window_height // 2)
        self.screen.blit(self.background_scaled, bg_rect)
        self.screen.blit(self.button_image, self.button_rect)


