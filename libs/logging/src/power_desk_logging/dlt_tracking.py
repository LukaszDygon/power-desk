"""A dlt tracking module (`dlt.pipeline.trace.TRACKING_MODULES`, dlt's hook for Sentry and telemetry).

Registered once per process, it covers every pipeline run, whoever calls it:
- every record logged during a run carries `dlt.pipeline_name`, `dlt.step` and, once extracted, `dlt.load_id`;
- every completed load is a `dlt.load` provenance event: its load id and rows per table (normalize metrics).
"""

from __future__ import annotations

from contextvars import Token
import logging
import sys
from typing import Any

from dlt.common.pipeline import SupportsPipeline
from dlt.pipeline import trace as dlt_trace
from dlt.pipeline.trace import PipelineStepTrace, PipelineTrace

from power_desk_logging.context import Attributes, bind, unbind
from power_desk_logging.formatter import EVENT_NAME

logger = logging.getLogger(__name__)

# bindings of each open trace, by transaction id: its own, and a stack of its steps (`run` holds the others);
# unbinding the trace's drops everything bound since
_open: dict[str, Token[Attributes]] = {}
_steps: dict[str, list[Token[Attributes]]] = {}


def register() -> None:
    if (module := sys.modules[__name__]) not in dlt_trace.TRACKING_MODULES:
        dlt_trace.TRACKING_MODULES.append(module)  # pyright: ignore[reportArgumentType]


def on_start_trace(trace: PipelineTrace, step: str, pipeline: SupportsPipeline) -> None:
    _open[trace.transaction_id] = bind({"dlt.pipeline_name": pipeline.pipeline_name})


def on_start_trace_step(trace: PipelineTrace, step: str, pipeline: SupportsPipeline) -> None:
    _steps.setdefault(trace.transaction_id, []).append(bind({"dlt.step": step}))


def on_end_trace_step(
    trace: PipelineTrace, step: PipelineStepTrace, pipeline: SupportsPipeline, step_info: Any, send_state: bool
) -> None:
    succeeded = step.step_exception is None and step_info
    if succeeded and step.step == "load":
        log_loads(trace, pipeline, step_info)
    if steps := _steps.get(trace.transaction_id):
        unbind(steps.pop())
    if succeeded and step.step == "extract" and len(step_info.loads_ids) == 1:
        bind({"dlt.load_id": step_info.loads_ids[0]})  # for the steps that follow


def on_end_trace(trace: PipelineTrace, pipeline: SupportsPipeline, send_state: bool) -> None:
    _steps.pop(trace.transaction_id, None)
    if token := _open.pop(trace.transaction_id, None):
        unbind(token)


def log_loads(trace: PipelineTrace, pipeline: SupportsPipeline, load_info: Any) -> None:
    """One `dlt.load` event per load package."""
    metrics = trace.last_normalize_info.metrics if trace.last_normalize_info else {}
    for load_id in load_info.loads_ids:
        tables = metrics.get(load_id, [{}])[0].get("table_metrics", {})
        rows = {table: m.items_count for table, m in tables.items() if not table.startswith("_dlt")}
        logger.info(
            "dlt load %s into %s: %s",
            load_id,
            load_info.dataset_name,
            ", ".join(f"{table} {count}" for table, count in rows.items()) or "no rows",
            extra={
                EVENT_NAME: "dlt.load",
                "dlt.pipeline_name": pipeline.pipeline_name,
                "dlt.destination_name": load_info.destination_name,
                "dlt.dataset_name": load_info.dataset_name,
                "dlt.load_id": load_id,
                "dlt.row_counts": rows,
            },
        )
