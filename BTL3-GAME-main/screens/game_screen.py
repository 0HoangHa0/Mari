import pygame
import math

try:
    from pytmx.util_pygame import load_pygame
except Exception as e:  # pragma: no cover
    load_pygame = None

from utils.tilemap import get_mainlevel_tmx_path
from utils.assets import safe_load_image, resource_path
from utils.settings import get_settings


class Coin(pygame.sprite.Sprite):
    def __init__(self, image, x, y, local_id=None, tile_x=None, tile_y=None):
        super().__init__()
        self.image = image
        self.rect = self.image.get_rect(topleft=(x, y))
        self.local_id = local_id  # ID from tile properties (7 or 11 for split coins)
        self.tile_x = tile_x  # Tile grid X position
        self.tile_y = tile_y  # Tile grid Y position


class DamageText(pygame.sprite.Sprite):
    def __init__(self, damage_amount, x, y, font):
        super().__init__()
        self.damage_amount = damage_amount
        self.font = font
        self.x = float(x)
        self.y = float(y)
        self.lifetime = 60  # 1 second at 60 FPS
        self.age = 0
        self.vy = -1.5  # Move upward
        self.update_image()
    
    def update_image(self):
        """Update the text image with fading alpha"""
        alpha = max(0, 255 - int(self.age * 255 / self.lifetime))
        text_surf = self.font.render(f"-{self.damage_amount}", True, (255, 0, 0))
        # Create surface with alpha channel
        self.image = pygame.Surface(text_surf.get_size(), pygame.SRCALPHA)
        text_surf.set_alpha(alpha)
        self.image.blit(text_surf, (0, 0))
        self.rect = self.image.get_rect(center=(int(self.x), int(self.y)))
    
    def update(self):
        """Update damage text position and fade"""
        self.age += 1
        self.y += self.vy
        self.update_image()
        if self.age >= self.lifetime:
            self.kill()


class HealEffect(pygame.sprite.Sprite):
    """Effect showing 3 '+' signs appearing sequentially above player"""
    def __init__(self, x, y, font):
        super().__init__()
        self.x = float(x)
        self.y = float(y)
        self.font = font
        self.age = 0
        self.vy = -1.0  # Move upward slower than damage text
        self.lifetime = 90  # 1.5 seconds at 60 FPS
        self.plus_signs = []  # List of (age, y_offset) for each '+' sign
        self.update_image()
    
    def update_image(self):
        """Update the heal effect image with 3 '+' signs appearing sequentially"""
        # Show first '+' after 5 frames, second after 15 frames, third after 25 frames
        signs_to_show = []
        if self.age >= 5:
            signs_to_show.append((0, 0))  # First '+' at base position
        if self.age >= 15:
            signs_to_show.append((0, -20))  # Second '+' 20px above
        if self.age >= 25:
            signs_to_show.append((0, -40))  # Third '+' 40px above
        
        if not signs_to_show:
            # Create empty surface
            self.image = pygame.Surface((20, 20), pygame.SRCALPHA)
            self.rect = self.image.get_rect(center=(int(self.x), int(self.y)))
            return
        
        # Calculate alpha for fading
        alpha = max(0, 255 - int((self.age - 25) * 255 / (self.lifetime - 25)))
        
        # Create surface to hold all '+' signs
        max_height = 60
        text_surf = self.font.render("+", True, (0, 255, 0))
        text_height = text_surf.get_height()
        surface_height = max_height
        
        self.image = pygame.Surface((text_surf.get_width() + 10, surface_height), pygame.SRCALPHA)
        
        # Draw each '+' sign
        for i, (offset_x, offset_y) in enumerate(signs_to_show):
            sign_alpha = min(255, alpha + (i * 20))  # Slightly brighter for later signs
            text_surf = self.font.render("+", True, (0, 255, 0))
            text_surf.set_alpha(sign_alpha)
            # Position: center horizontally, offset vertically
            text_rect = text_surf.get_rect()
            text_rect.centerx = self.image.get_width() // 2
            text_rect.y = surface_height - 30 + offset_y  # Start from bottom, move up
            self.image.blit(text_surf, text_rect)
        
        self.rect = self.image.get_rect(center=(int(self.x), int(self.y)))
    
    def update(self):
        """Update heal effect position and fade"""
        self.age += 1
        self.y += self.vy
        self.update_image()
        if self.age >= self.lifetime:
            self.kill()


class Sword(pygame.sprite.Sprite):
    def __init__(self, image, x, y):
        super().__init__()
        self.image = image
        self.rect = self.image.get_rect(topleft=(x, y))


class Box(pygame.sprite.Sprite):
    def __init__(self, image, x, y):
        super().__init__()
        self.image = image
        self.rect = self.image.get_rect(topleft=(x, y))
        self.health = 1  # Box has 1 health, needs 3 sword damage to break


class Star(pygame.sprite.Sprite):
    def __init__(self, image, x, y):
        super().__init__()
        self.image = image
        self.rect = self.image.get_rect(topleft=(x, y))


class Key(pygame.sprite.Sprite):
    def __init__(self, image, x, y):
        super().__init__()
        self.image = image
        self.rect = self.image.get_rect(topleft=(x, y))


class Skeleton(pygame.sprite.Sprite):
    def __init__(self, image_right, image_left, x, y):
        super().__init__()
        self.image_right = image_right
        self.image_left = image_left
        self.image = image_right  # Start facing right
        self.rect = self.image.get_rect(topleft=(x, y))
        
        # Movement properties
        self.start_x = x  # Spawn position (left bound)
        self.patrol_range = 7 * 32  # 224 pixels
        self.left_bound = self.start_x
        self.right_bound = self.start_x + self.patrol_range
        self.x = float(x)  # Use float for smooth movement
        self.y = float(y)
        self.direction = 1  # 1 = right, -1 = left (start moving right)
        self.base_speed = 2
        self.chase_speed = 2
        self.speed = self.base_speed
        self.detection_range = 7 * 32  # Same as patrol range
        self.chasing = False  # Track if currently chasing player
        
        # Hitbox properties (similar to player)
        skel_w, skel_h = self.image.get_size()
        self.skel_w = skel_w
        self.skel_h = skel_h
        self.hitbox_inset = 4  # Same as player
        
        # Physics (similar to player)
        self.vy = 0  # Vertical velocity
        self.gravity = 2  # Same as player
        self.max_fall = 20  # Same as player
        
        # Health system
        self.health = 3  # Skeleton takes 3 hits to kill
        self.max_health = 3
        self.knockback_duration = 0  # Duration of knockback effect
        self.knockback_distance = 0  # How far to knockback
        self.knockback_direction = 0  # Direction of knockback (-1 left, 1 right)
    
    def _is_grounded(self, collision_checker):
        """Check if skeleton is on ground, similar to player"""
        rect = pygame.Rect(
            int(self.x + self.hitbox_inset), 
            int(self.y + self.hitbox_inset), 
            self.skel_w - 2 * self.hitbox_inset, 
            self.skel_h - 2 * self.hitbox_inset
        )
        rect.y += 1  # Check 1px below
        return any(True for _ in collision_checker(rect))
    
    def update(self, player_x, player_y, collision_checker, world_width_px, world_height_px):
        # Calculate distance to player
        dx_to_player = player_x - self.x
        dy_to_player = abs(player_y - self.y)
        distance_to_player = abs(dx_to_player)
        
        # Only chase if player is on the same row (same Y level) and within detection range
        # Check if Y is close enough (same row/horizontal level) - within 1 tile (32px)
        same_row = dy_to_player < 32  # Allow small vertical difference (within 1 tile)
        
        if same_row and distance_to_player <= self.detection_range:
            # Player detected on same row - increase speed and chase
            self.chasing = True
            self.speed = self.chase_speed
            # Move towards player
            if dx_to_player > 0:
                self.direction = 1  # Move right
            else:
                self.direction = -1  # Move left
        else:
            # Normal patrol behavior - always patrol regardless of player position
            self.chasing = False
            self.speed = self.base_speed
            # Check if we've reached patrol boundaries
            if self.x >= self.right_bound:
                self.direction = -1  # Turn left
            elif self.x <= self.left_bound:
                self.direction = 1  # Turn right
        
        # Apply gravity and vertical movement first
        is_grounded = self._is_grounded(collision_checker)
        if not is_grounded:
            # Apply gravity
            self.vy = min(self.vy + self.gravity, self.max_fall)
        else:
            # Reset vertical velocity when grounded
            self.vy = 0
        
        # Move vertically with collision detection
        if self.vy != 0:
            self._move_vertical(self.vy, collision_checker, world_height_px)
        
        # Handle knockback first (if being knocked back)
        if self.knockback_duration > 0:
            # Apply knockback movement (32px total over 10 frames = 3.2px per frame)
            knockback_per_frame = self.knockback_distance/10 # 32 / 10 = 3.2
            dx_knockback = int(knockback_per_frame * self.knockback_direction)
            self._move_with_collision(dx_knockback, collision_checker, world_width_px)
            self.knockback_duration -= 1
            # Don't move normally during knockback
            return
        
        # Move skeleton horizontally with collision detection
        dx = self.direction * self.speed
        moved = self._move_with_collision(dx, collision_checker, world_width_px)
        
        # If movement was blocked (position didn't change), turn around and try again
        # This ensures skeleton never stops moving
        if not moved:
            # Turn around
            self.direction = -self.direction
            # Try moving in the new direction
            dx = self.direction * self.speed
            self._move_with_collision(dx, collision_checker, world_width_px)
        
        # Clamp position to patrol bounds when not chasing
        if not self.chasing:
            self.x = max(self.left_bound, min(self.x, self.right_bound))
        
        # Update image based on direction
        if self.direction > 0:
            self.image = self.image_right
        else:
            self.image = self.image_left
        
        # Update rect position
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)
    
    def take_damage(self, damage, attacker_direction, collision_checker, world_width_px):
        """Take damage and apply knockback"""
        self.health = max(0, self.health - damage)
        # Knockback: move 32px immediately in opposite direction of attacker
        self.knockback_duration = 5  # Knockback animation duration (visual only)
        self.knockback_distance = 32
        self.knockback_direction = -attacker_direction  # Opposite direction of attacker
        
        # Apply immediate knockback movement
        self._move_with_collision(32 * self.knockback_direction, collision_checker, world_width_px)
    
    def _move_with_collision(self, dx, collision_checker, world_width_px):
        """Move skeleton with collision detection, similar to player
        Returns True if movement was successful, False if blocked"""
        if dx == 0:
            return True
            
        old_x = self.x
        
        # Create hitbox with inset (same as player)
        rect = pygame.Rect(
            int(self.x + self.hitbox_inset), 
            int(self.y + self.hitbox_inset), 
            self.skel_w - 2 * self.hitbox_inset, 
            self.skel_h - 2 * self.hitbox_inset
        )
        rect.x += int(dx)
        
        # Check collision with solid tiles
        for tile_rect in collision_checker(rect):
            if dx > 0:
                # moving right: stop flush at tile's left edge
                rect.right = min(rect.right, tile_rect.left)
            else:
                # moving left: stop flush at tile's right edge
                rect.left = max(rect.left, tile_rect.right)
        
        # Update position
        new_x = rect.x - self.hitbox_inset
        self.x = max(0, min(new_x, world_width_px - self.skel_w))
        self.x = int(self.x)
        
        # Return True if position actually changed, False if blocked
        return abs(self.x - old_x) > 0.5
    
    def _move_vertical(self, dy, collision_checker, world_height_px):
        """Move skeleton vertically with collision detection"""
        if dy == 0:
            return
        
        # Create hitbox with inset
        rect = pygame.Rect(
            int(self.x + self.hitbox_inset), 
            int(self.y + self.hitbox_inset), 
            self.skel_w - 2 * self.hitbox_inset, 
            self.skel_h - 2 * self.hitbox_inset
        )
        rect.y += int(dy)
        
        # Check collision with solid tiles
        for tile_rect in collision_checker(rect):
            if dy > 0:
                # moving down: stop at tile's top
                rect.bottom = min(rect.bottom, tile_rect.top)
            else:
                # moving up: stop at tile's bottom
                rect.top = max(rect.top, tile_rect.bottom)
        
        # Update position
        new_y = rect.y - self.hitbox_inset
        self.y = max(0, min(new_y, world_height_px - self.skel_h))
        self.y = int(self.y)


class Bullet(pygame.sprite.Sprite):
    def __init__(self, image, x, y, angle):
        super().__init__()
        self.image = image
        self.rect = self.image.get_rect(center=(x, y))
        self.x = float(x)
        self.y = float(y)
        self.angle = angle  # Angle in degrees (0, 90, 180, 270)
        self.speed = 6  # Bullet speed
        
        # Convert angle to velocity components
        radians = math.radians(angle)
        self.vx = math.cos(radians) * self.speed
        self.vy = -math.sin(radians) * self.speed  # Negative because Y increases downward
    
    def update(self, world_width_px, world_height_px):
        """Update bullet position"""
        self.x += self.vx
        self.y += self.vy
        
        # Update rect position
        self.rect.center = (int(self.x), int(self.y))
        
        # Remove bullet if out of bounds
        if (self.x < -50 or self.x > world_width_px + 50 or 
            self.y < -50 or self.y > world_height_px + 50):
            self.kill()


class Boss(pygame.sprite.Sprite):
    def __init__(self, sprite_images, bullet_image, x, y):
        super().__init__()
        # sprite_images is a list of 10 images: Lightning_Ball_0.png to Lightning_Ball_9.png
        self.sprite_images = sprite_images
        self.bullet_image = bullet_image  # Store bullet image for spawning
        self.hits = 0  # Track number of hits (0-10)
        self.max_hits = 5  # Boss dies after 5 hits
        self.image = sprite_images[0]  # Start with Lightning_Ball_0.png
        self.rect = self.image.get_rect(topleft=(x, y))
        
        # Movement properties
        self.start_x = x  # Spawn position (left bound)
        self.patrol_range = 5 * 32  # 160 pixels (5 tiles)
        self.left_bound = self.start_x
        self.right_bound = self.start_x + self.patrol_range
        self.x = float(x)  # Use float for smooth movement
        self.y = float(y)
        self.direction = 1  # 1 = right, -1 = left (start moving right)
        self.speed = 2  # Boss movement speed
        
        # Hitbox properties
        boss_w, boss_h = self.image.get_size()
        self.boss_w = boss_w
        self.boss_h = boss_h
        self.hitbox_inset = 4  # Same as player
        
        # Physics (similar to player/skeleton)
        self.vy = 0  # Vertical velocity
        self.gravity = 2  # Same as player
        self.max_fall = 20  # Same as player
        
        # Health system (for display)
        self.health = 5  # Boss takes 5 hits to kill
        self.max_health = 5
        
        # Knockback system
        self.knockback_duration = 0
        self.knockback_distance = 0
        self.knockback_direction = 0
        
        # Bullet spawning
        self.bullet_cooldown = 0
        self.bullet_interval = 150  # 2.5 seconds at 60 FPS (2.5 * 60 = 150 frames)
    
    def _is_grounded(self, collision_checker):
        """Check if boss is on ground"""
        rect = pygame.Rect(
            int(self.x + self.hitbox_inset), 
            int(self.y + self.hitbox_inset), 
            self.boss_w - 2 * self.hitbox_inset, 
            self.boss_h - 2 * self.hitbox_inset
        )
        rect.y += 1  # Check 1px below
        return any(True for _ in collision_checker(rect))
    
    def update(self, player_x, player_y, collision_checker, world_width_px, world_height_px, bullet_group):
        """Update boss movement and spawn bullets"""
        # Update bullet cooldown
        if self.bullet_cooldown > 0:
            self.bullet_cooldown -= 1
        
        # Spawn bullets every 5 seconds (300 frames)
        if self.bullet_cooldown <= 0:
            self._spawn_bullets(bullet_group)
            self.bullet_cooldown = self.bullet_interval
        
        # Apply gravity and vertical movement
        is_grounded = self._is_grounded(collision_checker)
        if not is_grounded:
            # Apply gravity
            self.vy = min(self.vy + self.gravity, self.max_fall)
        else:
            # Reset vertical velocity when grounded
            self.vy = 0
        
        # Move vertically with collision detection
        if self.vy != 0:
            self._move_vertical(self.vy, collision_checker, world_height_px)
        
        # Handle knockback first (if being knocked back)
        if self.knockback_duration > 0:
            knockback_per_frame = self.knockback_distance / 10
            dx_knockback = int(knockback_per_frame * self.knockback_direction)
            self._move_with_collision(dx_knockback, collision_checker, world_width_px)
            self.knockback_duration -= 1
            return
        
        # Move boss horizontally (patrol back and forth)
        dx = self.direction * self.speed
        moved = self._move_with_collision(dx, collision_checker, world_width_px)
        
        # If movement was blocked, turn around
        if not moved:
            self.direction = -self.direction
            dx = self.direction * self.speed
            self._move_with_collision(dx, collision_checker, world_width_px)
        
        # Check if we've reached patrol boundaries and turn around
        if self.x >= self.right_bound:
            self.direction = -1  # Turn left
        elif self.x <= self.left_bound:
            self.direction = 1  # Turn right
        
        # Clamp position to patrol bounds
        self.x = max(self.left_bound, min(self.x, self.right_bound))
        
        # Update rect position
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)
    
    def _spawn_bullets(self, bullet_group):
        """Spawn bullets in 4 directions (0, 90, 180, 270 degrees)"""
        boss_center_x = self.x + self.boss_w // 2
        boss_center_y = self.y + self.boss_h // 2
        
        # Spawn 4 bullets in cardinal directions
        angles = [0,45, 90, 135, 180, 225, 270, 315]
        for angle in angles:
            bullet = Bullet(self.bullet_image, boss_center_x, boss_center_y, angle)
            bullet_group.add(bullet)
    
    def take_damage(self, damage, attacker_direction, collision_checker, world_width_px):
        """Take damage and update sprite"""
        self.hits = min(self.hits + damage, self.max_hits)
        
        # Update sprite based on hits (0-9)
        sprite_index = min(self.hits, 9)
        self.image = self.sprite_images[sprite_index]
        
        # Update health for display
        self.health = max(0, self.max_health - self.hits)
        
        # Apply knockback
        self.knockback_duration = 5
        self.knockback_distance = 32
        self.knockback_direction = -attacker_direction
        
        # Apply immediate knockback movement
        self._move_with_collision(32 * self.knockback_direction, collision_checker, world_width_px)
    
    def _move_with_collision(self, dx, collision_checker, world_width_px):
        """Move boss with collision detection"""
        if dx == 0:
            return True
        
        old_x = self.x
        
        rect = pygame.Rect(
            int(self.x + self.hitbox_inset), 
            int(self.y + self.hitbox_inset), 
            self.boss_w - 2 * self.hitbox_inset, 
            self.boss_h - 2 * self.hitbox_inset
        )
        rect.x += int(dx)
        
        # Check collision with solid tiles
        for tile_rect in collision_checker(rect):
            if dx > 0:
                rect.right = min(rect.right, tile_rect.left)
            else:
                rect.left = max(rect.left, tile_rect.right)
        
        # Update position
        new_x = rect.x - self.hitbox_inset
        self.x = max(0, min(new_x, world_width_px - self.boss_w))
        self.x = int(self.x)
        
        return abs(self.x - old_x) > 0.5
    
    def _move_vertical(self, dy, collision_checker, world_height_px):
        """Move boss vertically with collision detection"""
        if dy == 0:
            return
        
        rect = pygame.Rect(
            int(self.x + self.hitbox_inset), 
            int(self.y + self.hitbox_inset), 
            self.boss_w - 2 * self.hitbox_inset, 
            self.boss_h - 2 * self.hitbox_inset
        )
        rect.y += int(dy)
        
        # Check collision with solid tiles
        for tile_rect in collision_checker(rect):
            if dy > 0:
                rect.bottom = min(rect.bottom, tile_rect.top)
            else:
                rect.top = max(rect.top, tile_rect.bottom)
        
        # Update position
        new_y = rect.y - self.hitbox_inset
        self.y = max(0, min(new_y, world_height_px - self.boss_h))
        self.y = int(self.y)


class GameScreen:
    def __init__(self, screen, window_size):
        if load_pygame is None:
            raise RuntimeError('pytmx is required. Install with: pip install pytmx')

        self.screen = screen
        self.window_width, self.window_height = window_size

        # background (parallax)
        self.background = safe_load_image(pygame, 'Images', 'Background', 'game_background.jpg')
        self.bg_w, self.bg_h = self.background.get_size()
        # Parallax speed factors (0 < factor < 1). Lower = slower background.
        self.parallax_x = 0.3
        self.parallax_y = 0.2

        tmx_path = get_mainlevel_tmx_path()
        self.tmx_data = load_pygame(tmx_path)

        self.tile_width = self.tmx_data.tilewidth
        self.tile_height = self.tmx_data.tileheight
        # enforce expected 32x32 tiles for exact collision math
        try:
            if self.tile_width != 32 or self.tile_height != 32:
                pass
        except Exception:
            pass
        self.map_width_tiles = self.tmx_data.width
        self.map_height_tiles = self.tmx_data.height

        self.world_width_px = self.map_width_tiles * self.tile_width
        self.world_height_px = self.map_height_tiles * self.tile_height

        # target layer
        self.layer = self.tmx_data.get_layer_by_name('Tile Layer 1')
        # cache layer index for fast tile checks
        self.layer_index = None
        for idx, lyr in enumerate(self.tmx_data.layers):
            if getattr(lyr, 'name', None) == 'Tile Layer 1':
                self.layer_index = idx
                break

        # camera for horizontal and vertical scrolling
        self.camera_x = 0
        self.camera_y = 0
        
        # Camera control state
        self.keyboard_active = True  # Track if keyboard is being used (default: True to follow player on start)
        self.mouse_dragging = False  # Track if mouse is dragging camera
        self.last_mouse_pos = None  # Last mouse position for dragging
        self.keyboard_inactive_timer = 0  # Timer to delay keyboard deactivation

        # player sprite (bottom-left on screen)
        self.player_run_right = safe_load_image(pygame, 'Images', 'Main_Run_right.png')
        self.player_run_left = safe_load_image(pygame, 'Images', 'Main_Run_left.png')
        self.player_idle_left = safe_load_image(pygame, 'Images', 'Main_Idle_left.png')
        self.player_idle_right = safe_load_image(pygame, 'Images', 'Main_Idle_right.png')
        self.player_jump_left = safe_load_image(pygame, 'Images', 'Main_Jump_left.png')
        self.player_jump_right = safe_load_image(pygame, 'Images', 'Main_Jump_right.png')
        self.player_fall_left = safe_load_image(pygame, 'Images', 'Main_falling_left.png')
        self.player_fall_right = safe_load_image(pygame, 'Images', 'Main_falling_right.png')
        
        # Sword sprites
        self.player_sword_right = safe_load_image(pygame, 'Images', 'main_idle_sword_right.png')
        self.player_sword_left = safe_load_image(pygame, 'Images', 'main_idle_sword_left.png')
        self.player_sword_run_right = safe_load_image(pygame, 'Images', 'main_run_sword_right.png')
        self.player_sword_run_left = safe_load_image(pygame, 'Images', 'main_run_sword_left.png')
        self.player_sword_jump_left = safe_load_image(pygame, 'Images', 'main_jump_sword_left.png')
        self.player_sword_jump_right = safe_load_image(pygame, 'Images', 'main_jump_sword_right.png')
        self.player_sword_attack_left = safe_load_image(pygame, 'Images', 'main_attack_sword_left.png')
        self.player_sword_attack_right = safe_load_image(pygame, 'Images', 'main_attack_sword_right.png')
        self.player_sword_falling_left  = safe_load_image(pygame, 'Images', 'main_falling_sword_left.png')
        self.player_sword_falling_right = safe_load_image(pygame, 'Images', 'main_falling_sword_right.png')
        
        
        self.player_image = self.player_idle_right
        self.player_image_left = self.player_idle_left
        self.player_margin_left = 8
        # Track last horizontal direction for idle sprite
        self.last_direction = 1  # 1 = right, -1 = left
        
        # Sword state
        self.has_sword = False
        self.sword_health = 0  # Sword durability (max 10)
        self.sword_max_health = 10
        self.attack_duration = 0  # Attack animation duration
        self.attack_cooldown = 0  # Cooldown between attacks
        # physics
        self.vy = 0
        self.gravity = 2
        self.max_fall = 20
        # choose jump velocity to reach about 50px: v^2/(2g) ≈ 49 when v=14, g=2
        self.jump_velocity = -18.2

        # player world position (start near bottom-left of the map)
        p_w, p_h = self.player_idle_left.get_size()
        self.player_w = p_w
        self.player_h = p_h
        # collision hitbox inset to avoid catching tile borders
        self.hitbox_inset = 4
        # compute safe spawn near bottom-left
        self.player_x = 32
        self.player_y =  max(0, self.world_height_px - p_h - 64)
        self.spawn_x = int(self.player_x)
        self.spawn_y = int(self.player_y)
        self.player_speed = 4

        # score and UI font
        self.score = 0
        self.health = 100  # Initial health
        self.max_health = 100
        self.damage_cooldown = 0  # Cooldown to prevent continuous damage
        self.damage_cooldown_time = 60  # 1 second at 60 FPS
        
        # Key collection tracking
        self.keys_collected = 0
        self.keys_required = 3  # Need 3 keys to win
        try:
            self.ui_font = pygame.font.SysFont('arial', 24)
            self.hud_font = pygame.font.SysFont('arial', 26, bold=True)
            self.game_over_font = pygame.font.SysFont('arial', 48)
        except Exception:
            self.ui_font = pygame.font.Font(None, 24)
            self.hud_font = pygame.font.Font(None, 28)
            self.game_over_font = pygame.font.Font(None, 48)

        # sounds
        try:
            self.coin_sound = pygame.mixer.Sound(resource_path('Sounds', 'GoldPickup.mp3'))
        except Exception:
            self.coin_sound = None
        
        try:
            self.damage_sound = pygame.mixer.Sound(resource_path('Sounds', 'Hit.mp3'))
        except Exception:
            # Try alternative sound file names
            try:
                self.damage_sound = pygame.mixer.Sound(resource_path('Sounds', 'Debuff.mp3'))
            except Exception:
                try:
                    self.damage_sound = pygame.mixer.Sound(resource_path('Sounds', 'Hurt.mp3'))
                except Exception:
                    self.damage_sound = None
        
        try:
            self.star_sound = pygame.mixer.Sound(resource_path('Sounds', 'GoldPickup.mp3'))
        except Exception:
            try:
                self.star_sound = pygame.mixer.Sound(resource_path('Sounds', 'GoldPickup.mp3'))
            except Exception:
                self.star_sound = None
        
        try:
            self.lava_sound = pygame.mixer.Sound(resource_path('Sounds', 'Lava_Sound.mp3'))
        except Exception:
            try:
                self.lava_sound = pygame.mixer.Sound(resource_path('Sounds', 'Debuff.mp3'))
            except Exception:
                self.lava_sound = None
        
        try:
            self.buff_sound = pygame.mixer.Sound(resource_path('Sounds', 'Buff.mp3'))
        except Exception:
            self.buff_sound = None

        # Apply volume settings to sounds
        settings = get_settings()
        sound_volume = settings.sound_volume * settings.volume
        music_volume = settings.music_volume * settings.volume
        for sound in [self.coin_sound, self.damage_sound, self.star_sound, self.lava_sound, self.buff_sound]:
            if sound is not None:
                sound.set_volume(sound_volume)
        
        # Load and play background music
        try:
            pygame.mixer.music.load(resource_path('Sounds', 'Background_Sound.mp3'))
            pygame.mixer.music.set_volume(music_volume)
            pygame.mixer.music.play(-1)  # -1 means loop forever
        except Exception as e:
            print(f"WARNING: Could not load background music: {e}")

        # item tiles: compute firstgid for TileSet (items)
        self.items_firstgid = self._find_tileset_firstgid(('TileSet', 'TilesSet', 'Items'))
        self.item_gid_score = {}
        if self.items_firstgid is not None:
            # handle coin (7, 11) via sprite system; keep only id 1 here
            self.item_gid_score[self.items_firstgid + 1] = 500

        # spawn coin sprites from tiles with class="coin"
        self.coin_group = pygame.sprite.Group()
        # Track coin GIDs to exclude from collision
        self.coin_gids = set()
        # Spawn coins based on class="coin" property only
        coins_spawned = self._spawn_coins_from_layer()
        print(f"DEBUG: Spawned {coins_spawned} coin sprites (based on class='coin')")
        print(f"DEBUG: Coin GIDs tracked: {sorted(self.coin_gids)}")
        if coins_spawned == 0:
            print("WARNING: No coins found with class='coin'. Check tile properties in TMX file.")
        
        # List all items marked as coin
        self._list_coin_items()
        
        # Spawn sword sprites from objects with class/type="sword"
        self.sword_group = pygame.sprite.Group()
        # Track sword GIDs to exclude from collision (similar to coin_gids)
        self.sword_gids = set()
        swords_spawned = self._spawn_swords_from_layer()
        print(f"DEBUG: Spawned {swords_spawned} sword objects")
        print(f"DEBUG: Sword GIDs tracked: {sorted(self.sword_gids)}")
        
        # Spawn box sprites from tiles with class/type="box"
        self.box_group = pygame.sprite.Group()
        # Track box GIDs to exclude from collision
        self.box_gids = set()
        boxes_spawned = self._spawn_boxes_from_layer()
        print(f"DEBUG: Spawned {boxes_spawned} box objects")
        print(f"DEBUG: Box GIDs tracked: {sorted(self.box_gids)}")

        # Water pit puzzle: push a box into water to open crossing
        self.water_pits = []
        self._load_water_pits_from_objects()
        self._move_box_near_water_pit()
        
        # Spawn star sprites from tiles with class/type="star"
        self.star_group = pygame.sprite.Group()
        # Track star GIDs to exclude from collision
        self.star_gids = set()
        stars_spawned = self._spawn_stars_from_layer()
        print(f"DEBUG: Spawned {stars_spawned} star objects")
        print(f"DEBUG: Star GIDs tracked: {sorted(self.star_gids)}")
        
        # Spawn key sprites from tiles with class/type="key"
        self.key_group = pygame.sprite.Group()
        # Track key GIDs to exclude from collision
        self.key_gids = set()
        keys_spawned = self._spawn_keys_from_layer()
        print(f"DEBUG: Spawned {keys_spawned} key objects")
        print(f"DEBUG: Key GIDs tracked: {sorted(self.key_gids)}")
        
        # Track lava tiles for damage detection
        self.lava_gids = set()
        self._init_lava_tiles()
        print(f"DEBUG: Lava GIDs tracked: {sorted(self.lava_gids)}")
        
        # Lava damage tracking
        self.in_lava = False  # Track if player is currently in lava
        self.lava_damage_cooldown = 0  # Cooldown to prevent instant death
        self.lava_damage_interval = 30  # Damage every 30 frames (0.5 seconds)
        
        # Load skeleton images
        self.skel_image_right = safe_load_image(pygame, 'Images', 'Monsters', 'skel_idle', 'skel_idle_0.png')
        self.skel_image_left = safe_load_image(pygame, 'Images', 'Monsters', 'skel_idle', 'skel_idle_0_left.png')
        
        # Spawn skeleton enemies from Enemies layer
        self.skeleton_group = pygame.sprite.Group()
        skeletons_spawned = self._spawn_skeletons_from_layer()
        print(f"DEBUG: Spawned {skeletons_spawned} skeleton enemies")
        
        # Load boss sprite images (Lightning_Ball_0.png to Lightning_Ball_9.png)
        self.boss_sprite_images = []
        for i in range(10):
            try:
                img = safe_load_image(pygame, 'Images', 'Monsters', 'Boss', f'Lightning_Ball_{i}.png')
                self.boss_sprite_images.append(img)
            except Exception:
                print(f"WARNING: Could not load Lightning_Ball_{i}.png")
                # Use a placeholder if image not found
                placeholder = pygame.Surface((32, 32))
                placeholder.fill((255, 0, 0))
                self.boss_sprite_images.append(placeholder)
        
        # Load bullet image
        try:
            self.bullet_image = safe_load_image(pygame, 'Images', 'bullet.png')
        except Exception:
            # Create placeholder bullet
            self.bullet_image = pygame.Surface((16, 16))
            self.bullet_image.fill((255, 255, 0))
            print("WARNING: Could not load bullet.png, using placeholder")
        
        # Spawn boss enemies from Enemies layer
        self.boss_group = pygame.sprite.Group()
        bosses_spawned = self._spawn_bosses_from_layer()
        print(f"DEBUG: Spawned {bosses_spawned} boss enemies")
        
        # Bullet group for boss projectiles
        self.bullet_group = pygame.sprite.Group()
        
        # Damage text effects
        self.damage_text_group = pygame.sprite.Group()
        self.heal_effect_group = pygame.sprite.Group()  # Group for heal effects (3 '+' signs)
        self.flash_alpha = 0  # Flash effect alpha (0 = no flash, 255 = full flash)
        self.flash_duration = 0  # Flash duration counter
        
        # Initialize camera to follow player at start (after all player properties are set)
        self._update_camera_follow()

    def run(self):
        clock = pygame.time.Clock()
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_UP:
                    if self._is_grounded():
                        self.vy = self.jump_velocity
                    self.keyboard_active = True  # Keyboard is being used
                if event.type == pygame.KEYDOWN and event.key == pygame.K_f:
                    # Attack with sword
                    if self.has_sword and self.sword_health > 0 and self.attack_cooldown <= 0:
                        self.attack_duration = 20  # Attack animation lasts 20 frames
                        self.attack_cooldown = 30  # Cooldown of 30 frames
                        self._attack_enemies()
                    self.keyboard_active = True  # Keyboard is being used
                # Mouse events for camera panning
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left mouse button
                        self.mouse_dragging = True
                        self.last_mouse_pos = event.pos
                        self.keyboard_active = False  # Disable keyboard follow when mouse dragging starts
                if event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:  # Left mouse button
                        self.mouse_dragging = False
                        self.last_mouse_pos = None
                if event.type == pygame.MOUSEMOTION:
                    if self.mouse_dragging and self.last_mouse_pos is not None:
                        # Calculate mouse movement delta
                        dx = event.pos[0] - self.last_mouse_pos[0]
                        dy = event.pos[1] - self.last_mouse_pos[1]
                        
                        # Pan camera in opposite direction of mouse movement
                        self.camera_x -= dx
                        self.camera_y -= dy
                        
                        # Clamp camera to world bounds
                        max_cx = max(0, self.world_width_px - self.window_width)
                        max_cy = max(0, self.world_height_px - self.window_height)
                        self.camera_x = max(0, min(self.camera_x, max_cx))
                        self.camera_y = max(0, min(self.camera_y, max_cy))
                        
                        self.last_mouse_pos = event.pos
            
            keys = pygame.key.get_pressed()
            
            # Check if any movement keys are pressed
            any_key_pressed = keys[pygame.K_LEFT] or keys[pygame.K_RIGHT] or keys[pygame.K_UP] or keys[pygame.K_f]
            if any_key_pressed:
                self.keyboard_active = True
                self.keyboard_inactive_timer = 0  # Reset timer when key is pressed
            elif not self.mouse_dragging:
                # If no keys pressed and not dragging, start timer to deactivate keyboard
                self.keyboard_inactive_timer += 1
                # After 30 frames (0.5 seconds) of no keyboard input, allow mouse panning
                if self.keyboard_inactive_timer >= 30:
                    self.keyboard_active = False
            dx = 0
            dy = 0
            if keys[pygame.K_LEFT]:
                dx -= self.player_speed
                self.last_direction = -1  # Track left direction
            if keys[pygame.K_RIGHT]:
                dx += self.player_speed
                self.last_direction = 1  # Track right direction
            # vertical movement controlled by physics only (gravity/jump)

            if dx:
                self._move_player(dx, 0)

            # gravity
            self.vy = min(self.vy + self.gravity, self.max_fall)
            self._move_player(0, self.vy)
            
            # Check if player stomps on skeleton heads (only when falling down)
            if self.vy > 0:  # Player is falling
                self._check_stomp_skeletons()

            # update sprite based on state: falling, jumping, moving, or grounded
            is_grounded = self._is_grounded()
            
            # Update player sprite based on sword state and movement
            r = (self.last_direction >= 0)
            if self.has_sword and self.sword_health > 0:
                # Sword equipped - use sword sprites
                if self.attack_duration > 0:
                    # Attack animation
                    if self.last_direction == -1:
                        self.player_image = self.player_sword_attack_right
                    else:
                        self.player_image = self.player_sword_attack_left
                elif not is_grounded and self.vy > 0:
                    # Falling with sword
                    if self.last_direction == -1:
                        self.player_image = self.player_sword_falling_right
                    else:
                        self.player_image = self.player_sword_falling_left
                elif not is_grounded and self.vy < 0:
                    # Jumping with sword
                    if self.last_direction == -1:
                        self.player_image = self.player_sword_jump_right
                    else:
                        self.player_image = self.player_sword_jump_left
                elif dx < 0:
                    # Moving left with sword
                    self.player_image = self.player_sword_run_right
                elif dx > 0:
                    # Moving right with sword
                    self.player_image = self.player_sword_run_left
                else:
                    # Idle with sword - use direction-based sprite
                    if self.last_direction == -1:
                        self.player_image = self.player_sword_right
                    else:
                        self.player_image = self.player_sword_left
            else:
                # No sword - use normal sprites
                # Priority 1: If falling (vy > 0 and not grounded), use fall sprite
                if not is_grounded and self.vy > 0:
                    if self.last_direction == -1:
                        self.player_image = self.player_fall_right
                    else:
                        self.player_image = self.player_fall_left
                # Priority 2: If jumping up (vy < 0), use jump sprite
                elif not is_grounded and self.vy < 0:
                    if self.last_direction == -1:
                        self.player_image = self.player_jump_right
                    else:
                        self.player_image = self.player_jump_left
                # Priority 3: If moving left, use left sprite
                elif dx < 0:
                    self.player_image = self.player_run_left
                # Priority 4: If moving right, use right sprite
                elif dx > 0:
                    self.player_image = self.player_run_right
                # Priority 5: If grounded and not moving (completely idle), use idle sprite
                elif is_grounded and self.vy >= 0 and dx == 0:
                    if self.last_direction == -1:
                        self.player_image = self.player_idle_right
                    else:
                        self.player_image = self.player_idle_left
                # Priority 6: If grounded and not moving, use idle based on last direction (fallback)
                elif is_grounded and self.vy >= 0:
                    if self.last_direction == -1:
                        self.player_image = self.player_idle_left
                    else:
                        self.player_image = self.player_idle_right
            # collect items when overlapping
            self._collect_items()
            
            # collect swords when overlapping
            self._collect_swords()
            
            # collect stars when overlapping
            self._collect_stars()
            
            # collect keys when overlapping
            self._collect_keys()
            
            # update skeleton enemies
            for skeleton in self.skeleton_group.sprites():
                # Pass collision checker function, world width and height to skeleton
                skeleton.update(self.player_x, self.player_y, self._iter_colliding_tile_rects, self.world_width_px, self.world_height_px)
            
            # update boss enemies
            for boss in self.boss_group.sprites():
                # Pass collision checker, world dimensions, and bullet group to boss
                boss.update(self.player_x, self.player_y, self._iter_colliding_tile_rects, self.world_width_px, self.world_height_px, self.bullet_group)
            
            # update bullets
            for bullet in self.bullet_group.sprites():
                bullet.update(self.world_width_px, self.world_height_px)
            
            # Check collision with skeletons and damage player
            if self.damage_cooldown <= 0 and self.health > 0:
                self._check_skeleton_collision()
            
            # Check collision with bullets and damage player
            if self.damage_cooldown <= 0 and self.health > 0:
                self._check_bullet_collision()
            
            # Update damage cooldown
            if self.damage_cooldown > 0:
                self.damage_cooldown -= 1
            
            # Check collision with lava and damage player continuously
            if self.health > 0:
                self._check_lava_collision()
            
            # Update lava damage cooldown
            if self.lava_damage_cooldown > 0:
                self.lava_damage_cooldown -= 1
            
            # Update damage text effects
            self.damage_text_group.update()
            
            # Update heal effects
            self.heal_effect_group.update()
            
            # Update flash effect
            if self.flash_duration > 0:
                self.flash_duration -= 1
                # Flash effect: fade out over time
                self.flash_alpha = int(255 * (self.flash_duration / 10))  # Flash for ~10 frames
            else:
                self.flash_alpha = 0
            
            # Update attack animation
            if self.attack_duration > 0:
                self.attack_duration -= 1
            
            # Update attack cooldown
            if self.attack_cooldown > 0:
                self.attack_cooldown -= 1
            
            # Sword damage only decreases when hitting enemies (handled in _attack_enemies)

            # update camera: follow player if keyboard is active, otherwise keep current position (allow mouse panning)
            if self.keyboard_active:
                self._update_camera_follow()
            # If keyboard not active and not dragging, camera stays where it is (user can pan with mouse)

            # no jump offset animation; physics handles vertical motion

            # Check if game won (collected 3 keys)
            if self.keys_collected >= self.keys_required:
                self._draw_win_screen()
            # Check if game over
            elif self.health <= 0:
                self._draw_game_over()
            else:
                self._draw()
            pygame.display.flip()
            clock.tick(60)

        return True

    def _iter_colliding_enemy_rects(self, rect):
        """Iterate through enemy rects (skeletons and bosses) that collide with the given rect"""
        # Check skeletons
        for skeleton in self.skeleton_group.sprites():
            if skeleton.health > 0:  # Only check alive skeletons
                skeleton_rect = pygame.Rect(
                    int(skeleton.x + skeleton.hitbox_inset),
                    int(skeleton.y + skeleton.hitbox_inset),
                    skeleton.skel_w - 2 * skeleton.hitbox_inset,
                    skeleton.skel_h - 2 * skeleton.hitbox_inset
                )
                if rect.colliderect(skeleton_rect):
                    yield skeleton_rect
        
        # Check bosses
        for boss in self.boss_group.sprites():
            if boss.hits < boss.max_hits:  # Only check alive bosses
                boss_rect = pygame.Rect(
                    int(boss.x + boss.hitbox_inset),
                    int(boss.y + boss.hitbox_inset),
                    boss.boss_w - 2 * boss.hitbox_inset,
                    boss.boss_h - 2 * boss.hitbox_inset
                )
                if rect.colliderect(boss_rect):
                    yield boss_rect

    def _move_player(self, dx, dy):
        # Use integer math and resolve per-axis against 32x32 grid
        if dx != 0:
            rect = pygame.Rect(int(self.player_x + self.hitbox_inset), int(self.player_y + self.hitbox_inset), self.player_w - 2 * self.hitbox_inset, self.player_h - 2 * self.hitbox_inset)
            rect.x += int(dx)

            # Boxes are NOT pushable: they block movement, can only be broken by sword
            for box in list(self.box_group.sprites()):
                if rect.colliderect(box.rect):
                    if dx > 0:
                        rect.right = min(rect.right, box.rect.left)
                    else:
                        rect.left = max(rect.left, box.rect.right)

            # Block crossing at water pit until a box fills it
            for pit in self.water_pits:
                if pit['filled']:
                    continue
                if rect.colliderect(pit['rect']):
                    if dx > 0:
                        rect.right = min(rect.right, pit['rect'].left)
                    else:
                        rect.left = max(rect.left, pit['rect'].right)
            
            # Check collision with solid tiles
            for tile_rect in self._iter_colliding_tile_rects(rect):
                if dx > 0:
                    # moving right: stop flush at tile's left edge
                    rect.right = min(rect.right, tile_rect.left)
                else:
                    # moving left: stop flush at tile's right edge
                    rect.left = max(rect.left, tile_rect.right)
            
            # Check collision with enemies (skeletons and bosses) - treat as solid
            for enemy_rect in self._iter_colliding_enemy_rects(rect):
                if dx > 0:
                    # moving right: stop flush at enemy's left edge
                    rect.right = min(rect.right, enemy_rect.left)
                else:
                    # moving left: stop flush at enemy's right edge
                    rect.left = max(rect.left, enemy_rect.right)
            
            new_x = rect.x - self.hitbox_inset
            self.player_x = max(0, min(new_x, self.world_width_px - self.player_w))

        if dy != 0:
            rect = pygame.Rect(int(self.player_x + self.hitbox_inset), int(self.player_y + self.hitbox_inset), self.player_w - 2 * self.hitbox_inset, self.player_h - 2 * self.hitbox_inset)
            rect.y += int(dy)
            
            # Check collision with solid tiles
            for tile_rect in self._iter_colliding_tile_rects(rect):
                if dy > 0:
                    # moving down: stop at tile's top
                    rect.bottom = min(rect.bottom, tile_rect.top)
                else:
                    # moving up: stop at tile's bottom
                    rect.top = max(rect.top, tile_rect.bottom)
            
            # Check collision with enemies (skeletons and bosses) - treat as solid
            for enemy_rect in self._iter_colliding_enemy_rects(rect):
                if dy > 0:
                    # moving down: stop at enemy's top
                    rect.bottom = min(rect.bottom, enemy_rect.top)
                else:
                    # moving up: stop at enemy's bottom
                    rect.top = max(rect.top, enemy_rect.bottom)
            
            new_y = rect.y - self.hitbox_inset
            self.player_y = max(0, min(new_y, self.world_height_px - self.player_h))

        # snap to integer pixel to avoid subpixel drift
        self.player_x = int(self.player_x)
        self.player_y = int(self.player_y)

    def _update_camera_follow(self):
        # center camera on player when within bounds, else clamp camera
        target_cx = int(self.player_x + self.player_w // 2 - self.window_width // 2)
        target_cy = int(self.player_y + self.player_h // 2 - self.window_height // 2)
        max_cx = max(0, self.world_width_px - self.window_width)
        max_cy = max(0, self.world_height_px - self.window_height)
        self.camera_x = max(0, min(target_cx, max_cx))
        self.camera_y = max(0, min(target_cy, max_cy))

    def _load_water_pits_from_objects(self):
        self.water_pits = []
        try:
            for layer in self.tmx_data.layers:
                layer_name = (getattr(layer, 'name', '') or '').lower()
                if layer_name not in ('treasure', 'objects', 'object layer 1'):
                    continue
                objects = getattr(layer, 'objects', None)
                if objects is None:
                    try:
                        objects = list(layer)
                    except Exception:
                        objects = []
                for obj in objects:
                    obj_type = (getattr(obj, 'type', '') or '').lower().strip()
                    obj_name = (getattr(obj, 'name', '') or '').lower().strip()
                    obj_class = (getattr(obj, 'class', '') or '').lower().strip()
                    if obj_type in ('water', 'pit') or obj_name in ('water', 'pit') or obj_class in ('water', 'pit'):
                        x = int(getattr(obj, 'x', 0))
                        y = int(getattr(obj, 'y', 0))
                        w = max(32, int(getattr(obj, 'width', 32)))
                        h = max(32, int(getattr(obj, 'height', 32)))
                        self.water_pits.append({
                            'rect': pygame.Rect(x, y, w, h),
                            'filled': False,
                            'bridge_rect': pygame.Rect(x + (w - 32) // 2, y, 32, 32),
                        })
        except Exception as e:
            print(f"DEBUG: Could not load water pits: {e}")

        print(f"DEBUG: Loaded {len(self.water_pits)} water pits")

    def _move_box_near_water_pit(self):
        if not self.water_pits or len(self.box_group.sprites()) == 0:
            return

        pit = self.water_pits[0]['rect']
        box = min(self.box_group.sprites(), key=lambda b: abs((b.rect.centerx - pit.centerx)))
        candidate_x = [pit.left - 48, pit.left - 80, pit.left - 112]
        target_y = pit.y + pit.height - box.rect.height

        for x in candidate_x:
            test_rect = pygame.Rect(int(x), int(target_y), box.rect.width, box.rect.height)
            if test_rect.left < 0 or test_rect.right > self.world_width_px:
                continue
            blocked = any(test_rect.colliderect(r) for r in self._iter_solid_tile_rects(test_rect))
            if blocked:
                continue
            overlap = False
            for other in self.box_group.sprites():
                if other is box:
                    continue
                if test_rect.colliderect(other.rect):
                    overlap = True
                    break
            if overlap:
                continue
            box.rect.topleft = (test_rect.x, test_rect.y)
            print("DEBUG: Moved one box near water pit")
            return

    def _try_push_box(self, box, dx):
        if dx == 0:
            return False

        step = 1 if dx > 0 else -1
        move_px = max(1, abs(int(dx)))
        test_rect = box.rect.copy()
        test_rect.x += step * move_px

        if test_rect.left < 0 or test_rect.right > self.world_width_px:
            return False

        for solid_rect in self._iter_solid_tile_rects(test_rect):
            if test_rect.colliderect(solid_rect):
                return False

        for other_box in self.box_group.sprites():
            if other_box is box:
                continue
            if test_rect.colliderect(other_box.rect):
                return False

        box.rect.x = test_rect.x

        # If box reaches water pit, it drops in and creates a bridge
        for pit in self.water_pits:
            if pit['filled']:
                continue
            if box.rect.colliderect(pit['rect']):
                pit['filled'] = True
                box.kill()
                print("DEBUG: Box filled water pit")
                break

        return True

    def _iter_solid_tile_rects(self, rect):
        start_col = max(0, rect.left // 32)
        end_col = min(self.map_width_tiles - 1, (rect.right - 1) // 32)
        start_row = max(0, rect.top // 32)
        end_row = min(self.map_height_tiles - 1, (rect.bottom - 1) // 32)

        for col in range(start_col, end_col + 1):
            for row in range(start_row, end_row + 1):
                if self._is_solid_tile(col, row):
                    yield pygame.Rect(col * 32, row * 32, 32, 32)

    def _draw_water_pits(self):
        for pit in self.water_pits:
            p = pit['rect']
            draw_rect = pygame.Rect(p.x - self.camera_x, p.y - self.camera_y, p.width, p.height)
            color = (45, 130, 220) if not pit['filled'] else (120, 95, 55)
            pygame.draw.rect(self.screen, color, draw_rect)
            pygame.draw.rect(self.screen, (220, 240, 255), draw_rect, 2)

            if pit['filled']:
                bridge = pit['bridge_rect']
                bridge_draw = pygame.Rect(bridge.x - self.camera_x, bridge.y - self.camera_y, bridge.width, bridge.height)
                pygame.draw.rect(self.screen, (140, 110, 70), bridge_draw)
                pygame.draw.rect(self.screen, (220, 200, 160), bridge_draw, 2)

    def _draw(self):
        # draw parallax background (tiled to cover screen)
        self._draw_parallax_background()

        # Draw only the requested tile layer, offset by camera
        # pytmx exposes tiles as ready-made pygame surfaces
        draw_left = self.camera_x
        for x, y, image in self.layer.tiles():
            if image is None:
                continue
            px = x * self.tile_width - self.camera_x
            py = y * self.tile_height - self.camera_y

            # Cull tiles outside the viewport horizontally for perf
            if px + self.tile_width < 0 or px > self.window_width:
                continue

            if py + self.tile_height < 0 or py > self.window_height:
                continue

            self.screen.blit(image, (px, py))

        # draw water pits/bridge markers
        self._draw_water_pits()

        # draw player fixed to screen bottom-left
        p_img = self.player_image
        # Draw player at world position relative to camera, minus jump offset visually
        screen_x = int(self.player_x - self.camera_x)
        screen_y = int(self.player_y - self.camera_y)
        
        # Apply flash effect if taking damage
        if self.flash_alpha > 0:
            # Draw base sprite first
            self.screen.blit(p_img, (screen_x, screen_y))
            # Draw red silhouette overlay using alpha mask (no rectangular box)
            try:
                sprite_mask = pygame.mask.from_surface(p_img)
                flash_overlay = sprite_mask.to_surface(
                    setcolor=(255, 0, 0, self.flash_alpha),
                    unsetcolor=(0, 0, 0, 0)
                )
                self.screen.blit(flash_overlay, (screen_x, screen_y))
            except Exception:
                # Safe fallback: draw original sprite only
                pass
        else:
            self.screen.blit(p_img, (screen_x, screen_y))

        # draw score at top-right
        score_rect = self._blit_hud_text(
            f"Score: {self.score}",
            (self.window_width - 12, 8),
            (255, 245, 170),
            anchor='topright'
        )

        # draw health below score
        self._blit_hud_text(
            f"Health: {self.health}",
            (self.window_width - 12, 8 + score_rect.height + 6),
            (255, 110, 110),
            anchor='topright'
        )
        
        # draw sword damage at bottom-left (always visible)
        current_sword_damage = self.sword_health if (self.has_sword and self.sword_health > 0) else 0
        sword_color = (255, 230, 90) if current_sword_damage > 0 else (190, 190, 190)
        sword_rect = self._blit_hud_text(
            f"Sword Damage: {current_sword_damage}",
            (12, self.window_height - 12),
            sword_color,
            anchor='bottomleft'
        )
        sword_text_height = sword_rect.height
        
        # draw keys collected at bottom-left (below sword damage if exists, otherwise at bottom)
        key_y_offset = sword_text_height + 4  # Always below sword damage
        self._blit_hud_text(
            f"Keys: {self.keys_collected}/{self.keys_required}",
            (12, self.window_height - 12 - key_y_offset),
            (140, 255, 160),
            anchor='bottomleft'
        )

        if any(not pit['filled'] for pit in self.water_pits):
            self._blit_hud_text(
                "Day hop xuong nuoc de mo duong",
                (12, self.window_height - 12 - key_y_offset - sword_text_height - 4),
                (100, 220, 255),
                anchor='bottomleft'
            )

        # draw coins with camera offset
        for coin in self.coin_group.sprites():
            self.screen.blit(coin.image, (coin.rect.x - self.camera_x, coin.rect.y - self.camera_y))
        
        # draw swords with camera offset
        for sword in self.sword_group.sprites():
            self.screen.blit(sword.image, (sword.rect.x - self.camera_x, sword.rect.y - self.camera_y))
        
        # draw boxes with camera offset
        for box in self.box_group.sprites():
            self.screen.blit(box.image, (box.rect.x - self.camera_x, box.rect.y - self.camera_y))
        
        # draw stars with camera offset
        for star in self.star_group.sprites():
            self.screen.blit(star.image, (star.rect.x - self.camera_x, star.rect.y - self.camera_y))
        
        # draw keys with camera offset
        for key in self.key_group.sprites():
            self.screen.blit(key.image, (key.rect.x - self.camera_x, key.rect.y - self.camera_y))
        
        # draw skeletons with camera offset and health bar
        for skeleton in self.skeleton_group.sprites():
            self.screen.blit(skeleton.image, (skeleton.rect.x - self.camera_x, skeleton.rect.y - self.camera_y))
            
            # Draw health bar above skeleton
            health_bar_width = skeleton.skel_w
            health_bar_height = 4
            health_bar_x = skeleton.rect.x - self.camera_x
            health_bar_y = skeleton.rect.y - self.camera_y - 8
            
            # Background (red)
            health_bg_rect = pygame.Rect(health_bar_x, health_bar_y, health_bar_width, health_bar_height)
            pygame.draw.rect(self.screen, (128, 0, 0), health_bg_rect)
            
            # Health (green)
            health_percentage = skeleton.health / skeleton.max_health
            health_fill_width = int(health_bar_width * health_percentage)
            if health_fill_width > 0:
                health_fill_rect = pygame.Rect(health_bar_x, health_bar_y, health_fill_width, health_bar_height)
                pygame.draw.rect(self.screen, (0, 255, 0), health_fill_rect)
        
        # draw bosses with camera offset and health bar
        for boss in self.boss_group.sprites():
            self.screen.blit(boss.image, (boss.rect.x - self.camera_x, boss.rect.y - self.camera_y))
            
            # Draw health bar above boss
            health_bar_width = boss.boss_w
            health_bar_height = 6
            health_bar_x = boss.rect.x - self.camera_x
            health_bar_y = boss.rect.y - self.camera_y - 10
            
            # Background (red)
            health_bg_rect = pygame.Rect(health_bar_x, health_bar_y, health_bar_width, health_bar_height)
            pygame.draw.rect(self.screen, (128, 0, 0), health_bg_rect)
            
            # Health (green)
            health_percentage = boss.health / boss.max_health
            health_fill_width = int(health_bar_width * health_percentage)
            if health_fill_width > 0:
                health_fill_rect = pygame.Rect(health_bar_x, health_bar_y, health_fill_width, health_bar_height)
                pygame.draw.rect(self.screen, (0, 255, 0), health_fill_rect)
        
        # draw bullets with camera offset
        for bullet in self.bullet_group.sprites():
            self.screen.blit(bullet.image, (bullet.rect.x - self.camera_x, bullet.rect.y - self.camera_y))
        
        # draw damage text with camera offset
        for damage_text in self.damage_text_group.sprites():
            # Convert world position to screen position
            screen_x = int(damage_text.x - self.camera_x)
            screen_y = int(damage_text.y - self.camera_y)
            damage_text.rect.center = (screen_x, screen_y)
            self.screen.blit(damage_text.image, damage_text.rect)
        
        # draw heal effects with camera offset
        for heal_effect in self.heal_effect_group.sprites():
            # Convert world position to screen position
            screen_x = int(heal_effect.x - self.camera_x)
            screen_y = int(heal_effect.y - self.camera_y)
            heal_effect.rect.center = (screen_x, screen_y)
            self.screen.blit(heal_effect.image, heal_effect.rect)

    def _blit_hud_text(self, text, pos, color, anchor='topleft'):
        """Draw HUD text with dark outline for better readability on any background."""
        text_surface = self.hud_font.render(text, True, color)
        outline_surface = self.hud_font.render(text, True, (0, 0, 0))
        text_rect = text_surface.get_rect()
        setattr(text_rect, anchor, pos)

        outline_offsets = [
            (-2, 0), (2, 0), (0, -2), (0, 2),
            (-1, -1), (1, -1), (-1, 1), (1, 1)
        ]
        for ox, oy in outline_offsets:
            self.screen.blit(outline_surface, (text_rect.x + ox, text_rect.y + oy))

        self.screen.blit(text_surface, text_rect)
        return text_rect

    def _find_safe_spawn(self):
        # 1) Try object layer marker named 'PlayerSpawn'
        try:
            for layer in self.tmx_data.layers:
                if getattr(layer, 'name', '') in ('Objects', 'objects', 'Spawns', 'spawns'):
                    for obj in getattr(layer, 'objects', []):
                        name = getattr(obj, 'name', '') or ''
                        if name.lower() in ('playerspawn', 'spawn_player', 'spawn'):
                            sx = int(getattr(obj, 'x', 0))
                            sy = int(getattr(obj, 'y', 0)) - self.player_h
                            rect = pygame.Rect(sx, sy, self.player_w, self.player_h)
                            if not any(rect.colliderect(r) for r in self._iter_colliding_tile_rects(rect)):
                                return sx, sy
        except Exception:
            pass

        # 2) Fallback: scan from left margin at bottom up until empty space that fits player
        margin_px = 8
        start_col = max(0, margin_px // self.tile_width)
        # start from bottom row upwards
        for row in range(self.map_height_tiles - 1, -1, -1):
            x_px = start_col * self.tile_width + (margin_px % self.tile_width)
            y_px = row * self.tile_height - (self.player_h - self.tile_height)
            if y_px < 0:
                continue
            rect = pygame.Rect(x_px, y_px, self.player_w, self.player_h)
            if not any(rect.colliderect(r) for r in self._iter_colliding_tile_rects(rect)):
                return x_px, min(y_px, self.world_height_px - self.player_h)

        # 3) Last resort: bottom-left inside world bounds
        return 8, max(0, self.world_height_px - self.player_h - 1)

    def _is_grounded(self):
        # Check 1px below hitbox for a solid tile
        inset = getattr(self, 'hitbox_inset', 0)
        rect = pygame.Rect(int(self.player_x + inset), int(self.player_y + inset), self.player_w - 2 * inset, self.player_h - 2 * inset)
        rect.y += 1
        return any(True for _ in self._iter_colliding_tile_rects(rect))
    
    def _check_stomp_skeletons(self):
        """Check if player stomps on skeleton heads while falling"""
        if self.vy <= 0:  # Only check when falling down
            return
        
        player_rect = pygame.Rect(
            int(self.player_x + self.hitbox_inset), 
            int(self.player_y + self.hitbox_inset), 
            self.player_w - 2 * self.hitbox_inset, 
            self.player_h - 2 * self.hitbox_inset
        )
        
        # Check bottom of player rect (where feet are)
        player_bottom = player_rect.bottom
        
        for skeleton in list(self.skeleton_group.sprites()):
            if skeleton.health <= 0:
                continue
                
            skeleton_rect = pygame.Rect(
                int(skeleton.x + skeleton.hitbox_inset),
                int(skeleton.y + skeleton.hitbox_inset),
                skeleton.skel_w - 2 * skeleton.hitbox_inset,
                skeleton.skel_h - 2 * skeleton.hitbox_inset
            )
            
            # Check if player is above skeleton and overlapping horizontally
            # Player must be falling and bottom of player is near top of skeleton
            if (player_rect.right > skeleton_rect.left and 
                player_rect.left < skeleton_rect.right and
                player_bottom >= skeleton_rect.top and 
                player_bottom <= skeleton_rect.top + 15):  # Within 15px of skeleton top
                
                # Stomp successful! Damage skeleton and bounce player
                skeleton.take_damage(2, 0, self._iter_colliding_tile_rects, self.world_width_px)  # 0 direction for stomp
                
                # Create damage text "-2" above skeleton
                damage_text_x = skeleton.x + skeleton.skel_w // 2
                damage_text_y = skeleton.y
                damage_text = DamageText(2, damage_text_x, damage_text_y, self.ui_font)
                self.damage_text_group.add(damage_text)
                
                # Position player on top of skeleton and bounce up
                self.player_y = skeleton_rect.top - self.player_h + self.hitbox_inset
                self.vy = -12  # Small bounce upward
                
                # Check if skeleton is dead
                if skeleton.health <= 0:
                    skeleton.kill()
                    self.score += 150  # Reward for killing skeleton
                
                break  # Only stomp one skeleton per frame
    
    def _check_skeleton_collision(self):
        """Check if player collides with any skeleton and take damage"""
        player_rect = pygame.Rect(
            int(self.player_x + self.hitbox_inset), 
            int(self.player_y + self.hitbox_inset), 
            self.player_w - 2 * self.hitbox_inset, 
            self.player_h - 2 * self.hitbox_inset
        )
        
        for skeleton in self.skeleton_group.sprites():
            skeleton_rect = pygame.Rect(
                int(skeleton.x + skeleton.hitbox_inset),
                int(skeleton.y + skeleton.hitbox_inset),
                skeleton.skel_w - 2 * skeleton.hitbox_inset,
                skeleton.skel_h - 2 * skeleton.hitbox_inset
            )
            
            # Only take damage if player is not stomping (not on top of skeleton)
            player_bottom = player_rect.bottom
            skeleton_top = skeleton_rect.top
            
            # Check if player is on top of skeleton (stomping)
            is_stomping = (player_rect.right > skeleton_rect.left and 
                          player_rect.left < skeleton_rect.right and
                          player_bottom >= skeleton_top and 
                          player_bottom <= skeleton_top + 10)
            
            if player_rect.colliderect(skeleton_rect) and not is_stomping:
                # Take damage
                damage_amount = 10
                self.health = max(0, self.health - damage_amount)
                self.damage_cooldown = self.damage_cooldown_time
                
                # Create damage text above player
                damage_text_x = self.player_x + self.player_w // 2
                damage_text_y = self.player_y
                damage_text = DamageText(damage_amount, damage_text_x, damage_text_y, self.ui_font)
                self.damage_text_group.add(damage_text)
                
                # Trigger flash effect
                self.flash_duration = 10  # Flash for 10 frames
                self.flash_alpha = 255
                
                # Play damage sound
                if self.damage_sound is not None:
                    try:
                        self.damage_sound.play()
                    except Exception:
                        pass
                
                break  # Only take damage once per frame
    
    def _check_bullet_collision(self):
        """Check if player collides with any bullet and take damage"""
        player_rect = pygame.Rect(
            int(self.player_x + self.hitbox_inset), 
            int(self.player_y + self.hitbox_inset), 
            self.player_w - 2 * self.hitbox_inset, 
            self.player_h - 2 * self.hitbox_inset
        )
        
        for bullet in list(self.bullet_group.sprites()):
            if player_rect.colliderect(bullet.rect):
                # Take damage
                damage_amount = 10
                self.health = max(0, self.health - damage_amount)
                self.damage_cooldown = self.damage_cooldown_time
                
                # Remove bullet
                bullet.kill()
                
                # Create damage text above player
                damage_text_x = self.player_x + self.player_w // 2
                damage_text_y = self.player_y
                damage_text = DamageText(damage_amount, damage_text_x, damage_text_y, self.ui_font)
                self.damage_text_group.add(damage_text)
                
                # Trigger flash effect
                self.flash_duration = 10  # Flash for 10 frames
                self.flash_alpha = 255
                
                # Play damage sound
                if self.damage_sound is not None:
                    try:
                        self.damage_sound.play()
                    except Exception:
                        pass
                
                break  # Only take damage once per frame
    
    def _collect_swords(self):
        """Collect sword objects when player overlaps them"""
        inset = getattr(self, 'hitbox_inset', 0)
        hit = pygame.Rect(
            int(self.player_x + inset), 
            int(self.player_y + inset), 
            self.player_w - 2 * inset, 
            self.player_h - 2 * inset
        )
        
        # Check collision with swords
        tmp_player = pygame.sprite.Sprite()
        tmp_player.rect = hit
        hits = pygame.sprite.spritecollide(tmp_player, self.sword_group, True)
        
        if hits:
            if not self.has_sword:
                # Pick up sword for the first time
                self.has_sword = True
                self.sword_health = self.sword_max_health
            else:
                # Already have sword - add 10 more damage
                self.sword_health += self.sword_max_health
    
    def _collect_stars(self):
        """Collect star objects when player overlaps them"""
        inset = getattr(self, 'hitbox_inset', 0)
        hit = pygame.Rect(
            int(self.player_x + inset), 
            int(self.player_y + inset), 
            self.player_w - 2 * inset, 
            self.player_h - 2 * inset
        )
        
        # Check collision with stars
        tmp_player = pygame.sprite.Sprite()
        tmp_player.rect = hit
        hits = pygame.sprite.spritecollide(tmp_player, self.star_group, True)
        
        if hits:
            old_health = self.health
            # Refill health to max when collecting star
            self.health = self.max_health
            
            # Play buff sound
            if self.buff_sound is not None:
                try:
                    self.buff_sound.play()
                except Exception:
                    pass
            
            # Create heal effect with 3 '+' signs appearing sequentially
            heal_effect_x = self.player_x + self.player_w // 2
            heal_effect_y = self.player_y - 10  # Start slightly above player
            heal_effect = HealEffect(heal_effect_x, heal_effect_y, self.ui_font)
            self.heal_effect_group.add(heal_effect)
    
    def _collect_keys(self):
        """Collect key objects when player overlaps them"""
        inset = getattr(self, 'hitbox_inset', 0)
        hit = pygame.Rect(
            int(self.player_x + inset), 
            int(self.player_y + inset), 
            self.player_w - 2 * inset, 
            self.player_h - 2 * inset
        )
        
        # Check collision with keys
        tmp_player = pygame.sprite.Sprite()
        tmp_player.rect = hit
        hits = pygame.sprite.spritecollide(tmp_player, self.key_group, True)
        
        if hits:
            # Collect key (max 3)
            self.keys_collected = min(self.keys_collected + len(hits), self.keys_required)
            
            # Play key pickup sound (use coin sound for now)
            if self.coin_sound is not None:
                try:
                    self.coin_sound.play()
                except Exception:
                    pass
    
    def _attack_enemies(self):
        """Attack enemies in front of player with relaxed vertical tolerance."""
        if not self.has_sword or self.sword_health <= 0:
            return
        
        attack_range = 64  # 64 pixels attack range
        vertical_attack_tolerance = 96  # Allow up to ~3 tiles vertical difference
        player_center_x = self.player_x + self.player_w // 2
        player_center_y = self.player_y + self.player_h // 2
        
        enemies_hit = 0  # Count how many enemies were hit
        boxes_broken = 0  # Count how many boxes were broken
        
        # Check each skeleton
        for skeleton in list(self.skeleton_group.sprites()):
            if skeleton.health <= 0:
                continue
            
            skeleton_center_x = skeleton.x + skeleton.skel_w // 2
            skeleton_center_y = skeleton.y + skeleton.skel_h // 2
            
            # Calculate distance
            dx = skeleton_center_x - player_center_x
            dy = abs(skeleton_center_y - player_center_y)
            distance = abs(dx)
            
            # Check if enemy is in range and same direction
            if distance <= attack_range and dy < vertical_attack_tolerance:
                # Check if enemy is in same direction as player facing
                if (self.last_direction == 1 and dx > 0) or (self.last_direction == -1 and dx < 0):
                    # Attack hits!
                    skeleton.take_damage(1, self.last_direction, self._iter_colliding_tile_rects, self.world_width_px)
                    enemies_hit += 1  # Count this enemy as hit
                    
                    # Create damage text "-1" above enemy
                    damage_text_x = skeleton_center_x
                    damage_text_y = skeleton.y
                    damage_text = DamageText(1, damage_text_x, damage_text_y, self.ui_font)
                    self.damage_text_group.add(damage_text)
                    
                    # Check if skeleton is dead
                    if skeleton.health <= 0:
                        skeleton.kill()
                        self.score += 150  # Reward for killing skeleton
        
        # Check each boss
        for boss in list(self.boss_group.sprites()):
            if boss.hits >= boss.max_hits:
                continue
            
            boss_center_x = boss.x + boss.boss_w // 2
            boss_center_y = boss.y + boss.boss_h // 2
            
            # Calculate distance
            dx = boss_center_x - player_center_x
            dy = abs(boss_center_y - player_center_y)
            distance = abs(dx)
            
            # Check if boss is in range and same direction
            if distance <= attack_range and dy < vertical_attack_tolerance:
                # Check if boss is in same direction as player facing
                if (self.last_direction == 1 and dx > 0) or (self.last_direction == -1 and dx < 0):
                    # Attack hits!
                    boss.take_damage(1, self.last_direction, self._iter_colliding_tile_rects, self.world_width_px)
                    enemies_hit += 1  # Count this boss as hit
                    
                    # Create damage text "-1" above boss
                    damage_text_x = boss_center_x
                    damage_text_y = boss.y
                    damage_text = DamageText(1, damage_text_x, damage_text_y, self.ui_font)
                    self.damage_text_group.add(damage_text)
                    
                    # Check if boss is dead (hits >= max_hits)
                    if boss.hits >= boss.max_hits:
                        boss.kill()
                        self.score += 500  # Reward for killing boss
        
        # Check each box (need sword damage >= 3 to break)
        if self.sword_health >= 3:
            for box in list(self.box_group.sprites()):
                box_center_x = box.rect.x + box.rect.width // 2
                box_center_y = box.rect.y + box.rect.height // 2
                
                # Calculate distance
                dx = box_center_x - player_center_x
                dy = abs(box_center_y - player_center_y)
                distance = abs(dx)
                
                # Check if box is in range and same direction
                if distance <= attack_range and dy < vertical_attack_tolerance:
                    # Check if box is in same direction as player facing
                    if (self.last_direction == 1 and dx > 0) or (self.last_direction == -1 and dx < 0):
                        # Attack hits box! Break it (costs 3 damage)
                        box.kill()
                        boxes_broken += 1
                        
                        # Cost: -3 sword damage
                        self.sword_health -= 3
                        
                        # Reward: +5 sword damage, +20 health (net gain: +2 damage)
                        self.sword_health += 5
                        self.health = min(self.max_health, self.health + 20)
                        
                        # Create break text above box
                        break_text_x = box_center_x
                        break_text_y = box.rect.y
                        break_text = DamageText(3, break_text_x, break_text_y, self.ui_font)  # Show -3 damage
                        self.damage_text_group.add(break_text)
                        
                        # Check if sword is depleted
                        if self.sword_health <= 0:
                            self.has_sword = False
                            self.sword_health = 0
        
        # Decrease sword damage by 1 for each enemy hit (but not for boxes - already handled above)
        if enemies_hit > 0:
            self.sword_health -= enemies_hit
            if self.sword_health <= 0:
                self.has_sword = False
                self.sword_health = 0
    
    def _spawn_swords_from_layer(self):
        """Spawn sword sprites from tiles with class/type='sword' (similar to coins)"""
        print("DEBUG: Looking for tiles with class='sword'")
        swords_spawned = 0
        
        # Scan ALL tile layers, not just Tile Layer 1 (similar to coins)
        for layer_idx, layer in enumerate(self.tmx_data.layers):
            if hasattr(layer, 'data') or hasattr(layer, 'tiles'):
                try:
                    for y in range(self.map_height_tiles):
                        for x in range(self.map_width_tiles):
                            try:
                                gid = self.tmx_data.get_tile_gid(x, y, layer_idx)
                                if gid == 0:
                                    continue  # Empty tile
                                
                                # Check tile properties for class="sword" or type="sword"
                                tile_props = self.tmx_data.get_tile_properties_by_gid(gid)
                                if tile_props:
                                    tile_class = tile_props.get('class', '')
                                    tile_type = tile_props.get('type', '')
                                    # Check if class or type is "sword" (case-insensitive)
                                    is_sword = (tile_class and tile_class.lower().strip() == 'sword') or \
                                              (tile_type and tile_type.lower().strip() == 'sword')
                                    if is_sword:
                                        img = self.tmx_data.get_tile_image(x, y, layer_idx)
                                        if img is not None:
                                            sword = Sword(img, x * 32, y * 32)
                                            self.sword_group.add(sword)
                                            swords_spawned += 1
                                            print(f"DEBUG: Found sword at ({x}, {y}) in layer {layer_idx}, GID={gid}, Class='{tile_class}', Type='{tile_type}'")
                                            # Update sword_gids to track this GID for collision exclusion
                                            self.sword_gids.add(gid)
                                            # Clear tile from layer so it's not drawn twice
                                            try:
                                                # Clear from current layer
                                                if hasattr(layer, 'data'):
                                                    if isinstance(layer.data, list):
                                                        if isinstance(layer.data[y], list):
                                                            layer.data[y][x] = 0
                                                        else:
                                                            # 1D array: index = y * width + x
                                                            idx = y * self.map_width_tiles + x
                                                            if idx < len(layer.data):
                                                                layer.data[idx] = 0
                                                # Also clear from Tile Layer 1 if sword is in a different layer
                                                if layer_idx != self.layer_index and self.layer_index is not None:
                                                    tile_layer = self.tmx_data.layers[self.layer_index]
                                                    tile_gid = self.tmx_data.get_tile_gid(x, y, self.layer_index)
                                                    if tile_gid == gid:  # Same GID, clear it too
                                                        if hasattr(tile_layer, 'data'):
                                                            if isinstance(tile_layer.data, list):
                                                                if isinstance(tile_layer.data[y], list):
                                                                    tile_layer.data[y][x] = 0
                                                                else:
                                                                    idx = y * self.map_width_tiles + x
                                                                    if idx < len(tile_layer.data):
                                                                        tile_layer.data[idx] = 0
                                            except Exception as e:
                                                print(f"DEBUG: Error clearing sword tile at ({x}, {y}): {e}")
                                                pass
                            except Exception:
                                continue
                except Exception as e:
                    print(f"DEBUG: Error scanning layer {layer_idx} for swords: {e}")
                    continue
        
        # Also check object layers for sword objects (fallback)
        for layer in self.tmx_data.layers:
            layer_name = getattr(layer, 'name', '') or ''
            
            # Check if this layer might have objects (Enemies, Treasure, etc.)
            if hasattr(layer, 'objects'):
                objects_list = layer.objects
            else:
                # Try to get objects if it's a TiledObjectGroup
                try:
                    objects_list = list(layer)
                except:
                    objects_list = []
            
            for obj in objects_list:
                obj_type = getattr(obj, 'type', '') or ''
                obj_name = getattr(obj, 'name', '') or ''
                obj_class = getattr(obj, 'class', '') or ''
                
                # Check if this is a sword
                is_sword = (obj_type and obj_type.lower().strip() == 'sword') or \
                          (obj_class and obj_class.lower().strip() == 'sword') or \
                          (obj_name and obj_name.lower().strip() == 'sword')
                
                if is_sword:
                    # Get position from object
                    x = int(getattr(obj, 'x', 0))
                    y = int(getattr(obj, 'y', 0))
                    
                    # Try to get image from object GID or use default
                    sword_image = None
                    try:
                        obj_gid = getattr(obj, 'gid', 0)
                        if obj_gid > 0:
                            sword_image = self.tmx_data.get_tile_image_by_gid(obj_gid)
                            self.sword_gids.add(obj_gid)  # Track GID
                    except:
                        pass
                    
                    # If no image from GID, try to load a default sword image
                    if sword_image is None:
                        try:
                            sword_image = safe_load_image(pygame, 'Images', 'Items', 'fox_run_sword_right.png')
                        except:
                            # Create a simple colored rectangle as fallback
                            sword_image = pygame.Surface((32, 32))
                            sword_image.fill((255, 215, 0))  # Gold color
                    
                    # Create sword sprite
                    sword = Sword(sword_image, x, y)
                    self.sword_group.add(sword)
                    swords_spawned += 1
                    print(f"DEBUG: Spawned sword from object at ({x}, {y})")
        
        return swords_spawned
    
    def _spawn_boxes_from_layer(self):
        """Spawn box sprites from tiles with class/type='box' (similar to coins)"""
        print("DEBUG: Looking for tiles with class='box'")
        boxes_spawned = 0
        
        # Scan ALL tile layers, not just Tile Layer 1 (similar to coins)
        for layer_idx, layer in enumerate(self.tmx_data.layers):
            if hasattr(layer, 'data') or hasattr(layer, 'tiles'):
                try:
                    for y in range(self.map_height_tiles):
                        for x in range(self.map_width_tiles):
                            try:
                                gid = self.tmx_data.get_tile_gid(x, y, layer_idx)
                                if gid == 0:
                                    continue  # Empty tile
                                
                                # Check tile properties for class="box" or type="box"
                                tile_props = self.tmx_data.get_tile_properties_by_gid(gid)
                                if tile_props:
                                    tile_class = tile_props.get('class', '')
                                    tile_type = tile_props.get('type', '')
                                    # Check if class or type is "box" (case-insensitive)
                                    is_box = (tile_class and tile_class.lower().strip() == 'box') or \
                                             (tile_type and tile_type.lower().strip() == 'box')
                                    if is_box:
                                        img = self.tmx_data.get_tile_image(x, y, layer_idx)
                                        if img is not None:
                                            box = Box(img, x * 32, y * 32)
                                            self.box_group.add(box)
                                            boxes_spawned += 1
                                            print(f"DEBUG: Found box at ({x}, {y}) in layer {layer_idx}, GID={gid}, Class='{tile_class}', Type='{tile_type}'")
                                            # Update box_gids to track this GID for collision exclusion
                                            self.box_gids.add(gid)
                                            # Clear tile from layer so it's not drawn twice
                                            try:
                                                # Clear from current layer
                                                if hasattr(layer, 'data'):
                                                    if isinstance(layer.data, list):
                                                        if isinstance(layer.data[y], list):
                                                            layer.data[y][x] = 0
                                                        else:
                                                            # 1D array: index = y * width + x
                                                            idx = y * self.map_width_tiles + x
                                                            if idx < len(layer.data):
                                                                layer.data[idx] = 0
                                                # Also clear from Tile Layer 1 if box is in a different layer
                                                if layer_idx != self.layer_index and self.layer_index is not None:
                                                    tile_layer = self.tmx_data.layers[self.layer_index]
                                                    tile_gid = self.tmx_data.get_tile_gid(x, y, self.layer_index)
                                                    if tile_gid == gid:  # Same GID, clear it too
                                                        if hasattr(tile_layer, 'data'):
                                                            if isinstance(tile_layer.data, list):
                                                                if isinstance(tile_layer.data[y], list):
                                                                    tile_layer.data[y][x] = 0
                                                                else:
                                                                    idx = y * self.map_width_tiles + x
                                                                    if idx < len(tile_layer.data):
                                                                        tile_layer.data[idx] = 0
                                            except Exception as e:
                                                print(f"DEBUG: Error clearing box tile at ({x}, {y}): {e}")
                                                pass
                            except Exception:
                                continue
                except Exception as e:
                    print(f"DEBUG: Error scanning layer {layer_idx} for boxes: {e}")
                    continue
        
        return boxes_spawned
    
    def _spawn_stars_from_layer(self):
        """Spawn star sprites from tiles with class/type='star' (similar to coins)"""
        print("DEBUG: Looking for tiles with class='star'")
        stars_spawned = 0
        
        # Scan ALL tile layers, not just Tile Layer 1 (similar to coins)
        for layer_idx, layer in enumerate(self.tmx_data.layers):
            if hasattr(layer, 'data') or hasattr(layer, 'tiles'):
                try:
                    for y in range(self.map_height_tiles):
                        for x in range(self.map_width_tiles):
                            try:
                                gid = self.tmx_data.get_tile_gid(x, y, layer_idx)
                                if gid == 0:
                                    continue  # Empty tile
                                
                                # Check tile properties for class="star" or type="star"
                                tile_props = self.tmx_data.get_tile_properties_by_gid(gid)
                                if tile_props:
                                    tile_class = tile_props.get('class', '')
                                    tile_type = tile_props.get('type', '')
                                    # Check if class or type is "star" (case-insensitive)
                                    is_star = (tile_class and tile_class.lower().strip() == 'star') or \
                                              (tile_type and tile_type.lower().strip() == 'star')
                                    if is_star:
                                        img = self.tmx_data.get_tile_image(x, y, layer_idx)
                                        if img is not None:
                                            star = Star(img, x * 32, y * 32)
                                            self.star_group.add(star)
                                            stars_spawned += 1
                                            print(f"DEBUG: Found star at ({x}, {y}) in layer {layer_idx}, GID={gid}, Class='{tile_class}', Type='{tile_type}'")
                                            # Update star_gids to track this GID for collision exclusion
                                            self.star_gids.add(gid)
                                            # Clear tile from layer so it's not drawn twice
                                            try:
                                                # Clear from current layer
                                                if hasattr(layer, 'data'):
                                                    if isinstance(layer.data, list):
                                                        if isinstance(layer.data[y], list):
                                                            layer.data[y][x] = 0
                                                        else:
                                                            # 1D array: index = y * width + x
                                                            idx = y * self.map_width_tiles + x
                                                            if idx < len(layer.data):
                                                                layer.data[idx] = 0
                                                # Also clear from Tile Layer 1 if star is in a different layer
                                                if layer_idx != self.layer_index and self.layer_index is not None:
                                                    tile_layer = self.tmx_data.layers[self.layer_index]
                                                    tile_gid = self.tmx_data.get_tile_gid(x, y, self.layer_index)
                                                    if tile_gid == gid:  # Same GID, clear it too
                                                        if hasattr(tile_layer, 'data'):
                                                            if isinstance(tile_layer.data, list):
                                                                if isinstance(tile_layer.data[y], list):
                                                                    tile_layer.data[y][x] = 0
                                                                else:
                                                                    idx = y * self.map_width_tiles + x
                                                                    if idx < len(tile_layer.data):
                                                                        tile_layer.data[idx] = 0
                                            except Exception as e:
                                                print(f"DEBUG: Error clearing star tile at ({x}, {y}): {e}")
                                                pass
                            except Exception:
                                continue
                except Exception as e:
                    print(f"DEBUG: Error scanning layer {layer_idx} for stars: {e}")
                    continue
        
        return stars_spawned
    
    def _spawn_keys_from_layer(self):
        """Spawn key sprites from tiles with class/type='key' (similar to coins/stars)"""
        print("DEBUG: Looking for tiles with class='key'")
        keys_spawned = 0
        
        # Scan ALL tile layers, not just Tile Layer 1 (similar to coins)
        for layer_idx, layer in enumerate(self.tmx_data.layers):
            if hasattr(layer, 'data') or hasattr(layer, 'tiles'):
                try:
                    for y in range(self.map_height_tiles):
                        for x in range(self.map_width_tiles):
                            try:
                                gid = self.tmx_data.get_tile_gid(x, y, layer_idx)
                                if gid == 0:
                                    continue  # Empty tile
                                
                                # Check tile properties for class="key" or type="key"
                                tile_props = self.tmx_data.get_tile_properties_by_gid(gid)
                                if tile_props:
                                    tile_class = tile_props.get('class', '')
                                    tile_type = tile_props.get('type', '')
                                    # Check if class or type is "key" (case-insensitive)
                                    is_key = (tile_class and tile_class.lower().strip() == 'key') or \
                                             (tile_type and tile_type.lower().strip() == 'key')
                                    if is_key:
                                        img = self.tmx_data.get_tile_image(x, y, layer_idx)
                                        if img is not None:
                                            key = Key(img, x * 32, y * 32)
                                            self.key_group.add(key)
                                            keys_spawned += 1
                                            print(f"DEBUG: Found key at ({x}, {y}) in layer {layer_idx}, GID={gid}, Class='{tile_class}', Type='{tile_type}'")
                                            # Update key_gids to track this GID for collision exclusion
                                            self.key_gids.add(gid)
                                            # Clear tile from layer so it's not drawn twice
                                            try:
                                                # Clear from current layer
                                                if hasattr(layer, 'data'):
                                                    if isinstance(layer.data, list):
                                                        if isinstance(layer.data[y], list):
                                                            layer.data[y][x] = 0
                                                        else:
                                                            # 1D array: index = y * width + x
                                                            idx = y * self.map_width_tiles + x
                                                            if idx < len(layer.data):
                                                                layer.data[idx] = 0
                                                # Also clear from Tile Layer 1 if key is in a different layer
                                                if layer_idx != self.layer_index and self.layer_index is not None:
                                                    tile_layer = self.tmx_data.layers[self.layer_index]
                                                    tile_gid = self.tmx_data.get_tile_gid(x, y, self.layer_index)
                                                    if tile_gid == gid:  # Same GID, clear it too
                                                        if hasattr(tile_layer, 'data'):
                                                            if isinstance(tile_layer.data, list):
                                                                if isinstance(tile_layer.data[y], list):
                                                                    tile_layer.data[y][x] = 0
                                                                else:
                                                                    idx = y * self.map_width_tiles + x
                                                                    if idx < len(tile_layer.data):
                                                                        tile_layer.data[idx] = 0
                                            except Exception as e:
                                                print(f"DEBUG: Error clearing key tile at ({x}, {y}): {e}")
                                                pass
                            except Exception:
                                continue
                except Exception as e:
                    print(f"DEBUG: Error scanning layer {layer_idx} for keys: {e}")
                    continue
        
        return keys_spawned
    
    def _init_lava_tiles(self):
        """Initialize lava tiles from map - scan all tiles with class/type='lava'"""
        print("DEBUG: Looking for tiles with class='lava'")
        
        # Scan ALL tile layers
        for layer_idx, layer in enumerate(self.tmx_data.layers):
            if hasattr(layer, 'data') or hasattr(layer, 'tiles'):
                try:
                    for y in range(self.map_height_tiles):
                        for x in range(self.map_width_tiles):
                            try:
                                gid = self.tmx_data.get_tile_gid(x, y, layer_idx)
                                if gid == 0:
                                    continue  # Empty tile
                                
                                # Check tile properties for class="lava" or type="lava"
                                tile_props = self.tmx_data.get_tile_properties_by_gid(gid)
                                if tile_props:
                                    tile_class = tile_props.get('class', '')
                                    tile_type = tile_props.get('type', '')
                                    # Check if class or type is "lava" (case-insensitive)
                                    is_lava = (tile_class and tile_class.lower().strip() == 'lava') or \
                                              (tile_type and tile_type.lower().strip() == 'lava')
                                    if is_lava:
                                        self.lava_gids.add(gid)
                                        print(f"DEBUG: Found lava tile at ({x}, {y}) in layer {layer_idx}, GID={gid}, Class='{tile_class}', Type='{tile_type}'")
                            except Exception:
                                continue
                except Exception as e:
                    print(f"DEBUG: Error scanning layer {layer_idx} for lava: {e}")
                    continue
    
    def _check_lava_collision(self):
        """Check if player is touching lava tiles and apply continuous damage"""
        inset = getattr(self, 'hitbox_inset', 0)
        player_rect = pygame.Rect(
            int(self.player_x + inset), 
            int(self.player_y + inset), 
            self.player_w - 2 * inset, 
            self.player_h - 2 * inset
        )
        
        # Check which tiles the player is overlapping
        start_col = max(0, player_rect.left // 32)
        end_col = min(self.map_width_tiles - 1, (player_rect.right-1) // 32)
        start_row = max(0, player_rect.top // 32)
        end_row = min(self.map_height_tiles - 1, (player_rect.bottom-1) // 32)
        
        touching_lava = False
        for col in range(start_col, end_col + 1):
            for row in range(start_row, end_row + 1):
                gid = self.tmx_data.get_tile_gid(col, row, self.layer_index)
                if gid in self.lava_gids:
                    touching_lava = True
                    break
            if touching_lava:
                break
        
        # Check if player just entered lava (wasn't in lava before)
        just_entered = not self.in_lava and touching_lava
        
        self.in_lava = touching_lava
        
        # Apply damage if in lava and cooldown is ready
        if self.in_lava and self.lava_damage_cooldown <= 0:
            # Take damage
            damage_amount = 20
            self.health = max(0, self.health - damage_amount)
            self.lava_damage_cooldown = self.lava_damage_interval
            
            # Play lava sound (only when first entering or periodically)
            if just_entered or self.lava_damage_cooldown == self.lava_damage_interval:
                if self.lava_sound is not None:
                    try:
                        # Play sound for maximum 4 seconds (4000 milliseconds)
                        self.lava_sound.play(maxtime=4000)
                    except Exception:
                        pass
            
            # Create damage text above player
            damage_text_x = self.player_x + self.player_w // 2
            damage_text_y = self.player_y
            damage_text = DamageText(damage_amount, damage_text_x, damage_text_y, self.ui_font)
            self.damage_text_group.add(damage_text)
            
            # Trigger flash effect
            self.flash_duration = 10  # Flash for 10 frames
            self.flash_alpha = 255
    
    def _draw_game_over(self):
        """Draw game over screen with background and text"""
        # Draw background
        self._draw_parallax_background()
        
        # Draw semi-transparent overlay
        overlay = pygame.Surface((self.window_width, self.window_height))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))
        
        # Draw "Game Over" text
        game_over_text = self.game_over_font.render("GAME OVER", True, (255, 0, 0))
        game_over_rect = game_over_text.get_rect(center=(self.window_width // 2, self.window_height // 2 - 50))
        self.screen.blit(game_over_text, game_over_rect)
        
        # Draw final score
        final_score_text = self.ui_font.render(f"Final Score: {self.score}", True, (255, 255, 255))
        final_score_rect = final_score_text.get_rect(center=(self.window_width // 2, self.window_height // 2 + 20))
        self.screen.blit(final_score_text, final_score_rect)
    
    def _draw_win_screen(self):
        """Draw win screen with background and text"""
        # Draw background
        self._draw_parallax_background()
        
        # Draw semi-transparent overlay
        overlay = pygame.Surface((self.window_width, self.window_height))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))
        
        # Draw "YOU WIN!" text
        win_text = self.game_over_font.render("YOU WIN!", True, (0, 255, 0))
        win_rect = win_text.get_rect(center=(self.window_width // 2, self.window_height // 2 - 50))
        self.screen.blit(win_text, win_rect)
        
        # Draw final score
        final_score_text = self.ui_font.render(f"Final Score: {self.score}", True, (255, 255, 255))
        final_score_rect = final_score_text.get_rect(center=(self.window_width // 2, self.window_height // 2 + 20))
        self.screen.blit(final_score_text, final_score_rect)

    def _collect_items(self):
        inset = getattr(self, 'hitbox_inset', 0)
        hit = pygame.Rect(int(self.player_x + inset), int(self.player_y + inset), self.player_w - 2 * inset, self.player_h - 2 * inset)
        
        # Collect tile-based items (id 1) if any exist
        if self.item_gid_score:
            start_col = max(0, hit.left // 32)
            end_col = min(self.map_width_tiles - 1, (hit.right-1) // 32)
            start_row = max(0, hit.top // 32)
            end_row = min(self.map_height_tiles - 1, (hit.bottom-1) // 32)
            for col in range(start_col, end_col + 1):
                for row in range(start_row, end_row + 1):
                    gid = self.tmx_data.get_tile_gid(col, row, self.layer_index)
                    if gid in self.item_gid_score:
                        self.score += self.item_gid_score[gid]
                        # remove tile by setting gid to 0 in layer data
                        try:
                            self.tmx_data.layers[self.layer_index].data[row][col] = 0
                        except Exception:
                            pass

        # sprite-based coin collection - ALWAYS check coins
        if len(self.coin_group) > 0:
            # Build a lightweight sprite for collision with world coordinates
            tmp_player = pygame.sprite.Sprite()
            tmp_player.rect = hit
            # Don't kill immediately, we need to check for split coins (7 and 11)
            hits = pygame.sprite.spritecollide(tmp_player, self.coin_group, False)
            if hits:
                coins_to_kill = set()
                score_to_add = 0
                handled_group_7_11 = set()  # Track which groups we've already handled
                
                for hit_coin in hits:
                    local_id = getattr(hit_coin, 'local_id', None)
                    
                    # If coin is ID 7 or 11, find its partner within 1 tile radius
                    if local_id in (7, 11):
                        # Check if we've already handled this coin
                        coin_key = (getattr(hit_coin, 'tile_x', None), getattr(hit_coin, 'tile_y', None), local_id)
                        if coin_key in handled_group_7_11:
                            continue  # Already handled this group
                        
                        # Find partner coin (the other ID: if hit is 7, find 11; if hit is 11, find 7)
                        partner_id = 11 if local_id == 7 else 7
                        hit_tile_x = getattr(hit_coin, 'tile_x', None)
                        hit_tile_y = getattr(hit_coin, 'tile_y', None)
                        
                        if hit_tile_x is not None and hit_tile_y is not None:
                            partner_coins = [hit_coin]  # Start with the hit coin
                            
                            # Find the partner coin (7 or 11) within 1 tile radius
                            for coin in list(self.coin_group):
                                coin_local_id = getattr(coin, 'local_id', None)
                                coin_tile_x = getattr(coin, 'tile_x', None)
                                coin_tile_y = getattr(coin, 'tile_y', None)
                                
                                # Check if coin is the partner (7 or 11) and within 1 tile radius
                                if coin_local_id == partner_id:
                                    if coin_tile_x is not None and coin_tile_y is not None:
                                        dx = abs(coin_tile_x - hit_tile_x)
                                        dy = abs(coin_tile_y - hit_tile_y)
                                        # Within 1 tile radius (manhattan distance <= 1)
                                        if dx <= 1 and dy <= 1:
                                            partner_coins.append(coin)
                                            break  # Only find one partner
                            
                            # Kill all coins in this group (both 7 and 11 together)
                            for coin in partner_coins:
                                coins_to_kill.add(coin)
                                # Mark this group as handled
                                coin_key = (getattr(coin, 'tile_x', None), getattr(coin, 'tile_y', None), getattr(coin, 'local_id', None))
                                handled_group_7_11.add(coin_key)
                            
                            # Add score only once for the whole group (both tiles = 1 coin)
                            if len(partner_coins) > 0:
                                score_to_add += 100
                    else:
                        # Regular coin (not 7 or 11), kill individually
                        coins_to_kill.add(hit_coin)
                        score_to_add += 100
                
                # Kill all coins in the set
                for coin in coins_to_kill:
                    coin.kill()
                
                # Add score
                if score_to_add > 0:
                    self.score += score_to_add
                    # Play sound once if any coins collected
                    if self.coin_sound is not None:
                        try:
                            self.coin_sound.play()
                        except Exception:
                            pass

    def _spawn_coins_from_layer(self):
        # Only find tiles with class="coin" property
        print("DEBUG: Looking for tiles with class='coin'")
        coins_spawned = 0
        
        # Scan ALL tile layers, not just Tile Layer 1
        for layer_idx, layer in enumerate(self.tmx_data.layers):
            if hasattr(layer, 'data') or hasattr(layer, 'tiles'):
                try:
                    for y in range(self.map_height_tiles):
                        for x in range(self.map_width_tiles):
                            try:
                                gid = self.tmx_data.get_tile_gid(x, y, layer_idx)
                                if gid == 0:
                                    continue  # Empty tile
                                
                                # Check tile properties for class="coin" or type="coin"
                                tile_props = self.tmx_data.get_tile_properties_by_gid(gid)
                                if tile_props:
                                    tile_class = tile_props.get('class', '')
                                    tile_type = tile_props.get('type', '')
                                    # Check if class or type is "coin" (case-insensitive)
                                    is_coin = (tile_class and tile_class.lower().strip() == 'coin') or \
                                              (tile_type and tile_type.lower().strip() == 'coin')
                                    if is_coin:
                                        img = self.tmx_data.get_tile_image(x, y, layer_idx)
                                        if img is not None:
                                            # Get local_id from properties (for grouping split coins)
                                            local_id = tile_props.get('id', None)
                                            coin = Coin(img, x * 32, y * 32, local_id=local_id, tile_x=x, tile_y=y)
                                            self.coin_group.add(coin)
                                            coins_spawned += 1
                                            print(f"DEBUG: Found coin at ({x}, {y}) in layer {layer_idx}, GID={gid}, Local ID={local_id}, Class='{tile_class}', Type='{tile_type}'")
                                            # Update coin_gids to track this GID for collision exclusion
                                            self.coin_gids.add(gid)
                                            # clear tile from layer so it's not drawn twice
                                            # Also clear from Tile Layer 1 if this is a different layer
                                            try:
                                                # Clear from current layer
                                                if hasattr(layer, 'data'):
                                                    if isinstance(layer.data, list):
                                                        if isinstance(layer.data[y], list):
                                                            layer.data[y][x] = 0
                                                        else:
                                                            # 1D array: index = y * width + x
                                                            idx = y * self.map_width_tiles + x
                                                            if idx < len(layer.data):
                                                                layer.data[idx] = 0
                                                # Also clear from Tile Layer 1 if coin is in a different layer
                                                if layer_idx != self.layer_index and self.layer_index is not None:
                                                    tile_layer = self.tmx_data.layers[self.layer_index]
                                                    tile_gid = self.tmx_data.get_tile_gid(x, y, self.layer_index)
                                                    if tile_gid == gid:  # Same GID, clear it too
                                                        if hasattr(tile_layer, 'data'):
                                                            if isinstance(tile_layer.data, list):
                                                                if isinstance(tile_layer.data[y], list):
                                                                    tile_layer.data[y][x] = 0
                                                                else:
                                                                    idx = y * self.map_width_tiles + x
                                                                    if idx < len(tile_layer.data):
                                                                        tile_layer.data[idx] = 0
                                            except Exception as e:
                                                print(f"DEBUG: Error clearing tile at ({x}, {y}): {e}")
                                                pass
                            except Exception:
                                continue
                except Exception as e:
                    print(f"DEBUG: Error scanning layer {layer_idx}: {e}")
                    continue
        
        return coins_spawned

    def _spawn_skeletons_from_layer(self):
        """Spawn skeleton enemies from Enemies layer objects with class/type='skel'"""
        skeletons_spawned = 0
        
        # Load Enemies layer similar to Tile Layer 1
        try:
            enemies_layer = self.tmx_data.get_layer_by_name('Enemies')
            if enemies_layer:
                print(f"DEBUG: Found Enemies layer, type: {type(enemies_layer)}")
                # TiledObjectGroup can be iterated directly or may have objects attribute
                objects_list = None
                if hasattr(enemies_layer, 'objects'):
                    objects_list = enemies_layer.objects
                else:
                    # Try iterating the layer directly (TiledObjectGroup is a list-like object)
                    try:
                        objects_list = list(enemies_layer)
                        print(f"DEBUG: TiledObjectGroup can be iterated directly, length: {len(objects_list)}")
                    except:
                        pass
                
                if objects_list:
                    print(f"DEBUG: Enemies layer has {len(objects_list)} objects")
                    for obj in objects_list:
                        obj_type = getattr(obj, 'type', '') or ''
                        obj_name = getattr(obj, 'name', '') or ''
                        obj_class = getattr(obj, 'class', '') or ''
                        
                        # Check if this is a skeleton (class or type is 'skel')
                        is_skel = (obj_type and obj_type.lower().strip() == 'skel') or \
                                  (obj_class and obj_class.lower().strip() == 'skel') or \
                                  (obj_name and obj_name.lower().strip() == 'skel')
                        
                        if is_skel:
                            # Get position from object
                            x = int(getattr(obj, 'x', 0))
                            y = int(getattr(obj, 'y', 0))
                            
                            # Create skeleton at this position
                            skeleton = Skeleton(self.skel_image_right, self.skel_image_left, x, y)
                            self.skeleton_group.add(skeleton)
                            skeletons_spawned += 1
                            print(f"DEBUG: Spawned skeleton at ({x}, {y})")
                else:
                    print(f"DEBUG: Enemies layer found but cannot access objects. Available attributes: {[attr for attr in dir(enemies_layer) if not attr.startswith('_')]}")
            else:
                print("DEBUG: Enemies layer not found")
        except Exception as e:
            print(f"DEBUG: Error loading Enemies layer: {e}")
            # Fallback: try to find layer by iterating
            for layer in self.tmx_data.layers:
                if hasattr(layer, 'name') and getattr(layer, 'name', None) == 'Enemies':
                    if hasattr(layer, 'objects'):
                        for obj in layer.objects:
                            obj_type = getattr(obj, 'type', '') or ''
                            obj_name = getattr(obj, 'name', '') or ''
                            obj_class = getattr(obj, 'class', '') or ''
                            
                            is_skel = (obj_type and obj_type.lower().strip() == 'skel') or \
                                      (obj_class and obj_class.lower().strip() == 'skel') or \
                                      (obj_name and obj_name.lower().strip() == 'skel')
                            
                            if is_skel:
                                x = int(getattr(obj, 'x', 0))
                                y = int(getattr(obj, 'y', 0))
                                skeleton = Skeleton(self.skel_image_right, self.skel_image_left, x, y)
                                self.skeleton_group.add(skeleton)
                                skeletons_spawned += 1
                                print(f"DEBUG: Spawned skeleton at ({x}, {y}) (fallback method)")
        
        return skeletons_spawned
    
    def _spawn_bosses_from_layer(self):
        """Spawn boss enemies from Enemies layer objects with class/type='boss'"""
        bosses_spawned = 0
        
        # Load Enemies layer similar to Tile Layer 1
        try:
            enemies_layer = self.tmx_data.get_layer_by_name('Enemies')
            if enemies_layer:
                print(f"DEBUG: Found Enemies layer for bosses, type: {type(enemies_layer)}")
                # TiledObjectGroup can be iterated directly or may have objects attribute
                objects_list = None
                if hasattr(enemies_layer, 'objects'):
                    objects_list = enemies_layer.objects
                else:
                    # Try iterating the layer directly (TiledObjectGroup is a list-like object)
                    try:
                        objects_list = list(enemies_layer)
                        print(f"DEBUG: TiledObjectGroup can be iterated directly, length: {len(objects_list)}")
                    except:
                        pass
                
                if objects_list:
                    print(f"DEBUG: Enemies layer has {len(objects_list)} objects")
                    for obj in objects_list:
                        obj_type = getattr(obj, 'type', '') or ''
                        obj_name = getattr(obj, 'name', '') or ''
                        obj_class = getattr(obj, 'class', '') or ''
                        
                        # Check if this is a boss (class or type is 'boss')
                        is_boss = (obj_type and obj_type.lower().strip() == 'boss') or \
                                  (obj_class and obj_class.lower().strip() == 'boss') or \
                                  (obj_name and obj_name.lower().strip() == 'boss')
                        
                        if is_boss:
                            # Get position from object
                            x = int(getattr(obj, 'x', 0))
                            y = int(getattr(obj, 'y', 0))
                            
                            # Create boss at this position
                            boss = Boss(self.boss_sprite_images, self.bullet_image, x, y)
                            self.boss_group.add(boss)
                            bosses_spawned += 1
                            print(f"DEBUG: Spawned boss at ({x}, {y})")
                else:
                    print(f"DEBUG: Enemies layer found but cannot access objects for bosses.")
            else:
                print("DEBUG: Enemies layer not found for bosses")
        except Exception as e:
            print(f"DEBUG: Error loading Enemies layer for bosses: {e}")
            # Fallback: try to find layer by iterating
            for layer in self.tmx_data.layers:
                if hasattr(layer, 'name') and getattr(layer, 'name', None) == 'Enemies':
                    if hasattr(layer, 'objects'):
                        for obj in layer.objects:
                            obj_type = getattr(obj, 'type', '') or ''
                            obj_name = getattr(obj, 'name', '') or ''
                            obj_class = getattr(obj, 'class', '') or ''
                            
                            is_boss = (obj_type and obj_type.lower().strip() == 'boss') or \
                                      (obj_class and obj_class.lower().strip() == 'boss') or \
                                      (obj_name and obj_name.lower().strip() == 'boss')
                            
                            if is_boss:
                                x = int(getattr(obj, 'x', 0))
                                y = int(getattr(obj, 'y', 0))
                                boss = Boss(self.boss_sprite_images, self.bullet_image, x, y)
                                self.boss_group.add(boss)
                                bosses_spawned += 1
                                print(f"DEBUG: Spawned boss at ({x}, {y}) (fallback method)")
        
        return bosses_spawned
    
    def _list_coin_items(self):
        """List all tiles marked as 'coin' in the TMX file"""
        print("\n=== LISTING ALL ITEMS MARKED AS COIN ===")
        coin_items = []
        
        # Scan all tilesets
        for tileset in self.tmx_data.tilesets:
            firstgid = getattr(tileset, 'firstgid', 0)
            tileset_name = getattr(tileset, 'name', '') or ''
            tileset_source = getattr(tileset, 'source', '') or ''
            
            # Check each tile in the tileset
            max_tile_id = getattr(tileset, 'tilecount', 0)
            for local_id in range(max_tile_id):
                gid = firstgid + local_id
                tile_props = self.tmx_data.get_tile_properties_by_gid(gid)
                
                if tile_props:
                    # Check if tile has class="coin" or property "coin"
                    tile_class = tile_props.get('class', '')
                    tile_type = tile_props.get('type', '')
                    is_coin = tile_props.get('coin', False)
                    
                    if 'coin' in tile_class.lower() or 'coin' in tile_type.lower() or is_coin:
                        coin_items.append({
                            'gid': gid,
                            'local_id': local_id,
                            'firstgid': firstgid,
                            'tileset': tileset_name or tileset_source,
                            'class': tile_class,
                            'type': tile_type,
                            'properties': tile_props
                        })
        
        # Also check object layers for coin objects
        for layer in self.tmx_data.layers:
            if hasattr(layer, 'objects'):
                for obj in layer.objects:
                    obj_type = getattr(obj, 'type', '') or ''
                    obj_name = getattr(obj, 'name', '') or ''
                    obj_class = getattr(obj, 'class', '') or ''
                    gid = getattr(obj, 'gid', 0)
                    
                    if 'coin' in obj_type.lower() or 'coin' in obj_name.lower() or 'coin' in obj_class.lower() or gid in self.coin_gids:
                        coin_items.append({
                            'gid': gid,
                            'local_id': gid - (getattr(self.tmx_data.tilesets[0], 'firstgid', 0) if self.tmx_data.tilesets else 0),
                            'firstgid': None,
                            'tileset': 'Object Layer',
                            'class': obj_class,
                            'type': obj_type,
                            'name': obj_name,
                            'x': getattr(obj, 'x', 0),
                            'y': getattr(obj, 'y', 0),
                            'properties': getattr(obj, 'properties', {})
                        })
        
        # Print results
        if coin_items:
            print(f"Found {len(coin_items)} coin items:")
            for item in coin_items:
                print(f"  - GID: {item['gid']}, Local ID: {item['local_id']}, Tileset: {item['tileset']}")
                if 'class' in item and item['class']:
                    print(f"    Class: {item['class']}")
                if 'type' in item and item['type']:
                    print(f"    Type: {item['type']}")
                if 'name' in item and item['name']:
                    print(f"    Name: {item['name']}")
                if 'x' in item:
                    print(f"    Position: ({item['x']}, {item['y']})")
                print(f"    Properties: {item['properties']}")
        else:
            print("No items found marked as 'coin'")
            print("Checking all tilesets for reference...")
            for tileset in self.tmx_data.tilesets:
                firstgid = getattr(tileset, 'firstgid', 0)
                tileset_name = getattr(tileset, 'name', '') or getattr(tileset, 'source', '') or 'Unknown'
                print(f"  Tileset: {tileset_name}, FirstGID: {firstgid}")
        
        print("=" * 40 + "\n")
        
        return coin_items

    def _find_tileset_firstgid(self, name_candidates):
        try:
            for ts in self.tmx_data.tilesets:
                ts_name = getattr(ts, 'name', '') or ''
                ts_source = getattr(ts, 'source', '') or ''
                # Normalize source to remove .tsx extension for comparison
                ts_source_base = ts_source.replace('.tsx', '').replace('.tsm', '').lower()
                for cand in name_candidates:
                    cand_lower = cand.lower()
                    if cand_lower in ts_name.lower() or cand_lower in ts_source_base:
                        firstgid = getattr(ts, 'firstgid', None)
                        if firstgid is not None:
                            return firstgid
        except Exception as e:
            print(f"DEBUG: Error finding tileset: {e}")
        return None

    def _is_solid_tile(self, col, row):
        if self.layer_index is None:
            return False
        if col < 0 or row < 0 or col >= self.map_width_tiles or row >= self.map_height_tiles:
            return False
        # Check if this tile is a coin, sword, star, key, or lava - these are NOT solid
        # Box tiles ARE solid (they block movement until broken)
        gid = self.tmx_data.get_tile_gid(col, row, self.layer_index)
        if gid == 0:
            return False  # Empty tile
        
        # FIRST: Check if this is a coin, sword, star, key, or lava by GID (fast check)
        if gid in self.coin_gids or gid in self.sword_gids or gid in self.star_gids or gid in self.key_gids or gid in self.lava_gids:
            return False  # Coin, sword, star, key, and lava tiles are NOT solid
        
        # SECOND: Check tile properties directly for class="coin"/"sword"/"star"/"key"/"lava" or type="coin"/"sword"/"star"/"key"/"lava" (even if not in gids yet)
        # Note: Box tiles are solid, so we don't exclude them here
        try:
            tile_props = self.tmx_data.get_tile_properties_by_gid(gid)
            if tile_props:
                tile_class = tile_props.get('class', '')
                tile_type = tile_props.get('type', '')
                is_coin = (tile_class and tile_class.lower().strip() == 'coin') or \
                          (tile_type and tile_type.lower().strip() == 'coin')
                is_sword = (tile_class and tile_class.lower().strip() == 'sword') or \
                           (tile_type and tile_type.lower().strip() == 'sword')
                is_star = (tile_class and tile_class.lower().strip() == 'star') or \
                          (tile_type and tile_type.lower().strip() == 'star')
                is_key = (tile_class and tile_class.lower().strip() == 'key') or \
                         (tile_type and tile_type.lower().strip() == 'key')
                is_lava = (tile_class and tile_class.lower().strip() == 'lava') or \
                          (tile_type and tile_type.lower().strip() == 'lava')
                if is_coin:
                    # Add to coin_gids for future fast checks
                    self.coin_gids.add(gid)
                    return False  # Coin tiles are NOT solid
                if is_sword:
                    # Add to sword_gids for future fast checks
                    self.sword_gids.add(gid)
                    return False  # Sword tiles are NOT solid
                if is_star:
                    # Add to star_gids for future fast checks
                    self.star_gids.add(gid)
                    return False  # Star tiles are NOT solid
                if is_key:
                    # Add to key_gids for future fast checks
                    self.key_gids.add(gid)
                    return False  # Key tiles are NOT solid
                if is_lava:
                    # Add to lava_gids for future fast checks
                    self.lava_gids.add(gid)
                    return False  # Lava tiles are NOT solid
                # Box tiles are solid, so we don't exclude them
        except Exception:
            pass
        
        # THIRD: Check if tile has an image (solid tile)
        img = self.tmx_data.get_tile_image(col, row, self.layer_index)
        return img is not None

    def _iter_colliding_tile_rects(self, rect):
        # Determine tile indices overlapped by rect and yield solid tile rects
        start_col = max(0, rect.left // 32)
        end_col = min(self.map_width_tiles - 1, (rect.right-1) // 32)
        start_row = max(0, rect.top // 32)
        end_row = min(self.map_height_tiles - 1, (rect.bottom-1) // 32)

        for col in range(start_col, end_col + 1):
            for row in range(start_row, end_row + 1):
                if self._is_solid_tile(col, row):
                    yield pygame.Rect(col * 32, row * 32, 32, 32)
        
        # Also check for box sprites (boxes are solid until broken)
        for box in self.box_group.sprites():
            if rect.colliderect(box.rect):
                yield box.rect

    def _draw_parallax_background(self):
        # Offset based on camera with slower movement for parallax effect
        ox = int(self.camera_x * self.parallax_x) % self.bg_w
        oy = int(self.camera_y * self.parallax_y) % self.bg_h

        start_x = -ox
        start_y = -oy

        x = start_x
        while x < self.window_width:
            y = start_y
            while y < self.window_height:
                self.screen.blit(self.background, (x, y))
                y += self.bg_h
            x += self.bg_w


