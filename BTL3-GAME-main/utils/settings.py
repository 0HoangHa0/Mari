"""
Settings management for the game
"""
import json
import os


class Settings:
    def __init__(self):
        self.volume = 1.0  # 0.0 to 1.0
        self.music_volume = 1.0
        self.sound_volume = 1.0
        self.fullscreen = False
        self.window_size = (960, 540)
        self.settings_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'settings.json')
        self.load()

    def load(self):
        """Load settings from file"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    self.volume = data.get('volume', 1.0)
                    self.music_volume = data.get('music_volume', 1.0)
                    self.sound_volume = data.get('sound_volume', 1.0)
                    self.fullscreen = data.get('fullscreen', False)
                    window_size_data = data.get('window_size', [960, 540])
                    self.window_size = tuple(window_size_data)
            except Exception:
                # If loading fails, use defaults
                pass

    def save(self):
        """Save settings to file"""
        try:
            data = {
                'volume': self.volume,
                'music_volume': self.music_volume,
                'sound_volume': self.sound_volume,
                'fullscreen': self.fullscreen,
                'window_size': list(self.window_size)
            }
            with open(self.settings_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            # If saving fails, silently continue
            pass

    def apply_volume(self):
        """Apply volume settings to pygame mixer"""
        try:
            import pygame
            pygame.mixer.music.set_volume(self.music_volume * self.volume)
        except Exception:
            pass


# Global settings instance
_settings_instance = None


def get_settings():
    """Get the global settings instance"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance

