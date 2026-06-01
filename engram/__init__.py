"""engram — your local AI brain: persistent memory + full observability.

Data never leaves your machine.
"""

from .core import BudgetExceeded, Recall
from .config import Config
from .adapters import register as register_adapter
from .instrument import instrument

# Engram is the brand name; Recall is kept as an alias for the core class.
Engram = Recall

__version__ = "0.14.0"
__all__ = [
    "Engram", "Recall", "Config", "BudgetExceeded",
    "register_adapter", "instrument", "__version__",
]
