"""Utility script to exercise the RAG controller and capture metrics.

This script can be executed in two modes:

* ``python test.py <LLM_MODEL> <LOG_LIMIT>`` runs a single prompt using the
  provided model name and the desired number of log entries extracted through
  :func:`app.controllers.rag_controller.build_final_prompt`.
* ``python test.py auto`` iterates through combinations of heavyweight and
  lightweight models together with several log limits (5, 10, 15, 20 and 25).

Each run records metrics in the CSV file defined by ``LLM_METRICS_CSV_PATH``
and prints a concise summary highlighting whether the prompt consumed the
expected number of log entries from ``log.txt``.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import sys
import types
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Lightweight stubs so the controller can be imported without heavy deps.
# ---------------------------------------------------------------------------

mock_st = types.ModuleType("sentence_transformers")
mock_embedder = MagicMock()
mock_embedder.encode.return_value = [[0.0]]
mock_st.SentenceTransformer = MagicMock(return_value=mock_embedder)
mock_st.util = types.ModuleType("sentence_transformers.util")
sys.modules.setdefault("sentence_transformers", mock_st)

mock_chromadb = types.ModuleType("chromadb")
mock_chroma_client = MagicMock()
mock_chroma_client.heartbeat.return_value = True
mock_chromadb.HttpClient = MagicMock(return_value=mock_chroma_client)
sys.modules.setdefault("chromadb", mock_chromadb)

requests_get_patcher = patch(
    "requests.get", return_value=SimpleNamespace(status_code=200, text="ok")
)
requests_get_patcher.start()
atexit.register(requests_get_patcher.stop)


# ---------------------------------------------------------------------------
# Import the controller after the environment has been prepared.
# ---------------------------------------------------------------------------

from app.controllers import rag_controller
from app.utils import metrics as metrics_utils


# ---------------------------------------------------------------------------
# Constants and configuration helpers
# ---------------------------------------------------------------------------

DEFAULT_QUESTION = (
    "Quais são os principais eventos de segurança detetados nas últimas 24 horas?"
)
DEFAULT_METRICS_PATH = metrics_utils.DEFAULT_CSV_PATH
AUTO_MODELS = ["gpt-oss:120b", "deepseek-r1:8b", "gemma3:4b", "qwen3:4b"]
AUTO_LOG_LIMITS = [5, 10, 15, 20, 25]


def configure_metrics_path(path: Path | None) -> Path:
    target = path or DEFAULT_METRICS_PATH
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.environ[metrics_utils.CSV_PATH_ENV] = str(target)
    return target


# ---------------------------------------------------------------------------
# Ollama stubbing so the metrics code can execute deterministically.
# ---------------------------------------------------------------------------


def _format_summary(content: str, limit: int = 120) -> str:
    cleaned = " ".join(content.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


def _fake_llm_response(model: str, prompt: str) -> str:
    summary = _format_summary(prompt)
    return (
        f"[fake-{model}] A responder com base em {len(prompt.split())} tokens. "
        f"Resumo do prompt: {summary}"
    )


@contextmanager
def patched_ollama_chat() -> Iterator[None]:
    def _chat(model: str, messages: List[dict], stream: bool = False, **_) -> Iterator[dict] | dict:
        prompt_text = messages[-1]["content"] if messages else ""
        reply = _fake_llm_response(model, prompt_text)
        chunk = {"message": {"content": reply}, "done": True}
        if stream:
            def _generator() -> Iterator[dict]:
                yield chunk

            return _generator()
        return chunk

    with patch.object(rag_controller.ollama, "chat", side_effect=_chat):
        yield


# ---------------------------------------------------------------------------
# Utilities to inspect the prompt built by the controller
# ---------------------------------------------------------------------------


def _extract_context(prompt: str) -> str:
    marker = "Contexto (logs e políticas relevantes"
    idx = prompt.find(marker)
    if idx == -1:
        return ""
    idx = prompt.find(":", idx)
    if idx == -1:
        return ""
    context_block = prompt[idx + 1 :]
    task_marker = "\nTarefa:"
    task_idx = context_block.find(task_marker)
    if task_idx != -1:
        context_block = context_block[:task_idx]
    return context_block.strip()


def _parse_logs_from_prompt(prompt: str) -> Tuple[Optional[list], str]:
    context = _extract_context(prompt)
    if not context:
        return None, ""
    try:
        parsed = json.loads(context)
        if isinstance(parsed, list):
            return parsed, context
    except json.JSONDecodeError:
        pass
    return None, context


def _expected_logs(limit: int) -> Tuple[Optional[list], Path]:
    base_dir = Path(rag_controller.__file__).resolve().parent
    log_file = base_dir / "log.txt"
    if not log_file.exists():
        return None, log_file
    try:
        data = json.loads(log_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, log_file
    if isinstance(data, list):
        return data[:limit], log_file
    return None, log_file


@dataclass
class RunResult:
    model: str
    light_model: str
    log_limit: int
    metrics_csv: Path
    prompt_logs: Optional[list]
    expected_logs: Optional[list]
    log_file: Path
    response: str

    def is_log_match(self) -> bool:
        return self.prompt_logs == self.expected_logs if self.expected_logs is not None else True

    def prompt_log_count(self) -> int:
        return len(self.prompt_logs) if isinstance(self.prompt_logs, list) else 0

    def expected_log_count(self) -> int:
        return len(self.expected_logs) if isinstance(self.expected_logs, list) else 0


# ---------------------------------------------------------------------------
# Core execution helpers
# ---------------------------------------------------------------------------


def run_single_experiment(
    *,
    model: str,
    light_model: str,
    log_limit: int,
    question: str,
    metrics_path: Path,
    mode: str = "single",
) -> RunResult:
    original_model = rag_controller.LLM_MODEL
    original_light = rag_controller.LLM_MODEL_LIGHT
    try:
        rag_controller.LLM_MODEL = model
        rag_controller.LLM_MODEL_LIGHT = light_model

        prompt = rag_controller.build_final_prompt([], question, num_objects=log_limit)
        logs_from_prompt, context_text = _parse_logs_from_prompt(prompt)
        expected_logs, log_file = _expected_logs(log_limit)

        metrics_extra = {
            "num_es_logs": log_limit,
            "num_chroma_chunks": 0,
            "elastic_logs_limit": log_limit,
            "chroma_chunks_limit": 0,
            "question_tokens": metrics_utils.count_tokens(question, model),
            "context_tokens": metrics_utils.count_tokens(context_text, model),
            "question_chars": len(question),
            "context_chars": len(context_text),
            "light_model": light_model,
            "log_limit": log_limit,
            "mode": mode,
        }

        response = rag_controller.ask_llm(
            prompt,
            model,
            metrics_service="chat",
            metrics_operation="rag_prompt_test",
            metrics_extra=metrics_extra,
        )

        return RunResult(
            model=model,
            light_model=light_model,
            log_limit=log_limit,
            metrics_csv=metrics_path,
            prompt_logs=logs_from_prompt,
            expected_logs=expected_logs,
            log_file=log_file,
            response=response.strip(),
        )
    finally:
        rag_controller.LLM_MODEL = original_model
        rag_controller.LLM_MODEL_LIGHT = original_light


def print_result_summary(result: RunResult) -> None:
    status = "OK" if result.is_log_match() else "MISMATCH"
    print(
        f"[RUN] model={result.model} light={result.light_model} logs={result.log_limit} -> {status}"
    )
    print(
        f"      prompt_logs={result.prompt_log_count()} expected_logs={result.expected_log_count()} "
        f"metrics_csv={result.metrics_csv}"
    )
    print(f"      response_preview={_format_summary(result.response)}")
    if not result.is_log_match():
        print(
            f"      ⚠️  Os logs extraídos do prompt não correspondem ao conteúdo esperado de {result.log_file}."
        )


def run_automatic_suite(question: str, metrics_path: Path) -> None:
    print("[AUTO] A executar a bateria completa de combinações de modelos e limites.")
    for main_model, light_model in product(AUTO_MODELS, repeat=2):
        for log_limit in AUTO_LOG_LIMITS:
            result = run_single_experiment(
                model=main_model,
                light_model=light_model,
                log_limit=log_limit,
                question=question,
                metrics_path=metrics_path,
                mode="auto",
            )
            print_result_summary(result)


# ---------------------------------------------------------------------------
# CLI handling
# ---------------------------------------------------------------------------


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Executa prompts RAG e regista métricas.")
    parser.add_argument(
        "mode_or_model",
        help="Nome do modelo a testar ou 'auto' para executar todas as combinações.",
    )
    parser.add_argument(
        "log_limit",
        nargs="?",
        type=int,
        help="Número de logs a enviar para build_final_prompt no modo manual.",
    )
    parser.add_argument(
        "--light-model",
        dest="light_model",
        default=None,
        help="Modelo lightweight a usar para reformulações (apenas modo manual).",
    )
    parser.add_argument(
        "--question",
        dest="question",
        default=DEFAULT_QUESTION,
        help="Pergunta base a ser usada nas execuções.",
    )
    parser.add_argument(
        "--metrics",
        dest="metrics",
        default=None,
        help="Caminho para o ficheiro CSV onde as métricas serão gravadas.",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    metrics_path = Path(args.metrics).expanduser() if args.metrics else None
    metrics_path = configure_metrics_path(metrics_path)

    with patched_ollama_chat():
        if args.mode_or_model.lower() == "auto":
            run_automatic_suite(args.question, metrics_path)
            return 0

        if args.log_limit is None:
            raise SystemExit("É necessário indicar o número de logs para o modo manual.")

        light_model = args.light_model or rag_controller.LLM_MODEL_LIGHT
        result = run_single_experiment(
            model=args.mode_or_model,
            light_model=light_model,
            log_limit=args.log_limit,
            question=args.question,
            metrics_path=metrics_path,
        )
        print_result_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

