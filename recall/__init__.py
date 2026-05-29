"""recall — your local AI brain: persistent memory + full observability.

Data never leaves your machine.
"""

from .core import BudgetExceeded, Recall
from .config import Config

__version__ = "0.5.0"
__all__ = ["Recall", "Config", "BudgetExceeded", "__version__"]
