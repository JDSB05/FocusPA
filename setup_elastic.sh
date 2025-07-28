
# Parâmetros
ELASTIC_VERSION="8.13.0"
ES_PORT=9200
ES_CONTAINER_NAME="elasticsearch"
KIBANA_CONTAINER_NAME="kibana"

echo "🧱 A iniciar Elasticsearch ($ELASTIC_VERSION)..."

# Lançar container Elasticsearch
docker run -d --rm --name $ES_CONTAINER_NAME \
  -p $ES_PORT:9200 -p 9300:9300 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  docker.elastic.co/elasticsearch/elasticsearch:$ELASTIC_VERSION

# Aguardar que o Elasticsearch esteja disponível
echo "⏳ A aguardar que o Elasticsearch fique pronto..."
until curl -s "http://localhost:$ES_PORT" | grep -q "cluster_name"; do
  sleep 2
done
echo "✅ Elasticsearch está a correr em http://localhost:$ES_PORT"