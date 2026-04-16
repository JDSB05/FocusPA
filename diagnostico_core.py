import os
import torch
import torch.nn as nn
from app.LogBERT.logdeep.models.lstm import Deeplog
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from drain3.file_persistence import FilePersistence
from drain3.masking import MaskingInstruction

FIXED_VOCAB_SIZE = 1500
WINDOW_SIZE = 10 

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

config_drain = TemplateMinerConfig()
config_drain.drain_sim_th = 0.85 # Mantenemos el bloqueo estricto contra la fusión
config_drain.masking_instructions = [
    MaskingInstruction(pattern=r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", mask_with="IP"),
    MaskingInstruction(pattern=r"\b\d+\b", mask_with="NUM")
]
persistence = FilePersistence("models/drain3_state.bin")
miner = TemplateMiner(persistence_handler=persistence, config=config_drain)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# La nueva ruta apunta directamente al archivo binario nativo
caminho_modelo = os.path.join(BASE_DIR, "models", "logbert_core", "lstm_model.pth")

# Instanciación de la topología LSTM (DeepLog)
model = Deeplog(
    input_size=128, 
    hidden_size=128, 
    num_layers=2, 
    vocab_size=FIXED_VOCAB_SIZE, 
    embedding_dim=128
).to(device)

if os.path.exists(caminho_modelo):
    # Carga atómica de los pesos tensoriales
    model.load_state_dict(torch.load(caminho_modelo, map_location=device))
    model.eval()
    print(f"[INFO] Cerebro LSTM cargado desde: {caminho_modelo}")
else:
    print("[ERROR CRÍTICO] Modelo no encontrado. Ejecuta 'train_alpha.py' primero.")
    exit()

def testar_causalidade(nombre, lista_logs):
    print(f"\n--- EVALUACIÓN: {nombre} ---")
    ids = []
    for l in lista_logs:
        cluster = miner.match(l)
        if cluster is None:
            cid = FIXED_VOCAB_SIZE - 2 
        else:
            cid = min(cluster.cluster_id, FIXED_VOCAB_SIZE - 2)
        ids.append(cid)
    
    if len(ids) < WINDOW_SIZE + 1:
        print("[AVISO] Secuencia demasiado corta.")
        return

    # Aislamiento matemático: Tomamos los 10 anteriores como contexto, y aislamos el objetivo
    fatia = ids[-(WINDOW_SIZE + 1):-1] 
    alvo_real = ids[-1] 
    
    inputs = torch.tensor([fatia], dtype=torch.long).to(device)
    
    with torch.no_grad():
        # La LSTM predice el siguiente paso basándose en la evolución temporal de la secuencia
        outputs = model(features=[inputs], device=device)
        probs = torch.softmax(outputs, dim=-1)
    
    certeza = probs[0, alvo_real].item() * 100
    print(f"Log Bajo Escrutinio: {lista_logs[-1]}")
    
    cluster_alvo = miner.drain.id_to_cluster.get(alvo_real)
    template_str = cluster_alvo.get_template() if cluster_alvo else "ALERTA: SINTAXIS ALIENÍGENA (OOV)"
    print(f"Template Drain3   : {template_str}")
    
    print(f"Certeza Matemática: {certeza:.4f}%")
    if certeza < 1.0 or not cluster_alvo:
        print("Veredicto         : 🔴 ANOMALÍA GRAVE")
    else:
        print("Veredicto         : 🟢 NORMAL")

# A Verdadeira Prova de Fogo Temporal (Alvo é o erro)
ataque_estado_logico = [
    "Logon on PC-1234", "Logoff on PC-1234", 
    "Logon on PC-1234", "Logoff on PC-1234",
    "Logon on PC-1234", "Logoff on PC-1234", 
    "Logon on PC-1234", "Logoff on PC-1234",   
    "Logon on PC-1234", "Logoff on PC-1234", # Contexto termina legalmente num Logoff
    "Logoff on PC-1234" # ALVO A PREVER: Outro Logoff (Fisicamente impossível)
]

testar_causalidade("Violación de Estado Lógico (Teste Corrigido)", ataque_estado_logico)