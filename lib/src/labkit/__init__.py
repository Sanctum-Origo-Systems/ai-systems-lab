"""labkit: the shared library every ai-systems-lab workstream builds on."""

from importlib.metadata import version

from labkit.health import HealthChecks, HealthServer, serve_from_settings
from labkit.log import configure_from_settings, configure_logging
from labkit.request_id import RequestIdMiddleware, bind, current
from labkit.settings import LabSettings, SettingsError, load_settings

__version__ = version("labkit")

__all__ = [
    "HealthChecks",
    "HealthServer",
    "LabSettings",
    "RequestIdMiddleware",
    "SettingsError",
    "__version__",
    "bind",
    "configure_from_settings",
    "configure_logging",
    "current",
    "load_settings",
    "serve_from_settings",
]
