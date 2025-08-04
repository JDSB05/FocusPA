#!/bin/bash

# Define runtime se estiver a usar GPU (Windows com GPU)
if [[ "$USE_GPU" == "false" ]]; then
  export GPU_RUNTIME=""
  export OLLAMA_FORCE_CPU=true
  echo "→ CPU mode (macOS ou sem GPU)"
else
  export GPU_RUNTIME="nvidia"
  export OLLAMA_FORCE_CPU=false
  echo "→ GPU mode (Windows com GPU NVIDIA)"
fi

docker compose up
