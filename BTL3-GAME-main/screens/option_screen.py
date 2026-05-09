import pygame

from utils.assets import safe_load_image, safe_load_font
from utils.settings import get_settings


class OptionScreen:
    def __init__(self, screen, window_size):
        self.screen = screen
        self.window_width, self.window_height = window_size
        self.settings = get_settings()

        # Load background
        self.background = safe_load_image(pygame, 'Images', 'Background', 'Background.jpg')
        self.background_scaled = None

        # Load fonts
        try:
            self.title_font = safe_load_font(pygame, 'fonts/arial.ttf', 48)
            self.menu_font = safe_load_font(pygame, 'fonts/arial.ttf', 28)
            self.label_font = safe_load_font(pygame, 'fonts/arial.ttf', 24)
        except Exception:
            self.title_font = pygame.font.SysFont('arial', 48)
            self.menu_font = pygame.font.SysFont('arial', 28)
            self.label_font = pygame.font.SysFont('arial', 24)

        # Colors
        self.color_normal = (255, 255, 255)
        self.color_title = (255, 255, 255)
        self.color_back = (200, 200, 200)
        self.color_selected = (255, 215, 0)
        self.color_slider_bg = (100, 100, 100)
        self.color_slider_fill = (0, 150, 255)
        self.color_slider_handle = (255, 255, 255)

        # Option items
        self.options = [
            {'name': 'Master Volume', 'type': 'slider', 'value': self.settings.volume, 'min': 0.0, 'max': 1.0, 'key': 'volume'},
            {'name': 'Music Volume', 'type': 'slider', 'value': self.settings.music_volume, 'min': 0.0, 'max': 1.0, 'key': 'music_volume'},
            {'name': 'Sound Volume', 'type': 'slider', 'value': self.settings.sound_volume, 'min': 0.0, 'max': 1.0, 'key': 'sound_volume'},
            {'name': 'Fullscreen', 'type': 'toggle', 'value': self.settings.fullscreen, 'key': 'fullscreen'},
            {'name': 'Controls', 'type': 'info', 'key': 'controls'},
        ]
        
        self.selected_index = 0
        self.dragging_slider = None
        self.slider_rects = []
        self.toggle_rects = []
        self.info_rects = []
        self.back_rect = None

        # Controls info
        self.controls_info = [
            "Arrow Keys / WASD: Move",
            "Space / Up Arrow: Jump",
            "Z / X: Attack",
            "ESC: Pause / Menu"
        ]

    def _scale_background(self):
        bg_w, bg_h = self.background.get_size()
        scale = max(self.window_width / bg_w, self.window_height / bg_h)
        new_size = (int(bg_w * scale), int(bg_h * scale))
        self.background_scaled = pygame.transform.smoothscale(self.background, new_size)

    def _calculate_positions(self):
        """Calculate positions for all UI elements"""
        self.slider_rects = []
        self.toggle_rects = []
        self.info_rects = []
        
        start_y = int(self.window_height * 0.3)
        spacing = 60
        slider_width = 300
        slider_height = 20
        slider_x = self.window_width // 2 - slider_width // 2
        
        for i, option in enumerate(self.options):
            y_pos = start_y + i * spacing
            
            if option['type'] == 'slider':
                # Slider background
                slider_bg_rect = pygame.Rect(slider_x, y_pos, slider_width, slider_height)
                # Slider handle position based on value
                handle_x = slider_x + int((option['value'] - option['min']) / (option['max'] - option['min']) * slider_width)
                handle_rect = pygame.Rect(handle_x - 8, y_pos - 6, 16, 32)
                self.slider_rects.append({
                    'bg': slider_bg_rect,
                    'handle': handle_rect,
                    'option_index': i
                })
            elif option['type'] == 'toggle':
                toggle_rect = pygame.Rect(slider_x + slider_width - 100, y_pos - 5, 80, 30)
                self.toggle_rects.append({
                    'rect': toggle_rect,
                    'option_index': i
                })
            elif option['type'] == 'info':
                info_rect = pygame.Rect(slider_x, y_pos, slider_width, 30)
                self.info_rects.append({
                    'rect': info_rect,
                    'option_index': i
                })

    def run(self):
        """Run the options screen"""
        if self.background_scaled is None:
            self._scale_background()
        
        self._calculate_positions()

        clock = pygame.time.Clock()
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
                
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.settings.save()
                        return True
                    elif event.key == pygame.K_UP:
                        self.selected_index = (self.selected_index - 1) % len(self.options)
                    elif event.key == pygame.K_DOWN:
                        self.selected_index = (self.selected_index + 1) % len(self.options)
                    elif event.key == pygame.K_LEFT:
                        self._adjust_selected(-0.1)
                    elif event.key == pygame.K_RIGHT:
                        self._adjust_selected(0.1)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self._toggle_selected()
                
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mouse_pos = event.pos
                    
                    # Check sliders
                    for slider_data in self.slider_rects:
                        if slider_data['bg'].collidepoint(mouse_pos) or slider_data['handle'].collidepoint(mouse_pos):
                            self.dragging_slider = slider_data['option_index']
                            self._update_slider_from_mouse(mouse_pos)
                            break
                    
                    # Check toggles
                    for toggle_data in self.toggle_rects:
                        if toggle_data['rect'].collidepoint(mouse_pos):
                            option = self.options[toggle_data['option_index']]
                            option['value'] = not option['value']
                            self._apply_option(toggle_data['option_index'])
                            break
                    
                    # Check info (show controls)
                    for info_data in self.info_rects:
                        if info_data['rect'].collidepoint(mouse_pos):
                            # Toggle controls display
                            if 'show_controls' not in self.options[info_data['option_index']]:
                                self.options[info_data['option_index']]['show_controls'] = True
                            else:
                                self.options[info_data['option_index']]['show_controls'] = not self.options[info_data['option_index']]['show_controls']
                            break
                    
                    # Check back button
                    if self.back_rect and self.back_rect.collidepoint(mouse_pos):
                        self.settings.save()
                        return True
                
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self.dragging_slider = None
                
                if event.type == pygame.MOUSEMOTION:
                    if self.dragging_slider is not None:
                        self._update_slider_from_mouse(event.pos)
                    else:
                        # Update selection based on mouse position
                        self._update_selection_from_mouse(event.pos)

            self._draw()
            pygame.display.flip()
            clock.tick(60)

        self.settings.save()
        return True

    def _update_selection_from_mouse(self, mouse_pos):
        """Update selected index based on mouse position"""
        for i, option in enumerate(self.options):
            if option['type'] == 'slider':
                for slider_data in self.slider_rects:
                    if slider_data['option_index'] == i:
                        if slider_data['bg'].collidepoint(mouse_pos) or slider_data['handle'].collidepoint(mouse_pos):
                            self.selected_index = i
                            return
            elif option['type'] == 'toggle':
                for toggle_data in self.toggle_rects:
                    if toggle_data['option_index'] == i:
                        if toggle_data['rect'].collidepoint(mouse_pos):
                            self.selected_index = i
                            return
            elif option['type'] == 'info':
                for info_data in self.info_rects:
                    if info_data['option_index'] == i:
                        if info_data['rect'].collidepoint(mouse_pos):
                            self.selected_index = i
                            return

    def _update_slider_from_mouse(self, mouse_pos):
        """Update slider value based on mouse position"""
        if self.dragging_slider is None:
            return
        
        option = self.options[self.dragging_slider]
        if option['type'] != 'slider':
            return
        
        for slider_data in self.slider_rects:
            if slider_data['option_index'] == self.dragging_slider:
                slider_bg = slider_data['bg']
                # Clamp mouse x to slider bounds
                mouse_x = max(slider_bg.left, min(slider_bg.right, mouse_pos[0]))
                # Calculate value
                ratio = (mouse_x - slider_bg.left) / slider_bg.width
                option['value'] = option['min'] + ratio * (option['max'] - option['min'])
                option['value'] = max(option['min'], min(option['max'], option['value']))
                self._apply_option(self.dragging_slider)
                break

    def _adjust_selected(self, delta):
        """Adjust the selected option value"""
        option = self.options[self.selected_index]
        if option['type'] == 'slider':
            option['value'] = max(option['min'], min(option['max'], option['value'] + delta))
            self._apply_option(self.selected_index)

    def _toggle_selected(self):
        """Toggle the selected option"""
        option = self.options[self.selected_index]
        if option['type'] == 'toggle':
            option['value'] = not option['value']
            self._apply_option(self.selected_index)

    def _apply_option(self, index):
        """Apply the option value to settings"""
        option = self.options[index]
        key = option['key']
        
        if key == 'volume':
            self.settings.volume = option['value']
        elif key == 'music_volume':
            self.settings.music_volume = option['value']
        elif key == 'sound_volume':
            self.settings.sound_volume = option['value']
        elif key == 'fullscreen':
            self.settings.fullscreen = option['value']
            # Apply fullscreen change immediately by recreating display
            if self.settings.fullscreen:
                self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            else:
                target_size = getattr(self.settings, 'window_size', (960, 540))
                self.screen = pygame.display.set_mode(target_size)

            self.window_width, self.window_height = self.screen.get_size()
            self.background_scaled = None
            self._calculate_positions()

        self.settings.save()

    def _draw(self):
        """Draw the options screen"""
        if self.background_scaled is None:
            self._scale_background()
        if self.background_scaled is None:
            return

        # Draw background
        bg_rect = self.background_scaled.get_rect()
        bg_rect.center = (self.window_width // 2, self.window_height // 2)
        self.screen.blit(self.background_scaled, bg_rect)

        # Draw title
        title_text = "OPTIONS"
        title_surface = self.title_font.render(title_text, True, self.color_title)
        title_rect = title_surface.get_rect()
        title_rect.centerx = self.window_width // 2
        title_rect.y = int(self.window_height * 0.15)
        self.screen.blit(title_surface, title_rect)

        # Draw options
        start_y = int(self.window_height * 0.3)
        spacing = 60
        slider_width = 300
        slider_height = 20
        slider_x = self.window_width // 2 - slider_width // 2

        for i, option in enumerate(self.options):
            y_pos = start_y + i * spacing
            is_selected = (i == self.selected_index)
            
            # Draw option label
            label_text = option['name'] + ":"
            label_color = self.color_selected if is_selected else self.color_normal
            label_surface = self.label_font.render(label_text, True, label_color)
            label_rect = label_surface.get_rect()
            label_rect.right = slider_x - 20
            label_rect.centery = y_pos + 10
            self.screen.blit(label_surface, label_rect)

            if option['type'] == 'slider':
                # Draw slider background
                slider_bg_rect = pygame.Rect(slider_x, y_pos, slider_width, slider_height)
                pygame.draw.rect(self.screen, self.color_slider_bg, slider_bg_rect)
                
                # Draw filled portion
                fill_width = int((option['value'] - option['min']) / (option['max'] - option['min']) * slider_width)
                fill_rect = pygame.Rect(slider_x, y_pos, fill_width, slider_height)
                pygame.draw.rect(self.screen, self.color_slider_fill, fill_rect)
                
                # Draw handle
                handle_x = slider_x + fill_width - 8
                handle_rect = pygame.Rect(handle_x, y_pos - 6, 16, 32)
                handle_color = self.color_selected if is_selected else self.color_slider_handle
                pygame.draw.rect(self.screen, handle_color, handle_rect)
                pygame.draw.rect(self.screen, (0, 0, 0), handle_rect, 2)
                
                # Draw value text
                value_text = f"{int(option['value'] * 100)}%"
                value_surface = self.label_font.render(value_text, True, label_color)
                value_rect = value_surface.get_rect()
                value_rect.left = slider_x + slider_width + 20
                value_rect.centery = y_pos + 10
                self.screen.blit(value_surface, value_rect)
                
                # Update slider rects
                for slider_data in self.slider_rects:
                    if slider_data['option_index'] == i:
                        slider_data['bg'] = slider_bg_rect
                        slider_data['handle'] = handle_rect
                        break

            elif option['type'] == 'toggle':
                # Draw toggle button
                toggle_rect = pygame.Rect(slider_x + slider_width - 100, y_pos - 5, 80, 30)
                toggle_color = (0, 200, 0) if option['value'] else (150, 150, 150)
                pygame.draw.rect(self.screen, toggle_color, toggle_rect)
                pygame.draw.rect(self.screen, (255, 255, 255), toggle_rect, 2)
                
                # Draw toggle text
                toggle_text = "ON" if option['value'] else "OFF"
                toggle_surface = self.label_font.render(toggle_text, True, (255, 255, 255))
                toggle_text_rect = toggle_surface.get_rect()
                toggle_text_rect.center = toggle_rect.center
                self.screen.blit(toggle_surface, toggle_text_rect)
                
                # Update toggle rects
                for toggle_data in self.toggle_rects:
                    if toggle_data['option_index'] == i:
                        toggle_data['rect'] = toggle_rect
                        break

            elif option['type'] == 'info':
                # Draw info button
                info_rect = pygame.Rect(slider_x, y_pos, slider_width, 30)
                info_color = self.color_selected if is_selected else self.color_slider_bg
                pygame.draw.rect(self.screen, info_color, info_rect)
                pygame.draw.rect(self.screen, (255, 255, 255), info_rect, 2)
                
                info_text = "Click to show/hide controls"
                info_surface = self.label_font.render(info_text, True, (255, 255, 255))
                info_text_rect = info_surface.get_rect()
                info_text_rect.center = info_rect.center
                self.screen.blit(info_surface, info_text_rect)
                
                # Update info rects
                for info_data in self.info_rects:
                    if info_data['option_index'] == i:
                        info_data['rect'] = info_rect
                        break
                
                # Draw controls info if shown
                if option.get('show_controls', False):
                    controls_y = y_pos + 40
                    for j, control_text in enumerate(self.controls_info):
                        control_surface = self.label_font.render(control_text, True, self.color_normal)
                        control_rect = control_surface.get_rect()
                        control_rect.left = slider_x
                        control_rect.y = controls_y + j * 25
                        self.screen.blit(control_surface, control_rect)

        # Draw back button
        back_text = "Press ESC or Click to go back"
        back_surface = self.menu_font.render(back_text, True, self.color_back)
        self.back_rect = back_surface.get_rect()
        self.back_rect.centerx = self.window_width // 2
        self.back_rect.y = int(self.window_height * 0.85)
        self.screen.blit(back_surface, self.back_rect)
