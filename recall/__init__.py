"""recall — your local AI brain: persistent memory + full observability.

Data never leaves your machine.
"""

from .core import BudgetExceeded, Recall
from .config import Config
from .adapters import register as register_adapter

__version__ = "0.9.0"
__all__ = ["Recall", "Config", "BudgetExceeded", "register_adapter", "__version__"]
