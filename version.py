APP_NAME = "IJustWantToCut"
DEFAULT_DEV_VERSION = "0.0.0-dev"

try:
    from _build_meta import BUILD_VERSION as APP_VERSION
except ImportError:
    APP_VERSION = DEFAULT_DEV_VERSION

__all__ = ["APP_NAME", "APP_VERSION", "DEFAULT_DEV_VERSION"]
