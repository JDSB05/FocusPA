import json
import os
from pathlib import Path
from typing import Dict, Any

# podes sobrepor o caminho via env var ANOMALY_POLICY_PATH
_POLICY_PATH = Path(os.getenv("ANOMALY_POLICY_PATH", "app/policy.json")).resolve()

_cache = {"mtime": None, "data": {"admins": [], "dirs": [], "custom_prompt": ""}}

def load_policy(force: bool = False) -> Dict[str, Any]:
    """Carrega a policy de um ficheiro JSON (com cache por mtime)."""
    try:
        mtime = _POLICY_PATH.stat().st_mtime
    except FileNotFoundError:
        return _cache["data"]  # default vazio

    if force or _cache["mtime"] != mtime:
        with _POLICY_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # defaults mínimos
        data.setdefault("admins", [])
        data.setdefault("dirs", [])
        data.setdefault("custom_prompt", "")
        _cache["mtime"] = mtime
        _cache["data"] = data
    return _cache["data"]


def build_policy_context_for_prompt() -> str:
    """Devolve um bloco de texto para meter no prompt do LLM (apenas contexto)."""
    p = load_policy()
    admins = ", ".join(p.get("admins") or []) or "—"
    # damos também a versão JSON para o LLM conseguir fazer match mais fiável
    dirs_json = json.dumps(p.get("dirs") or [], ensure_ascii=False)
    extra = p.get("custom_prompt") or ""
    return f"""
Contexto de permissões (apenas referência; não vinculativo):
- Admins (acesso generalista): {admins}
- Diretórios sensíveis (JSON): {dirs_json}
- Notas extra: {extra}
""".strip()
