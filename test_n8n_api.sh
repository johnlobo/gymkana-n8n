#!/usr/bin/env bash
# Comprueba la API de n8n llamando directamente a la IP interna del contenedor
# en la red de Docker, sin pasar por el reverse proxy ni por Authelia.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="$DIR/secrets/n8n_api_key"
CONTAINER="gymkana_n8n"

if [ ! -s "$KEY_FILE" ]; then
  echo "Error: $KEY_FILE está vacío. Pega ahí tu API key (Settings > n8n API en la UI)." >&2
  exit 1
fi

API_KEY="$(<"$KEY_FILE")"
CONTAINER_IP="$(docker inspect "$CONTAINER" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"

if [ -z "$CONTAINER_IP" ]; then
  echo "Error: no se pudo obtener la IP de $CONTAINER (¿está corriendo?)." >&2
  exit 1
fi

curl -sS -H "X-N8N-API-KEY: $API_KEY" \
  "http://${CONTAINER_IP}:5678/api/v1/workflows?limit=1" | head -c 1000
echo
