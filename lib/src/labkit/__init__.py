"""labkit: the shared library every ai-systems-lab workstream builds on."""

from importlib.metadata import version

from labkit.settings import LabSettings, SettingsError, load_settings

__version__ = version("labkit")

__all__ = ["LabSettings", "SettingsError", "__version__", "load_settings"]
