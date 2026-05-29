"""recall — your local AI brain: persistent memory + full observability.

Data never leaves your machine.
"""

from .core import Recall
from .config import Config

__version__ = "0.3.0"
__all__ = ["Recall", "Config", "__version__"]
