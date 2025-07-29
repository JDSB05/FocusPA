from flask import Flask, request, jsonify
from elasticsearch import Elasticsearch
from datetime import datetime

app = Flask(__name__)
es = Elasticsearch("http://localhost:9200")

@app.route('/logs', methods=['POST'])
def receber_log():
    log = request.json
    if log is None:
        return jsonify({"error": "Invalid or missing JSON in request"}), 400
    log['timestamp'] = datetime.utcnow().isoformat()
    res = es.index(index="logs_security", document=log)
    return jsonify(res['result'])

@app.route('/search', methods=['GET'])
def procurar_logs():
    termo = request.args.get("q", "")
    res = es.search(index="logs_security", body={
        "query": {"match": {"message": termo}},
        "size": 10
    })
    hits = [hit['_source'] for hit in res['hits']['hits']]
    return jsonify(hits)

if __name__ == '__main__':
    app.run(debug=True)
