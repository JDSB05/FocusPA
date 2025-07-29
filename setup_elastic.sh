#!/bin/bash

# === CONFIGURACOES ===
ELASTIC_VERSION="8.13.0"
ELASTIC_CONTAINER="elasticsearch"
KIBANA_CONTAINER="kibana"
ELASTIC_PORT=9200

echo "[INFO] A iniciar o container do Elasticsearch..."

docker run -d --rm --name $ELASTIC_CONTAINER \
  -p $ELASTIC_PORT:9200 -p 9300:9300 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  docker.elastic.co/elasticsearch/elasticsearch:$ELASTIC_VERSION

echo "[INFO] A aguardar que o Elasticsearch fique pronto..."

until curl -s http://localhost:$ELASTIC_PORT >/dev/null; do
  sleep 2
done

echo "[OK] Elasticsearch está a correr em http://localhost:$ELASTIC_PORT"

# === PERGUNTAR SE QUER INICIAR KIBANA ===
read -p "Deseja iniciar Kibana também? (s/n): " startKibana
if [[ "$startKibana" =~ ^[sS]$ ]]; then
  echo "[INFO] A iniciar Kibana..."
  docker run -d --rm --name $KIBANA_CONTAINER \
    -p 5601:5601 \
    --link $ELASTIC_CONTAINER:elasticsearch \
    -e ELASTICSEARCH_HOSTS=http://elasticsearch:9200 \
    docker.elastic.co/kibana/kibana:$ELASTIC_VERSION
  echo "[OK] Kibana disponível em http://localhost:5601"
fi

# === PERGUNTAR SE QUER CRIAR O INDICE logs_security ===
read -p "Queres criar o índice logs_security? (s/n): " criarIndice
if [[ "$criarIndice" =~ ^[sS]$ ]]; then
  echo "[INFO] A criar o índice logs_security..."
  curl -XPUT "http://localhost:$ELASTIC_PORT/logs_security" \
    -H "Content-Type: application/json" \
    -d '{"settings":{"number_of_shards":1},"mappings":{"properties":{"timestamp":{"type":"date"},"level":{"type":"keyword"},"message":{"type":"text"}}}}'
  echo
  echo "[OK] Índice logs_security criado."
fi

echo "[OK] Setup concluído."