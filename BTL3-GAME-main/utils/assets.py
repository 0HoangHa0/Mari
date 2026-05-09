import os


def get_base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def get_resources_dir():
    base_dir = os.path.abspath(os.path.join(get_base_dir(), os.pardir))
    preferred = os.path.join(base_dir, 'Resources')
    fallback = os.path.join(base_dir, 'resources')
    if os.path.isdir(preferred):
        return preferred
    if os.path.isdir(fallback):
        return fallback
    return preferred


def resource_path(*relative_parts):
    return os.path.join(get_resources_dir(), *relative_parts)


def safe_load_image(pygame_module, *relative_parts):
    path = resource_path(*relative_parts)
    image = pygame_module.image.load(path)
    return image.convert_alpha()


def safe_load_font(pygame_module, relative_path, size):
    path = resource_path(relative_path)
    return pygame_module.font.Font(path, size)


