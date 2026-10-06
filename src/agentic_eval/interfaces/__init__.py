"""Plugin interfaces. Everything application- or provider-specific implements one of these."""

from agentic_eval.interfaces.adapter import Adapter, AdapterError
from agentic_eval.interfaces.connector import Connector, ConnectorError, RawResponse, Session
from agentic_eval.interfaces.judge import Judge, JudgeVerdict
from agentic_eval.interfaces.metric import Metric, MetricContext

__all__ = [
    "Adapter",
    "AdapterError",
    "Connector",
    "ConnectorError",
    "Judge",
    "JudgeVerdict",
    "Metric",
    "MetricContext",
    "RawResponse",
    "Session",
]
