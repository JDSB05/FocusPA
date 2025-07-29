@echo off
setlocal

REM === CONFIGURACOES ===
set ELASTIC_VERSION=8.13.0
set ELASTIC_CONTAINER=elasticsearch
set KIBANA_CONTAINER=kibana
set ELASTIC_PORT=9200

echo [INFO] A iniciar o container do Elasticsearch...

docker run -d --rm --name %ELASTIC_CONTAINER% ^
  -p %ELASTIC_PORT%:9200 -p 9300:9300 ^
  -e "discovery.type=single-node" ^
  -e "xpack.security.enabled=false" ^
  docker.elastic.co/elasticsearch/elasticsearch:%ELASTIC_VERSION%

echo [INFO] A aguardar que o Elasticsearch fique pronto...

:WAIT_LOOP
curl -s http://localhost:%ELASTIC_PORT% >nul
if errorlevel 1 (
  timeout /t 2 >nul
  goto WAIT_LOOP
)

echo [OK] Elasticsearch esta a correr em http://localhost:%ELASTIC_PORT%

REM === PERGUNTAR SE QUER INICIAR KIBANA ===
set /p startKibana=Deseja iniciar Kibana tambem? (s/n): 
if /i "%startKibana%"=="s" (
  echo [INFO] A iniciar Kibana...
  docker run -d --rm --name %KIBANA_CONTAINER% ^
    -p 5601:5601 ^
    --link %ELASTIC_CONTAINER%:elasticsearch ^
    -e ELASTICSEARCH_HOSTS=http://elasticsearch:9200 ^
    docker.elastic.co/kibana/kibana:%ELASTIC_VERSION%
  echo [OK] Kibana disponivel em http://localhost:5601
)

REM === PERGUNTAR SE QUER CRIAR O INDICE logs_security ===
set /p criarIndice=Queres criar o indice logs_security? (s/n): 
if /i "%criarIndice%"=="s" (
  echo [INFO] A criar o indice logs_security...
  curl -XPUT "http://localhost:%ELASTIC_PORT%/logs_security" -H "Content-Type: application/json" -d "{\"settings\":{\"number_of_shards\":1},\"mappings\":{\"properties\":{\"timestamp\":{\"type\":\"date\"},\"level\":{\"type\":\"keyword\"},\"message\":{\"type\":\"text\"}}}}"
  echo.
  echo [OK] Indice logs_security criado.
)

echo [OK] Setup concluido.
pause
