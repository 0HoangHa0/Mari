import os
import sys

import pygame

from screens.menu_screen import MenuScreen
from screens.game_screen import GameScreen
from screens.option_screen import OptionScreen
from screens.about_screen import AboutScreen
from utils.settings import get_settings


def init_pygame(window_size):
    pygame.init()
    settings = get_settings()
    if settings.fullscreen:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    else:
        screen = pygame.display.set_mode(window_size)
    pygame.display.set_caption('Game Platform')
    return screen


def main():
    settings = get_settings()
    window_size = settings.window_size if hasattr(settings, 'window_size') else (960, 540)
    screen = init_pygame(window_size)
    window_size = screen.get_size()

    running = True
    while running:
        menu = MenuScreen(screen, window_size)
        action = menu.run()

        if action == 'exit':
            running = False

        elif action == 'new_game':
            game = GameScreen(screen, window_size)
            game.run()

        elif action == 'online_co-op':
            # Import lazy để không crash nếu websocket-client chưa cài
            try:
                from screens.online_screen import OnlineScreen
                from screens.online_game_screen import OnlineGameScreen

                online_lobby = OnlineScreen(screen, window_size)
                result, client = online_lobby.run()

                if result == 'start' and client is not None:
                    player_name = client.my_name or "Player"
                    online_game = OnlineGameScreen(screen, window_size, client, player_name)
                    online_game.run()
                    client.stop()

            except ImportError as e:
                # websocket-client chưa được cài → thông báo
                _show_error_screen(
                    screen, window_size,
                    f"Thiếu thư viện: {e}\n\nCài đặt: pip install websocket-client websockets"
                )

        elif action == 'option':
            option = OptionScreen(screen, window_size)
            option.run()
            current_surface = pygame.display.get_surface()
            if current_surface is not None:
                screen = current_surface
                window_size = screen.get_size()

        elif action == 'about':
            about = AboutScreen(screen, window_size)
            about.run()

    pygame.quit()
    return 0


def _show_error_screen(screen, window_size, message: str):
    """Màn hình thông báo lỗi đơn giản."""
    pygame.font.init()
    font_big   = pygame.font.SysFont('arial', 28, bold=True)
    font_small = pygame.font.SysFont('arial', 22)
    font_hint  = pygame.font.SysFont('arial', 20)

    clock = pygame.time.Clock()
    w, h = window_size

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                return
            if event.type == pygame.MOUSEBUTTONDOWN:
                return

        screen.fill((20, 20, 40))

        title = font_big.render("⚠ Không thể khởi động Online", True, (255, 120, 60))
        screen.blit(title, (w // 2 - title.get_width() // 2, h // 3))

        y = h // 3 + 50
        for line in message.split('\n'):
            surf = font_small.render(line.strip(), True, (220, 220, 220))
            screen.blit(surf, (w // 2 - surf.get_width() // 2, y))
            y += 32

        hint = font_hint.render("Nhấn bất kỳ phím nào để quay lại menu", True, (150, 150, 170))
        screen.blit(hint, (w // 2 - hint.get_width() // 2, h * 3 // 4))

        pygame.display.flip()
        clock.tick(30)


if __name__ == '__main__':
    sys.exit(main())