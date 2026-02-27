"""
Tactics Engine - Azazel-Gadget 意思決定の形式化・監査化・再現化
完成形B：同一入力→同一決定が再現でき、根拠が機械可読に永続化される
"""

__version__ = "0.1.0"
__name_formal__ = "Tactics Engine"

from .config_hash import ConfigHash
from .decision_logger import DecisionLogger
from .eve_parser import EVEParser, EVEParseError

__all__ = [
    "ConfigHash",
    "DecisionLogger",
    "EVEParser",
    "EVEParseError",
]
