#!/usr/bin/env bash
set -e

# Inicia o servidor Ollama em background
ollama serve &
PID=$!

# Dá tempo ao servidor para ficar pronto
echo "Aguarda 5 segundos para o Ollama iniciar..."
sleep 5

# Só faz pull se o modelo ainda não existir na pasta persistida
if ! ollama ls | grep -q '^deepseek-coder$'; then
  echo "Modelo deepseek-coder não encontrado. A descarregar..."
  ollama pull deepseek-coder
  echo "Modelo deepseek-coder descarregado com sucesso."
else
  echo "Modelo deepseek-coder já está presente — a ignorar pull."
fi

# Aguarda o processo principal (serve) terminar
wait $PID
