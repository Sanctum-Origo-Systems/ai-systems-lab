"""labkit: the shared library every ai-systems-lab workstream builds on."""

from importlib.metadata import version

__version__ = version("labkit")

__all__ = ["__version__"]
