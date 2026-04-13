import json
import numpy as np
from sklearn.cluster import KMeans
from sklearn.svm import SVC
from sentence_transformers import SentenceTransformer
import joblib
import os
import sys

# Adicionar caminho para importar funções do vosso repositório
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.controllers.rag_controller import ask_llm
LLM_MODEL =os.environ.get('LLM_MODEL', 'deepseek-coder-v2')

def extract_historical_logs():
    """
    Lista de logs para treino que inclui comportamentos normais e anomalias críticas.
    Isto garante que o SVM tenha exemplos de ambas as classes para aprender.
    """
    return [
        # Exemplos de tráfego BENIGNO (Normal)
        "User Administrator logged in successfully",
        "System update completed successfully",
        "Daily backup task finished",
        "Connection established to database server 10.0.0.5",
        "Routine health check: all services operational",
        
        # Exemplos de ANOMALIAS (Ataques ou Falhas Críticas)
        "CRITICAL: Kernel panic - not syncing: Fatal exception",
        "SECURITY ALERT: Unauthorized access attempt to /etc/shadow",
        "SYN flood attack detected from multiple external IPs",
        "Buffer overflow attempt detected in service HTTP",
        "Failed login attempt for user ROOT from IP 192.168.1.5",
        "Multiple failed connection attempts to port 22 (SSH Brute Force)",
        "Unauthorized file deletion detected in /var/www/html",
        "Malicious script execution blocked by system integrity check"
    ]

def llm_label_centroid(log_text):
    # Prompt muito mais agressivo e claro para modelos pequenos
    prompt = f"""
Avalia o seguinte registo de sistema (log).
Se descreve sucesso, rotina ou operações normais, escreve APENAS: NORMAL
Se descreve um ataque, falha crítica, acesso negado ou erro, escreve APENAS: ANOMALY

Log: {log_text}
Resposta:"""

    # Assumindo que o teu ask_llm está a usar o modelo 'qwen2.5:1.5b'
    response = ask_llm(prompt, model=LLM_MODEL).strip().upper()
    
    # DEBUG: Imprimir a resposta exata do LLM para vermos o que ele está a pensar
    print(f"  -> [RAW LLM] O modelo respondeu: {response}")

    # 1. Tentar ler a resposta do LLM
    if "ANOMALY" in response:
        return 1
    elif "NORMAL" in response:
        return 0
        
    # 2. REDE DE SEGURANÇA (Fallback): Se o LLM pequeno se confundir e escrever 
    # texto sem as palavras-chave, o Python usa uma regra de dicionário 
    # apenas para garantir que o treino avança.
    palavras_perigo = ["FAIL", "ATTACK", "CRITICAL", "UNAUTHORIZED", "OVERFLOW", "MALICIOUS", "PANIC", "ALERT"]
    if any(p in log_text.upper() for p in palavras_perigo):
        print("  -> [FALLBACK] LLM falhou a formatação. Forçado para Anomalia por palavra-chave.")
        return 1
        
    return 0

def main():
    print("1. Extraindo histórico de logs...")
    logs = extract_historical_logs()
    
    print("2. Gerando Embeddings Vetoriais...")
    encoder = SentenceTransformer('all-MiniLM-L6-v2')
    vectors = np.array(encoder.encode(logs))
    
    print("3. Executando Clustering K-Means...")
    k = min(15, len(logs)) # Número de clusters (otimizado teoricamente no artigo)
    kmeans = KMeans(n_clusters=k, random_state=42)
    kmeans.fit(vectors)
    
    labels = np.zeros(len(logs))
    
    print("4. Anotação Ativa via LLM (Few-Shot)...")
    for i in range(k):
        # Encontrar o índice do log mais próximo ao centro do cluster (centroid)
        cluster_indices = np.where(kmeans.labels_ == i)
        centroid_vector = kmeans.cluster_centers_[i]
        
        # O cálculo de distância
        distances = np.linalg.norm(vectors[cluster_indices] - centroid_vector, axis=1)
        closest_idx = cluster_indices[np.argmin(distances)].item()
        
        # O LLM avalia a amostra representativa
        is_anomaly = llm_label_centroid(logs[closest_idx])
        print(f"Cluster {i} avaliado como: {'Anomalia' if is_anomaly else 'Normal'}")
        
        # Propagação: Todo o cluster recebe o rótulo do seu centroide
        labels[cluster_indices] = is_anomaly
        
    print("5. Treinando classificador SVM Rápido...")
    svm_model = SVC(kernel='linear', probability=True)
    svm_model.fit(vectors, labels)
    
    # Garantir que o diretório existe
    os.makedirs('./models', exist_ok=True)
    model_path = './models/alpha_svm.joblib'
    joblib.dump(svm_model, model_path)
    print(f"6. Pipeline concluído. SVM guardado em {model_path}.")
    testar_modelo()

from app.services.ml_inference import AlphaDetector

def testar_modelo():
    detector = AlphaDetector()
    
    # Lista de logs para teste
    logs_teste = [
        "User jdoe logged in from 192.168.1.50",          # Esperado: Normal (se treinado com logs benignos)
        "ATTACK: SQL Injection attempt detected on /login", # Esperado: Anomalia
        "System update completed successfully",            # Esperado: Normal
        "FATAL ERROR: Unauthorized memory access at 0x4F"  # Esperado: Anomalia
    ]
    
    print("--- Teste de Inferência ALPHA ---")
    for log in logs_teste:
        resultado = detector.is_anomaly(log)
        status = "ANOMALIA" if resultado else "NORMAL"
        print(f"Log: {log} -> Classificação: {status}")

if __name__ == "__main__":
    testar_modelo()

if __name__ == "__main__":
    main()