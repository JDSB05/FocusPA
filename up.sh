#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "uso: $0 [cpu|nvidia|amd]"
  exit 1
}

PROFILE="${1:-cpu}"
case "$PROFILE" in
  cpu|nvidia|amd) ;;
  *) usage ;;
esac

echo "→ a iniciar com perfil: $PROFILE"
# Sobe infra-base + perfil escolhido
docker compose --profile "$PROFILE" up -d
docker compose ps