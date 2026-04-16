import os
import torch
from transformers import BertConfig, BertForMaskedLM
from peft import PeftModel
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from drain3.file_persistence import FilePersistence

# --- 1. Configurações e Carregamento Rigoroso ---
FIXED_VOCAB_SIZE = 1500
MASK_TOKEN_ID = FIXED_VOCAB_SIZE - 1
WINDOW_SIZE = 10

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[SISTEMA] A usar processador: {device.type.upper()}")

persistence = FilePersistence("models/drain3_state.bin")
miner = TemplateMiner(persistence_handler=persistence, config=TemplateMinerConfig())

bert_config = BertConfig(
    vocab_size=FIXED_VOCAB_SIZE, hidden_size=128, num_hidden_layers=2,
    num_attention_heads=2, intermediate_size=256, max_position_embeddings=512
)

try:
    base_model = BertForMaskedLM(bert_config)
    model = PeftModel.from_pretrained(base_model, "models/logbert_lora").to(device)
    model.eval()
except Exception as e:
    print(f"[ERRO] Falha ao carregar a matriz LoRA. Garantiste o treino? Erro: {e}")
    exit()

def interrogar_modelo(descricao_teste, sequencia_logs):
    """
    Injeta uma fita de cinema (janela de 10 logs), oculta o último e obriga 
    o modelo a revelar a probabilidade estatística do evento real.
    """
    print(f"\n{'='*60}\n[CENÁRIO] {descricao_teste}")
    
    ids_sintaticos = []
    esqueleto = ""
    for log in sequencia_logs:
        resultado = miner.add_log_message(log)
        ids_sintaticos.append(min(resultado["cluster_id"], FIXED_VOCAB_SIZE - 2))
        esqueleto = resultado["template_mined"] # Guardamos o esqueleto imediatamente
        
    # Colocar no formato Tensor para a GPU
    inputs = torch.tensor([ids_sintaticos], dtype=torch.long).to(device)
    
    # Isolar o log que queremos avaliar (o último da linha temporal)
    id_alvo_real = inputs[0, -1].item()
    
    # Mascarar o último log (Esconder a verdade da IA)
    inputs[0, -1] = MASK_TOKEN_ID
    
    with torch.no_grad():
        outputs = model(inputs)
        # Extrair a distribuição de probabilidade para a posição mascarada
        probabilidades = torch.softmax(outputs.logits[0, -1, :], dim=-1)
        # Qual foi a probabilidade atribuída ao log que efetivamente aconteceu?
        prob_evento = probabilidades[id_alvo_real].item()
        
    # Tradução para Humanos
    log_avaliado = sequencia_logs[-1]
    #esqueleto = miner.get_cluster(id_alvo_real).get_template()
    
    print(f"Log Sob Escrutínio : {log_avaliado}")
    print(f"Esqueleto (Drain3) : {esqueleto}")
    print(f"Previsão Matemática: {prob_evento * 100:.6f} % de probabilidade desta ação ocorrer agora.")
    
    # O Limiar de 1% (0.01)
    if prob_evento < 0.01:
        print("Veredicto          : 🔴 ANOMALIA GRAVE (Ação topologicamente irracional)")
    else:
        print("Veredicto          : 🟢 EVENTO NORMAL (Ação rotineira validada)")

# --- 2. Simulação de Testes Operacionais ---

import ssl
import urllib.request
import pandas as pd

print("\n[INFO] A extrair amostra da realidade do servidor...")
url_csv = "https://raw.githubusercontent.com/logpai/loghub/master/Windows/Windows_2k.log_structured.csv"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
req = urllib.request.urlopen(url_csv, context=ctx)
df = pd.read_csv(req)
logs_reais = df['Content'].dropna().tolist()

# Teste A: 10 logs REAIS seguidos que o servidor gerou no minuto 1
rotina_estrita = logs_reais[0:10]
interrogar_modelo("Rotina Real do Servidor (Extraída do Dataset)", rotina_estrita)

# Teste B: 9 logs REAIS seguidos + 1 evento impossível/ataque
ataque_lateral = logs_reais[0:9]
ataque_lateral.append("Um executavel não assinado iniciou ligacao externa no porto 4444") 
interrogar_modelo("Ataque de Comando e Controlo (C2)", ataque_lateral)