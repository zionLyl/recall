"""recall — your local AI brain: persistent memory + full observability.

Data never leaves your machine.
"""

from .core import BudgetExceeded, Recall
from .config import Config
from .adapters import register as register_adapter
from .instrument import instrument

__version__ = "0.13.0"
__all__ = ["Recall", "Config", "BudgetExceeded", "register_adapter", "instrument", "__version__"]
