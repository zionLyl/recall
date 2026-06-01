"""memstash — your local AI brain: persistent memory + full observability.

Data never leaves your machine.
"""

from .core import BudgetExceeded, Recall
from .config import Config
from .adapters import register as register_adapter
from .instrument import instrument

# Memstash is the brand name; Recall is kept as an alias for the core class.
Memstash = Recall

__version__ = "0.16.0"
__all__ = [
    "Memstash", "Recall", "Config", "BudgetExceeded",
    "register_adapter", "instrument", "__version__",
]
