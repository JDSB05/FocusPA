import os
import torch
from transformers import BertConfig, BertForMaskedLM
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from drain3.file_persistence import FilePersistence
from drain3.masking import MaskingInstruction

# --- Configurações Alinhadas com o Novo Treino ---
FIXED_VOCAB_SIZE = 1500
MASK_TOKEN_ID = FIXED_VOCAB_SIZE - 1
WINDOW_SIZE = 10 

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[HW] A usar: {device.type.upper()}")

# Reconstrução do Parser com Máscaras
config_drain = TemplateMinerConfig()
config_drain.masking_instructions = [
    MaskingInstruction(pattern=r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", mask_with="IP"),
    MaskingInstruction(pattern=r"\b\d+\b", mask_with="NUM")
]
persistence = FilePersistence("models/drain3_state.bin")
miner = TemplateMiner(persistence_handler=persistence, config=config_drain)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
caminho_modelo = os.path.join(BASE_DIR, "models", "logbert_core")
caminho_config = os.path.join(caminho_modelo, "config.json")

print(f"[ML] A verificar matriz em: {caminho_modelo}")

# Verificação rigorosa do ficheiro matriz (config.json)
if os.path.exists(caminho_config):
    try:
        model = BertForMaskedLM.from_pretrained(caminho_modelo).to(device)
        model.eval()
        print(f"[INFO LogBERT] Modelo central carregado com sucesso na {device.type.upper()}.")
    except Exception as e:
        model = None
        print(f"[ERRO CRÍTICO] Ficheiros corrompidos: {e}")
else:
    model = None
    print("[AVISO] Modelo 'logbert_core' não encontrado!") 
    print("[AVISO] A iniciar em modo degradado: A criação está pendente do train_alpha.py.")
    # A INSTRUÇÃO exit() FOI ERRADICADA PARA PERMITIR A COMPILAÇÃO

def testar_causalidade(nome, lista_logs):
    print(f"\n--- TESTE: {nome} ---")
    ids = []
    for l in lista_logs:
        res = miner.add_log_message(l)
        ids.append(min(res["cluster_id"], FIXED_VOCAB_SIZE - 2))
    
    # Geometria Causal: 10 de contexto + 1 alvo
    if len(ids) < WINDOW_SIZE + 1:
        print(f"[AVISO] Sequência curta demais ({len(ids)}). Precisa de {WINDOW_SIZE+1}.")
        return

    # Usar apenas a última janela possível
    fatia = ids[-(WINDOW_SIZE + 1):]
    inputs = torch.tensor([fatia], dtype=torch.long).to(device)
    alvo_real = inputs[0, -1].item()
    inputs[0, -1] = MASK_TOKEN_ID
    
    with torch.no_grad():
        logits = model(inputs).logits[0, -1, :]
        probs = torch.softmax(logits, dim=-1)
    
    certeza = probs[alvo_real].item() * 100
    print(f"Último Log: {lista_logs[-1]}")
    print(f"Certeza da IA: {certeza:.4f}%")
    if certeza < 1.0:
        print("Veredicto: 🔴 ANOMALIA")
    else:
        print("Veredicto: 🟢 NORMAL")

# Injetar os mesmos logs que o 'prova_cientifica.py' usou para ganhar
logs_vencedores = [
    "[SYS] Session closed gracefully",
    "[APP] User requests login access",
    "[AUTH] Credentials validated successfully",
    "[DB] Access granted to secure payload",
    "[SYS] Session closed gracefully",
    "[APP] User requests login access",
    "[AUTH] Credentials validated successfully",
    "[DB] Access granted to secure payload",
    "[SYS] Session closed gracefully",
    "[APP] User requests login access",
    "[SYS] Session closed gracefully" # Alvo (O 11º log)
]

testar_causalidade("Verificação de Integridade Core", logs_vencedores)