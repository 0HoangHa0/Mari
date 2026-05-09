import pygame

from utils.assets import safe_load_image, safe_load_font


class AboutScreen:
    def __init__(self, screen, window_size):
        self.screen = screen
        self.window_width, self.window_height = window_size

        # Load background
        self.background = safe_load_image(pygame, 'Images', 'Background', 'Background.jpg')
        self.background_scaled = None

        # Load fonts
        try:
            self.title_font = safe_load_font(pygame, 'fonts/arial.ttf', 48)
            self.text_font = safe_load_font(pygame, 'fonts/arial.ttf', 24)
            self.menu_font = safe_load_font(pygame, 'fonts/arial.ttf', 32)
        except Exception:
            self.title_font = pygame.font.SysFont('arial', 48)
            self.text_font = pygame.font.SysFont('arial', 24)
            self.menu_font = pygame.font.SysFont('arial', 32)

        # Colors
        self.color_normal = (255, 255, 255)
        self.color_title = (255, 255, 255)
        self.color_back = (200, 200, 200)

        # Back button
        self.back_rect = None

    def _scale_background(self):
        bg_w, bg_h = self.background.get_size()
        scale = max(self.window_width / bg_w, self.window_height / bg_h)
        new_size = (int(bg_w * scale), int(bg_h * scale))
        self.background_scaled = pygame.transform.smoothscale(self.background, new_size)

    def run(self):
        """Run the about screen"""
        if self.background_scaled is None:
            self._scale_background()

        clock = pygame.time.Clock()
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
                
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return True
                
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.back_rect and self.back_rect.collidepoint(event.pos):
                        return True

            self._draw()
            pygame.display.flip()
            clock.tick(60)

        return True

    def _draw(self):
        """Draw the about screen"""
        if self.background_scaled is None:
            self._scale_background()

        # Draw background
        bg_rect = self.background_scaled.get_rect()
        bg_rect.center = (self.window_width // 2, self.window_height // 2)
        self.screen.blit(self.background_scaled, bg_rect)

        # Draw title
        title_text = "ABOUT"
        title_surface = self.title_font.render(title_text, True, self.color_title)
        title_rect = title_surface.get_rect()
        title_rect.centerx = self.window_width // 2
        title_rect.y = int(self.window_height * 0.15)
        self.screen.blit(title_surface, title_rect)

        # Draw about text
        about_lines = [
            "Game Platform",
            "",
            "A platform game built with Pygame",
            "",
            "Version 1.0",
            "",
            "Use arrow keys or mouse to navigate",
            "Press Enter or Space to select",
        ]
        
        start_y = int(self.window_height * 0.3)
        spacing = 35
        
        for i, line in enumerate(about_lines):
            if line:  # Skip empty lines
                text_surface = self.text_font.render(line, True, self.color_normal)
                text_rect = text_surface.get_rect()
                text_rect.centerx = self.window_width // 2
                text_rect.y = start_y + i * spacing
                self.screen.blit(text_surface, text_rect)

        # Draw back button
        back_text = "Press ESC or Click to go back"
        back_surface = self.menu_font.render(back_text, True, self.color_back)
        self.back_rect = back_surface.get_rect()
        self.back_rect.centerx = self.window_width // 2
        self.back_rect.y = int(self.window_height * 0.85)
        self.screen.blit(back_surface, self.back_rect)


