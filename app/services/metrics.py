"""Utilities to capture and persist LLM performance metrics.

This module centralises the logic required to collect telemetry from the
different LLM powered flows (chat and anomaly detection).  Metrics are printed
to the terminal for quick inspection and also appended to a CSV file so that
comparisons between models can be carried out afterwards in a spreadsheet.
"""

from __future__ import annotations

import csv
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Iterable, Iterator, Optional


try:  # Optional dependency – falls back to a simple heuristic when missing
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover - best effort only
    tiktoken = None  # type: ignore


DEFAULT_CSV_PATH = os.environ.get(
    "LLM_METRICS_CSV",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "llm_metrics.csv"),
)

BASE_FIELDS = [
    "timestamp",
    "run_name",
    "model",
    "prompt_tokens",
    "response_tokens",
    "total_tokens",
    "duration_s",
    "tokens_per_second",
    "tokens_per_minute",
    "prompt_chars",
    "response_chars",
    "prompt_messages",
    "response_chunks",
    "question_tokens",
    "context_tokens",
    "history_tokens",
    "es_hits",
    "total_es_hits",
    "es_took_ms",
    "elastic_query_type",
    "chroma_hits",
    "anomaly_events",
    "anomalies_saved",
    "notes",
]

_CSV_LOCK = threading.Lock()


def _ensure_directory(path: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def count_tokens(text: Optional[str], model: Optional[str] = None) -> int:
    """Best effort token counter.

    When :mod:`tiktoken` is available we rely on it, otherwise a simple word
    based heuristic is used.  The goal is not to be 100% accurate, but to keep
    the measurements consistent across different runs/models.
    """

    if text is None:
        return 0

    if not isinstance(text, str):
        text = str(text)

    if not text:
        return 0

    if tiktoken is not None:  # pragma: no branch - optional dependency
        encoding = None
        if model:
            try:
                encoding = tiktoken.encoding_for_model(model)
            except Exception:  # Unknown model, fall back to default encoding
                encoding = None
        if encoding is None:
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
            except Exception:
                encoding = None

        if encoding is not None:
            try:
                return len(encoding.encode(text))
            except Exception:
                pass

    # Fallback heuristic – number of whitespace separated tokens
    return len(text.split())


def count_tokens_in_messages(
    messages: Iterable[dict],
    model: Optional[str] = None,
) -> int:
    """Compute the total token usage for a list of chat messages."""

    total = 0
    for message in messages or []:
        if not isinstance(message, dict):  # defensive
            continue
        total += count_tokens(message.get("content"), model=model)
    return total


def log_metrics(metrics: dict, csv_path: Optional[str] = None) -> None:
    """Persist metrics to CSV and print a concise line to stdout."""

    path = os.path.abspath(csv_path or DEFAULT_CSV_PATH)
    row = {field: metrics.get(field, "") for field in BASE_FIELDS}

    _ensure_directory(path)
    with _CSV_LOCK:
        file_exists = os.path.isfile(path)
        with open(path, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=BASE_FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    printable = " | ".join(
        f"{key}={value}" for key, value in row.items() if value not in ("", None)
    )
    print(f"[LLM_METRICS] {printable}")


class LLMMetricsTracker:
    """Helper object used to track a single LLM interaction."""

    def __init__(
        self,
        run_name: str,
        model: str,
        *,
        csv_path: Optional[str] = None,
        token_model: Optional[str] = None,
    ) -> None:
        self.run_name = run_name
        self.model = model
        self.csv_path = csv_path or DEFAULT_CSV_PATH
        self.token_model = token_model or model
        self._prompt_parts: list[str] = []
        self._response_parts: list[str] = []
        self._extra: dict[str, object] = {}
        self._start = time.perf_counter()

    # Prompt / response helpers -------------------------------------------------
    def add_prompt(self, text: Optional[str]) -> None:
        if text:
            self._prompt_parts.append(text)

    def add_prompts(self, texts: Iterable[Optional[str]]) -> None:
        for text in texts or []:
            self.add_prompt(text)

    def record_response(self, text: Optional[str]) -> None:
        if text:
            self._response_parts.append(text)

    def update_extra(self, extra: Optional[dict]) -> None:
        if not extra:
            return
        for key, value in extra.items():
            if value is None:
                continue
            self._extra[key] = value

    def set_extra(self, key: str, value: object) -> None:
        if value is None:
            return
        self._extra[key] = value

    # Finalisation --------------------------------------------------------------
    def finalize(self, extra: Optional[dict] = None) -> dict:
        duration = time.perf_counter() - self._start
        prompt_text = "\n\n".join(self._prompt_parts)
        response_text = "".join(self._response_parts)

        prompt_tokens = count_tokens(prompt_text, model=self.token_model)
        response_tokens = count_tokens(response_text, model=self.token_model)
        total_tokens = prompt_tokens + response_tokens

        metrics = {
            "timestamp": datetime.utcnow().isoformat(),
            "run_name": self.run_name,
            "model": self.model,
            "prompt_tokens": prompt_tokens,
            "response_tokens": response_tokens,
            "total_tokens": total_tokens,
            "duration_s": round(duration, 4),
            "tokens_per_second": round(total_tokens / duration, 4) if duration > 0 else 0.0,
            "tokens_per_minute": round((total_tokens / duration) * 60, 4)
            if duration > 0
            else 0.0,
            "prompt_chars": len(prompt_text),
            "response_chars": len(response_text),
            "prompt_messages": len(self._prompt_parts),
            "response_chunks": len(self._response_parts),
        }

        metrics.update(self._extra)
        if extra:
            for key, value in extra.items():
                if value is None:
                    continue
                metrics[key] = value

        log_metrics(metrics, csv_path=self.csv_path)
        return metrics


@contextmanager
def track_llm_interaction(
    run_name: str,
    model: str,
    *,
    csv_path: Optional[str] = None,
    token_model: Optional[str] = None,
) -> Iterator[LLMMetricsTracker]:
    """Context manager to simplify metric collection."""

    tracker = LLMMetricsTracker(run_name, model, csv_path=csv_path, token_model=token_model)
    try:
        yield tracker
    finally:
        tracker.finalize()

