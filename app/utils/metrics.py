"""Utilities for collecting and persisting LLM performance metrics.

This module centralises the logic for:
* estimating token counts (prompt/response) using ``tiktoken`` when available;
* recording runtime metrics to both the terminal log and a CSV file that can be
  opened in Excel;
* providing a simple context manager (``LLMRunMetrics``) that can be used
  around any LLM call, including streaming generators.

The goal is to offer observability over different LLM models so that
experiments can be compared under the same conditions.
"""

from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Iterable, Optional

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

# Environment variable that can override the CSV path used to persist metrics.
CSV_PATH_ENV = "LLM_METRICS_CSV_PATH"

# Default location inside the repository. The directory is created on demand.
DEFAULT_CSV_PATH = Path("metrics/llm_metrics.csv")

# Keys that are written in a fixed order to the CSV file. Additional metadata
# is still stored (prefixed with ``meta_``) so that experiments can attach
# custom information without breaking the CSV layout.
BASE_FIELDS: tuple[str, ...] = (
    "timestamp",
    "service",
    "operation",
    "model",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "prompt_chars",
    "completion_chars",
    "duration_seconds",
    "tokens_per_second",
    "tokens_per_minute",
    "num_es_logs",
    "num_chroma_chunks",
    "elastic_logs_limit",
    "chroma_chunks_limit",
    "events_considered",
    "question_tokens",
    "context_tokens",
    "question_chars",
    "context_chars",
    "prompt_preview",
    "response_preview",
    "success",
    "error_message",
)


def _resolve_csv_path() -> Path:
    """Return the path where CSV metrics should be stored."""

    env_path = os.getenv(CSV_PATH_ENV)
    if env_path:
        try:
            return Path(env_path).expanduser().resolve()
        except Exception:
            # Fall back to default if the custom path is invalid.
            pass
    return DEFAULT_CSV_PATH


# ---------------------------------------------------------------------------
# Token utilities
# ---------------------------------------------------------------------------

def count_tokens(text: str | Iterable[str] | None, model: str | None = None) -> int:
    """Estimate the number of tokens in ``text``.

    The implementation relies on ``tiktoken`` when available; otherwise it
    gracefully degrades to a whitespace split which, while approximate, still
    gives a consistent metric for comparison purposes.
    """

    if text is None:
        return 0

    if isinstance(text, (list, tuple)):
        return sum(count_tokens(t, model=model) for t in text)

    txt = str(text)
    if not txt:
        return 0

    try:
        import tiktoken

        if model:
            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                encoding = tiktoken.get_encoding("cl100k_base")
        else:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(txt))
    except Exception:
        # Fallback: whitespace split (quick and dependency free)
        return len(txt.split())


def _preview(text: str, limit: int = 160) -> str:
    """Return a shortened preview suitable for CSV logging."""

    snippet = text.strip().replace("\n", " ⏎ ")
    if len(snippet) <= limit:
        return snippet
    return snippet[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# CSV logger
# ---------------------------------------------------------------------------


class MetricsLogger:
    """Persist metric rows to disk and mirror them to the terminal."""

    def __init__(self, csv_path: Path | None = None) -> None:
        self.csv_path = csv_path or _resolve_csv_path()
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self._csv_fields = list(BASE_FIELDS)
        self._logger = logging.getLogger("llm_metrics")

    # The CSV writer is created lazily per write to keep the implementation
    # simple and robust across processes.
    def log(self, data: Dict[str, Any]) -> None:
        row = self._prepare_row(data)
        self._write_row(row)
        self._emit_console_log(row)

    def _prepare_row(self, data: Dict[str, Any]) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for key in BASE_FIELDS:
            value = data.get(key, "")
            row[key] = "" if value is None else value

        # Persist additional metadata keys as ``meta_<key>`` to avoid changing
        # the base schema when new experiments add custom values.
        for key, value in data.items():
            if key in row:
                continue
            meta_key = f"meta_{key}"
            row[meta_key] = "" if value is None else value
            if meta_key not in self._csv_fields:
                self._csv_fields.append(meta_key)
        return row

    def _write_row(self, row: Dict[str, Any]) -> None:
        file_exists = self.csv_path.exists()
        with self.csv_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self._csv_fields)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def _emit_console_log(self, row: Dict[str, Any]) -> None:
        msg = (
            "[LLM][{timestamp}] service={service} op={operation} model={model} "
            "prompt_tokens={prompt_tokens} completion_tokens={completion_tokens} "
            "duration={duration_seconds}s tokens/s={tokens_per_second} "
            "es_logs={num_es_logs} chroma_chunks={num_chroma_chunks} success={success}"
        ).format(**row)
        self._logger.info(msg)


# ---------------------------------------------------------------------------
# Context manager used around LLM executions
# ---------------------------------------------------------------------------


@dataclass
class LLMRunMetrics:
    """Context manager to capture prompt/response metrics for an LLM call."""

    model: str
    prompt_text: str
    service: str
    operation: str
    extra: Dict[str, Any] = field(default_factory=dict)
    logger: MetricsLogger | None = None

    _start_time: float = field(init=False, default=0.0)
    _start_timestamp: datetime = field(init=False, default_factory=datetime.utcnow)
    _response_parts: list[str] = field(init=False, default_factory=list)
    _success: bool = field(init=False, default=True)
    _error_message: Optional[str] = field(init=False, default=None)

    def __enter__(self) -> "LLMRunMetrics":
        self._start_timestamp = datetime.utcnow()
        self._start_time = perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        end_time = perf_counter()
        duration = max(end_time - self._start_time, 0.0)
        response_text = "".join(self._response_parts)

        prompt_tokens = count_tokens(self.prompt_text, self.model)
        completion_tokens = count_tokens(response_text, self.model)
        total_tokens = prompt_tokens + completion_tokens

        tokens_per_second = (
            completion_tokens / duration if duration > 0 else 0.0
        )

        data: Dict[str, Any] = {
            "timestamp": self._start_timestamp.isoformat(),
            "service": self.service,
            "operation": self.operation,
            "model": self.model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "prompt_chars": len(self.prompt_text),
            "completion_chars": len(response_text),
            "duration_seconds": round(duration, 3),
            "tokens_per_second": round(tokens_per_second, 3),
            "tokens_per_minute": round(tokens_per_second * 60, 3),
            "prompt_preview": _preview(self.prompt_text),
            "response_preview": _preview(response_text),
            "success": "yes" if self._success and exc_type is None else "no",
            "error_message": self._error_message or (str(exc) if exc else ""),
        }

        # Merge extra metadata.
        for key, value in self.extra.items():
            if key in data:
                # only overwrite if the base value is empty
                if data[key] in ("", None):
                    data[key] = value
            else:
                data[key] = value

        (self.logger or MetricsLogger()).log(data)

        # Returning False propagates exceptions (if any) to callers.
        return False

    # ------------------------------------------------------------------
    # Helpers used by callers while streaming responses
    # ------------------------------------------------------------------

    def add_response_chunk(self, chunk: str | None) -> None:
        if chunk:
            self._response_parts.append(str(chunk))

    def set_response_text(self, text: str | None) -> None:
        self._response_parts = [str(text or "")]

    def mark_success(self, success: bool, error_message: Optional[str] = None) -> None:
        self._success = success
        if not success:
            self._error_message = error_message

