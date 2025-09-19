"""CLI utilitário para testar as métricas do chat RAG e do serviço de anomalias."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Gera logs sintéticos e executa fluxos de chat/anomalias para medir o "
            "rendimento dos modelos LLM."
        )
    )
    parser.add_argument(
        "--num-logs",
        type=int,
        default=0,
        help="Quantidade de logs sintéticos a criar antes dos testes.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed opcional para tornar a geração de logs determinística.",
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=10,
        help="Intervalo em minutos entre cada log sintético (default: 10).",
    )
    parser.add_argument(
        "--question",
        type=str,
        default="Quais são as atividades suspeitas mais recentes nos logs de segurança?",
        help="Pergunta a enviar para o chat RAG (default focado em segurança).",
    )
    parser.add_argument(
        "--time-from",
        type=str,
        default=None,
        help="Filtro temporal inicial (ISO 8601) para a pesquisa no chat.",
    )
    parser.add_argument(
        "--time-to",
        type=str,
        default=None,
        help="Filtro temporal final (ISO 8601) para a pesquisa no chat.",
    )
    parser.add_argument(
        "--skip-chat",
        action="store_true",
        help="Ignora o fluxo de chat RAG.",
    )
    parser.add_argument(
        "--skip-anomaly",
        action="store_true",
        help="Ignora a deteção/classificação de anomalias.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=100,
        help="Número máximo de eventos a recuperar para o serviço de anomalias.",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        default=15,
        help="Janela temporal (minutos) usada na recolha de eventos recentes.",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Caminho opcional para guardar o CSV de métricas (exporta LLM_METRICS_CSV).",
    )
    return parser.parse_args()


def create_logs(num_logs: int, seed: Optional[int], interval: int) -> None:
    if num_logs <= 0:
        return

    from app.services.elastic import create_fake_winlogs

    print(
        f"[Test] A criar {num_logs} logs sintéticos (seed={seed}, intervalo={interval}m)..."
    )
    create_fake_winlogs(num_logs, seed=seed, interval_minutes=interval)


def run_chat(question: str, time_from: Optional[str], time_to: Optional[str]) -> None:
    from app.controllers.rag_controller import query_hybrid_rag

    print("[Test] ===== Início do chat RAG =====")
    print(f"[Test] Pergunta: {question}")
    resposta = query_hybrid_rag(question, time_from=time_from, time_to=time_to)
    print("[Test] Resposta do modelo:\n")
    print(resposta)
    print("\n[Test] ===== Fim do chat RAG =====")


def run_anomaly(max_events: int, minutes: int) -> None:
    from app import create_app
    from app.services.anomaly_service import detect_and_create_anomalies

    print("[Test] ===== Início da deteção de anomalias =====")
    app = create_app()
    with app.app_context():
        detect_and_create_anomalies(max_events=max_events, minutes=minutes)
    print("[Test] ===== Fim da deteção de anomalias =====")


def main() -> None:
    args = parse_args()

    if args.csv:
        os.environ["LLM_METRICS_CSV"] = os.path.abspath(args.csv)
        print(f"[Test] CSV de métricas sobrescrito para: {os.environ['LLM_METRICS_CSV']}")

    try:
        create_logs(args.num_logs, seed=args.seed, interval=args.interval_minutes)
    except Exception as exc:
        print(f"[Test][ERRO] Falha ao criar logs sintéticos: {exc}", file=sys.stderr)
        return

    if not args.skip_chat:
        try:
            run_chat(args.question, args.time_from, args.time_to)
        except Exception as exc:
            print(f"[Test][ERRO] Falha ao executar o chat RAG: {exc}", file=sys.stderr)

    if not args.skip_anomaly:
        try:
            run_anomaly(args.max_events, args.minutes)
        except Exception as exc:
            print(
                f"[Test][ERRO] Falha ao executar a deteção de anomalias: {exc}",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
