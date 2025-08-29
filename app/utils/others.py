import sys
from ollama import Client, ResponseError
from flask import request
import os

def get_client_ip():
    """Obtém o IP real do cliente, considerando proxies."""
    if request.headers.get("X-Forwarded-For"):
        # Pode conter vários IPs separados por vírgula → usar o primeiro (origem)
        return request.headers.get("X-Forwarded-For").split(",")[0].strip() # type: ignore
    return request.remote_addr



ollama = Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))

def ensure_model(model: str):
    try:
        ollama.show(model)
        print(f"[INFO] Modelo '{model}' já existe ✅", flush=True)
    except ResponseError as e:
        if e.status_code == 404:
            print(f"[WARNING] Modelo '{model}' não existe, a fazer pull...", flush=True)
            for progress in ollama.pull(model, stream=True):
                status = progress.get("status", "")
                completed = progress.get("completed")
                total = progress.get("total")

                if completed is not None and total:
                    pct = int((completed / total) * 100)
                    sys.stdout.write(f"\r[INFO] {status}... {pct}%")
                else:
                    sys.stdout.write(f"\r[INFO] {status}...")
                sys.stdout.flush()
            print("\n[INFO] Modelo pronto ✅", flush=True)
        else:
            raise
