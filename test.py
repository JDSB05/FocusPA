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
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from pathlib import Path
from time import perf_counter
from typing import Iterable, Optional, Tuple
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
from app.utils.others import ensure_model


# ---------------------------------------------------------------------------
# Constants and configuration helpers
# ---------------------------------------------------------------------------

DEFAULT_QUESTION = (
    "Quais são os principais eventos de segurança detetados nas últimas 24 horas?"
)
DEFAULT_METRICS_PATH = metrics_utils.DEFAULT_CSV_PATH
AUTO_MODELS = ["gpt-oss:120b", "deepseek-r1:8b", "gemma3:4b", "qwen3:4b"]
AUTO_LOG_LIMITS = [5, 25, 50]

POLICY = {
    "id": "CM-ENUM-001",
    "name": "Controlo de abusos no Gestor de Credenciais",
    "description": (
        "Monitoriza acessos ao Gestor de Credenciais do Windows e sinaliza padrões "
        "de leitura abusiva."
    ),
    "rules": [
        {
            "id": "ENUM-SPAM",
            "description": (
                "Mais de 5 eventos 'Enumerar Credenciais' (event.code 5379) pelo mesmo "
                "utilizador e alvo num intervalo de 10 minutos são considerados anomalia."
            ),
            "logic": "Contar as ocorrências de 5379 por utilizador+alvo numa janela móvel de 10 minutos.",
        },
        {
            "id": "CRYPTO-NORMAL",
            "description": (
                "Eventos criptográficos 5061 com ReturnCode 0x0 são operações legítimas e não são anomalia."
            ),
        },
    ],
    "anomaly_definition": (
        "Considera-se anomalia qualquer log marcado com 'is_anomaly': true porque excede o limiar definido nas regras."
    ),
}


def configure_metrics_path(path: Path | None) -> Path:
    target = path or DEFAULT_METRICS_PATH
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.environ[metrics_utils.CSV_PATH_ENV] = str(target)
    return target


def _format_summary(content: str, limit: int = 120) -> str:
    cleaned = " ".join(content.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


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
        if isinstance(parsed, dict):
            logs = parsed.get("logs")
            if isinstance(logs, list):
                return logs, context
    except json.JSONDecodeError:
        pass
    return None, context


def _sanitize_logs_for_prompt(logs: list) -> list:
    sanitized: list = []
    for entry in logs:
        if isinstance(entry, dict):
            sanitized.append({k: v for k, v in entry.items() if k != "is_anomaly"})
        else:
            sanitized.append(entry)
    return sanitized


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


def _build_context_payload(logs: list) -> dict:
    logs_for_prompt = _sanitize_logs_for_prompt(logs)
    return {"policy": POLICY, "logs": logs_for_prompt}


def _build_prompt(question: str, context_payload: dict) -> Tuple[str, str]:
    context_text = json.dumps(context_payload, indent=2, ensure_ascii=False)
    prompt = f"""Contexto (logs e políticas relevantes, tens de responder baseando-te nas políticas fornecidas, as políticas estão depois dos logs):
{context_text}

Tarefa:
Analisa os logs fornecidos aplicando rigorosamente as regras descritas em policy.rules.
Responde exclusivamente em JSON **válido** com a seguinte estrutura (sem texto antes ou depois):
{{
  "evaluations": [
    {{"_id": "<_id do log>", "is_anomaly": true|false, "reason": "Resumo técnico muito curto"}}
  ],
  "summary": "Resumo técnico muito curto"
}}
Garante que devolves uma entrada na lista "evaluations" para cada log recebido e que "is_anomaly" é sempre um booleano.
Se não conseguires cumprir algum requisito, responde com JSON válido no formato {{"evaluations": [], "summary": "formato inválido"}}.
Não acrescentes qualquer texto fora do JSON.
Hoje é {datetime.utcnow().isoformat()}Z.

Pergunta original:
{question}

Resposta:"""
    return prompt, context_text


def _count_anomalies(logs: Optional[list]) -> int:
    if not isinstance(logs, list):
        return 0
    return sum(1 for entry in logs if isinstance(entry, dict) and entry.get("is_anomaly"))


def _extract_json_object(response: str) -> Optional[dict]:
    text = rag_controller.strip_json_markdown(response.strip())
    if not text:
        return None

    decoder = json.JSONDecoder()
    idx = 0
    length = len(text)

    while idx < length:
        char = text[idx]
        if char.isspace():
            idx += 1
            continue
        if char != "{":
            next_start = text.find("{", idx)
            if next_start == -1:
                return None
            idx = next_start
        try:
            parsed, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        if isinstance(parsed, dict):
            return parsed
        idx = end
    return None


def _to_bool(value) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "sim"}:
            return True
        if lowered in {"false", "no", "0", "nao", "não"}:
            return False
    return None


def _normalize_response_payload(response: str) -> tuple[dict, bool]:
    parsed = _extract_json_object(response)
    if isinstance(parsed, dict):
        return parsed, True
    return {"evaluations": [], "summary": "formato inválido"}, False


def _extract_predictions(payload: dict) -> dict[str, bool]:
    predictions: dict[str, bool] = {}

    def _populate_from_list(items: list) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            log_id = item.get("_id") or item.get("id") or item.get("log_id")
            if not log_id:
                continue
            is_anomaly = _to_bool(item.get("is_anomaly"))
            if is_anomaly is None:
                continue
            predictions[str(log_id)] = is_anomaly

    for key in ("evaluations", "logs", "results", "entries"):
        value = payload.get(key)
        if isinstance(value, list):
            _populate_from_list(value)
            if predictions:
                break

    if not predictions:
        for key, value in payload.items():
            bool_value = _to_bool(value)
            if bool_value is None:
                continue
            predictions[str(key)] = bool_value

    return predictions


def _actual_label_map(logs: Optional[list]) -> dict[str, bool]:
    labels: dict[str, bool] = {}
    if not isinstance(logs, list):
        return labels
    for entry in logs:
        if not isinstance(entry, dict):
            continue
        log_id = entry.get("_id")
        if not log_id:
            continue
        is_anomaly = entry.get("is_anomaly")
        if isinstance(is_anomaly, bool):
            labels[str(log_id)] = is_anomaly
        elif isinstance(is_anomaly, (int, float)):
            labels[str(log_id)] = bool(is_anomaly)
        elif isinstance(is_anomaly, str):
            normalized = _to_bool(is_anomaly)
            if normalized is not None:
                labels[str(log_id)] = normalized
    return labels


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
    detected_anomalies: Optional[int]
    actual_anomalies: int
    precision: Optional[float]

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
    prompt = ""
    context_text = ""
    logs_from_prompt: Optional[list] = None
    expected_logs: Optional[list] = None
    log_file = Path(rag_controller.__file__).resolve().parent / "log.txt"
    detected_anomalies: Optional[int] = None
    actual_anomalies = 0
    precision: Optional[float] = None
    try:
        ensure_model(model)
        if light_model:
            ensure_model(light_model)

        rag_controller.LLM_MODEL = model
        rag_controller.LLM_MODEL_LIGHT = light_model

        raw_expected_logs, log_file = _expected_logs(log_limit)
        logs_for_prompt = raw_expected_logs or []
        context_payload = _build_context_payload(logs_for_prompt)
        expected_logs = context_payload.get("logs") if isinstance(context_payload, dict) else None
        prompt, context_text = _build_prompt(question, context_payload)
        logs_from_prompt, _ = _parse_logs_from_prompt(prompt)

        question_tokens = metrics_utils.count_tokens(question, model)
        context_tokens = metrics_utils.count_tokens(context_text, model)
        prompt_tokens = metrics_utils.count_tokens(prompt, model)

        start_time = perf_counter()
        response = rag_controller.ask_llm(
            prompt,
            model,
            metrics_service=None,
            metrics_operation=None,
        )
        duration = max(perf_counter() - start_time, 0.0)

        completion_tokens = metrics_utils.count_tokens(response, model)
        total_tokens = prompt_tokens + completion_tokens

        payload, payload_valid = _normalize_response_payload(response)
        predictions = _extract_predictions(payload)
        detected_anomalies = sum(1 for value in predictions.values() if value)
        actual_anomalies = _count_anomalies(logs_for_prompt)
        actual_labels = _actual_label_map(logs_for_prompt)
        if actual_labels:
            predicted_labels = (
                {log_id: bool(value) for log_id, value in predictions.items()}
                if predictions
                else {}
            )
            total = len(actual_labels)
            correct = sum(
                1
                for log_id, actual in actual_labels.items()
                if predicted_labels.get(log_id, False) == actual
            )
            precision = round((correct / total) * 100, 2)
        else:
            precision = 100.0 if not predictions else 0.0

        metrics_logger = metrics_utils.MetricsLogger(csv_path=metrics_path)
        success = "yes"
        error_message = ""
        if response.strip().startswith("❌"):
            success = "no"
            error_message = response.strip()
        elif not payload_valid:
            success = "no"
            error_message = "Resposta do modelo não estava em JSON válido."

        metrics_logger.log(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "service": "chat",
                "operation": "rag_prompt_test",
                "model": model,
                "light_model": light_model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "prompt_chars": len(prompt),
                "completion_chars": len(response),
                "duration_seconds": round(duration, 3),
                "tokens_per_second": round(
                    completion_tokens / duration, 3
                )
                if duration > 0
                else 0,
                "tokens_per_minute": round(
                    (completion_tokens / duration) * 60, 3
                )
                if duration > 0
                else 0,
                "num_es_logs": log_limit,
                "num_chroma_chunks": 0,
                "elastic_logs_limit": log_limit,
                "chroma_chunks_limit": 0,
                "events_considered": len(logs_for_prompt),
                "question_tokens": question_tokens,
                "context_tokens": context_tokens,
                "question_chars": len(question),
                "context_chars": len(context_text),
                "prompt_preview": _format_summary(prompt),
                "response_preview": _format_summary(response),
                "success": success,
                "error_message": error_message,
                "light_model": light_model,
                "log_limit": log_limit,
                "mode": mode,
                "actual_anomalies": actual_anomalies,
                "detected_anomalies": detected_anomalies,
                "precision": precision if precision is not None else "",
            }
        )

        if response.strip().startswith("❌"):
            print(f"[ERROR] Execução do LLM falhou: {response.strip()}")

        return RunResult(
            model=model,
            light_model=light_model,
            log_limit=log_limit,
            metrics_csv=metrics_path,
            prompt_logs=logs_from_prompt,
            expected_logs=expected_logs,
            log_file=log_file,
            response=response.strip(),
            detected_anomalies=detected_anomalies,
            actual_anomalies=actual_anomalies,
            precision=precision,
        )
    except Exception as exc:
        error_text = f"❌ Erro durante a execução do teste: {exc}"
        print(f"[ERROR] {error_text}")

        prompt_tokens = metrics_utils.count_tokens(prompt, model) if prompt else 0
        context_tokens = metrics_utils.count_tokens(context_text, model) if context_text else 0

        logger = metrics_utils.MetricsLogger(csv_path=metrics_path)
        logger.log(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "service": "chat",
                "operation": "rag_prompt_test",
                "model": model,
                "light_model": light_model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 0,
                "total_tokens": prompt_tokens,
                "prompt_chars": len(prompt),
                "completion_chars": 0,
                "prompt_preview": _format_summary(prompt) if prompt else "",
                "response_preview": _format_summary(error_text),
                "duration_seconds": 0,
                "tokens_per_second": 0,
                "tokens_per_minute": 0,
                "success": "no",
                "error_message": str(exc),
                "num_es_logs": log_limit,
                "elastic_logs_limit": log_limit,
                "num_chroma_chunks": 0,
                "chroma_chunks_limit": 0,
                "question_tokens": metrics_utils.count_tokens(question, model),
                "question_chars": len(question),
                "context_tokens": context_tokens,
                "context_chars": len(context_text),
                "mode": mode,
                "log_limit": log_limit,
                "events_considered": len(expected_logs) if isinstance(expected_logs, list) else 0,
                "actual_anomalies": actual_anomalies,
                "detected_anomalies": detected_anomalies if detected_anomalies is not None else "",
                "precision": precision if precision is not None else "",
            }
        )

        return RunResult(
            model=model,
            light_model=light_model,
            log_limit=log_limit,
            metrics_csv=metrics_path,
            prompt_logs=logs_from_prompt,
            expected_logs=expected_logs,
            log_file=log_file,
            response=error_text,
            detected_anomalies=detected_anomalies,
            actual_anomalies=actual_anomalies,
            precision=precision,
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
    print(
        "      anomalies_detected="
        f"{result.detected_anomalies if result.detected_anomalies is not None else 'n/a'}"
        f"/{result.actual_anomalies} precision={result.precision if result.precision is not None else 'n/a'}%"
    )
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

