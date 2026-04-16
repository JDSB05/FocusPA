import os
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import BertConfig, BertForMaskedLM
from peft import LoraConfig, get_peft_model, PeftModel
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from drain3.file_persistence import FilePersistence

# 1. O Cenário Determinístico (Causalidade Perfeita)
# Uma rotina de 4 passos que se repete infinitamente: Pedido -> Autenticação -> Acesso -> Fecho.
rotina_base = [
    "[APP] User requests login access",
    "[AUTH] Credentials validated successfully",
    "[DB] Access granted to secure payload",
    "[SYS] Session closed gracefully"
]
dataset_sintetico = rotina_base * 500  # 2000 logs perfeitamente sequenciais

FIXED_VOCAB_SIZE = 50
MASK_TOKEN_ID = FIXED_VOCAB_SIZE - 1
WINDOW_SIZE = 4

# 2. Treino de Isolamento
print("[INFO] A gerar Cérebro Sintático de Controlo...")
os.makedirs("models/control", exist_ok=True)
miner = TemplateMiner(persistence_handler=FilePersistence("models/control/drain3.bin"), config=TemplateMinerConfig())

ids_sintaticos = []
for log in dataset_sintetico:
    cid = miner.add_log_message(log)["cluster_id"]
    ids_sintaticos.append(min(cid, FIXED_VOCAB_SIZE - 2))

class MatrizDataset(Dataset):
    def __init__(self, data):
        self.data = data
    def __len__(self):
        return len(self.data) - WINDOW_SIZE
    def __getitem__(self, idx):
        return torch.tensor(self.data[idx : idx + WINDOW_SIZE + 1], dtype=torch.long)

def mask_tokens(batch):
    inputs = batch.clone()
    # Inicializa a matriz de alvos com -100 (Silenciador de Gradiente do PyTorch)
    labels = torch.full_like(batch, -100)
    
    # Copia apenas o evento real para a última coluna da matriz de avaliação
    labels[:, -1] = batch[:, -1].clone()
    
    # Oculta o último evento na matriz de entrada com o Token de Máscara
    inputs[:, -1] = MASK_TOKEN_ID
    
    return inputs, labels

loader = DataLoader(MatrizDataset(ids_sintaticos), batch_size=16, shuffle=True)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[HW] Processador ativo: {device.type.upper()}")

bert_config = BertConfig(vocab_size=FIXED_VOCAB_SIZE, hidden_size=64, num_hidden_layers=2, num_attention_heads=2, intermediate_size=128)
base_model = BertForMaskedLM(bert_config)
# O micro-modelo é carregado na íntegra. Todos os neurónios vão aprender.
model = base_model.to(device)
optimizer = torch.optim.AdamW(model.parameters(), lr=0.001) # Reduzimos o LR para o padrão seguro

print("[INFO] A injetar rotina determinística no LogBP-LORA (10 Épocas)...")
model.train()
for epoch in range(10):
    total_loss = 0
    for batch in loader:
        inputs, labels = mask_tokens(batch)
        inputs, labels = inputs.to(device), labels.to(device)
        optimizer.zero_grad()
        loss = model(inputs, labels=labels).loss
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    print(f"  -> Época {epoch+1} | Loss: {total_loss/len(loader):.4f}")

model.eval()

# 3. Interrogatório de Prova
def avaliar(sequencia, nome):
    print(f"\n--- AVALIAÇÃO: {nome} ---")
    seq_ids = [min(miner.add_log_message(l)["cluster_id"], FIXED_VOCAB_SIZE - 2) for l in sequencia]
    inputs = torch.tensor([seq_ids], dtype=torch.long).to(device)
    alvo = inputs[0, -1].item()
    inputs[0, -1] = MASK_TOKEN_ID
    with torch.no_grad():
        probs = torch.softmax(model(inputs).logits[0, -1, :], dim=-1)
    
    certeza = probs[alvo].item() * 100
    print(f"Log Foco: {sequencia[-1]}")
    print(f"Certeza da IA: {certeza:.2f}%")

# Teste 1: A IA sabe o que vem a seguir ao "Acesso"?
# Fornecemos o contexto exato de 4 frames, mascarando o 5º frame
avaliar([
    "[SYS] Session closed gracefully",           # Frame 1 (A rotina anterior a reiniciar)
    "[APP] User requests login access",          # Frame 2
    "[AUTH] Credentials validated successfully", # Frame 3
    "[DB] Access granted to secure payload",     # Frame 4
    "[SYS] Session closed gracefully"            # Frame 5 (Alvo a prever)
], "Rotina Normal")

# Teste 2: Após o "Acesso", injetamos o ataque
avaliar([
    "[SYS] Session closed gracefully",           # Frame 1
    "[APP] User requests login access",          # Frame 2
    "[AUTH] Credentials validated successfully", # Frame 3
    "[DB] Access granted to secure payload",     # Frame 4
    "[CRITICAL] Unauthorized root escalation attempt" # Frame 5 (Anomalia)
], "Injeção de Anomalia")