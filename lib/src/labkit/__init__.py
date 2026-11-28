"""labkit: the shared library every ai-systems-lab workstream builds on."""

from importlib.metadata import version

from labkit.log import configure_from_settings, configure_logging
from labkit.settings import LabSettings, SettingsError, load_settings

__version__ = version("labkit")

__all__ = [
    "LabSettings",
    "SettingsError",
    "__version__",
    "configure_from_settings",
    "configure_logging",
    "load_settings",
]
