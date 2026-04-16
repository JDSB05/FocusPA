import os
import pandas as pd
import torch
import random
import shutil
from torch.utils.data import Dataset, DataLoader
import torch.nn as nn

# Importación directa de la arquitectura DeepLog existente en tu repositorio
from app.LogBERT.logdeep.models.lstm import Deeplog
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from drain3.file_persistence import FilePersistence
from drain3.masking import MaskingInstruction

# --- Umbrales Dimensionales ---
FIXED_VOCAB_SIZE = 1500 
WINDOW_SIZE = 10 

def extract_cert_logs(file_path):
    print(f"[INFO] Analizando la densidad poblacional en el archivo: {file_path}...")
    
    if not os.path.exists(file_path):
        print(f"[ERROR CRÍTICO] El archivo no fue encontrado: {file_path}")
        return []
        
    df = pd.read_csv(file_path)
    
    top_users = df['user'].value_counts().head(10).index.tolist()
    if not top_users:
        return []
        
    target_user = random.choice(top_users)
    user_df = df[df['user'] == target_user].sort_values(by='date')
    
    print(f"[INFO] Objetivo Seleccionado: {target_user} | Total de Eventos Brutos: {user_df.shape}")
    user_df['full_event'] = user_df['activity'] + " on " + user_df['pc']
    
    eventos_brutos = user_df['full_event'].tolist()
    
    # --- O FILTRO DE RUÍDO (Deduplicação Causal) ---
    eventos_limpos = []
    for evento in eventos_brutos:
        # Só guarda o evento se for diferente do imediatamente anterior
        if not eventos_limpos or eventos_limpos[-1] != evento:
            eventos_limpos.append(evento)
            
    print(f"[INFO] Total de Eventos após limpeza do caos humano: {len(eventos_limpos)}")
    
    return eventos_limpos

class LstmSequenceDataset(Dataset):
    def __init__(self, sequence, window_size=WINDOW_SIZE):
        self.inputs = []
        self.targets = []
        # Geometría Causal Autorregresiva: No hay máscaras. El pasado predice de forma estricta el futuro.
        for i in range(len(sequence) - window_size):
            self.inputs.append(sequence[i : i + window_size])
            self.targets.append(sequence[i + window_size])
            
    def __len__(self):
        return len(self.inputs)
        
    def __getitem__(self, idx):
        return torch.tensor(self.inputs[idx], dtype=torch.long), torch.tensor(self.targets[idx], dtype=torch.long)

def main():
    csv_path = os.path.join(os.path.dirname(__file__), 'logon.csv')
    logs = extract_cert_logs(csv_path)
    if not logs: return
    
    print("[INFO] Cargando motor de Abstracción Sintáctica (Drain3)...")
    config = TemplateMinerConfig()
    
    # Tolerancia restrictiva mantenida para evitar colapsos de abstracción
    config.drain_sim_th = 0.85 
    config.masking_instructions = [
        MaskingInstruction(pattern=r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", mask_with="IP"),
        MaskingInstruction(pattern=r"\b\d+\b", mask_with="NUM")
    ]
    
    os.makedirs("models", exist_ok=True)
    persistence = FilePersistence("models/drain3_state.bin")
    miner = TemplateMiner(persistence_handler=persistence, config=config)
    
    parsed_ids = []
    for log in logs:
        resultado = miner.add_log_message(log)
        cid = min(resultado["cluster_id"], FIXED_VOCAB_SIZE - 2)
        parsed_ids.append(cid)
        
    dataset = LstmSequenceDataset(parsed_ids)
    dataloader = DataLoader(dataset, batch_size=32, shuffle=True)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[HW] Procesador activo: {device.type.upper()}")
    
    # --- Instanciación del Motor LSTM (DeepLog) ---
    model = Deeplog(
        input_size=128, 
        hidden_size=128, 
        num_layers=2, 
        vocab_size=FIXED_VOCAB_SIZE, 
        embedding_dim=128
    ).to(device)
    
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()
    
    print("[INFO] Iniciando Entrenamiento Autorregresivo Integral...")
    model.train()
    
    for epoch in range(30):
        total_loss = 0
        for inputs, targets in dataloader:
            inputs, targets = inputs.to(device), targets.to(device)
            
            optimizer.zero_grad()
            
            # Deeplog espera una lista de tensores encapsulada
            outputs = model(features=[inputs], device=device)
            
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            
        print(f"  -> Época {epoch+1} | Error de Predicción (Loss): {total_loss/len(dataloader):.4f}")
        
    # --- Serialización Atómica Nativa (PyTorch) ---
    dir_produccion = "models/logbert_core"
    dir_sombra = "models/logbert_core_temp"
    
    print(f"[INFO] Grabando tensores en directorio aislado '{dir_sombra}'...")
    os.makedirs(dir_sombra, exist_ok=True)
    
    # Transición forzosa: Guardamos el state_dict binario directamente en formato .pth
    ruta_modelo_sombra = os.path.join(dir_sombra, "lstm_model.pth")
    torch.save(model.state_dict(), ruta_modelo_sombra)
    
    print("[INFO] Promoviendo directorio sombra a producción...")
    if os.path.exists(dir_produccion):
        try:
            shutil.rmtree(dir_produccion)
        except Exception as e:
            print(f"[AVISO] No se pudo borrar el modelo antiguo instantáneamente: {e}")
            
    try:
        os.rename(dir_sombra, dir_produccion)
        print(f"[ÉXITO] Cerebro LSTM grabado en '{dir_produccion}/lstm_model.pth'.")
    except FileExistsError:
        shutil.copytree(dir_sombra, dir_produccion, dirs_exist_ok=True)
        shutil.rmtree(dir_sombra)
        print(f"[ÉXITO] Cerebro LSTM inyectado por copia en '{dir_produccion}/lstm_model.pth'.")

if __name__ == "__main__":
    main()