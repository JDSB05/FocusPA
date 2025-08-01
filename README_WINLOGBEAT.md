
# 📈 Winlogbeat + Elasticsearch + Kibana (Windows)

Este guia descreve como configurar o **Winlogbeat** no Windows para enviar eventos dos logs `<span>Application</span>`, `<span>Security</span>` e `<span>System</span>` para o **Elasticsearch**, com visualização no **Kibana**.

---

## 📁 Estrutura do ficheiro `<span>winlogbeat.yml</span>`

```
winlogbeat.event_logs:
  - name: Application
  - name: Security
  - name: System

output.elasticsearch:
  hosts: ["http://localhost:9200"]
  index: "winlog-%{+yyyy.MM.dd}"

setup.template.name: "winlog"
setup.template.pattern: "winlog-*"

setup.kibana:
  host: "http://kibana:5601"
```

---

## 🛠️ Instalação Passo a Passo

1. ⚙️ **Descarrega e extrai o Winlogbeat**[Download Winlogbeat](https://www.elastic.co/downloads/beats/winlogbeat)
2. 📌 **Coloca o conteúdo em **`<span><strong>C:\winlogbeat</strong></span>`
3. ✍️ **Edita **`<span><strong>winlogbeat.yml</strong></span>` com o conteúdo acima.
4. 🔐 **Abre o PowerShell como Administrador**
5. 🛡️ **Define RemoteSigned**
   Se quiseres, para permitir scripts locais não assinados:
   ```
   Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
6. 🧪 **Testa a configuração**
   ```
   cd C:\winlogbeat
   .\winlogbeat.exe test config -c winlogbeat.yml -e
   ```
7. 🚀 **Instala o serviço com Bypass**
   ```
   cd C:\winlogbeat
   PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-service-winlogbeat.ps1
   ```
8. ▶️ **Inicia o serviço**
   ```
   Start-Service winlogbeat
   ```
9. 🗑️ **Para desinstalar (com Bypass)**
   ```
   PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall-service-winlogbeat.ps1
   ```

---

## 📊 Aceder aos dados no Kibana

1. Abre o Kibana: [http://localhost:5601](http://localhost:5601)
2. Vai a **Discover**
3. Cria um novo **Index Pattern**:
   * Nome: `<span>winlog-*</span>`
4. Explora os logs do Windows em tempo real!

---

## 🔔 Notas

* O evento `<span>event_id: 5379</span>` representa leitura de credenciais — monitorizar este evento pode revelar acessos sensíveis.
* Podes filtrar eventos específicos no campo `<span>winlogbeat.event_logs</span>`.

---

## 🖥️ Configuração de GPU no Windows (WSL2 + Docker Desktop)

Segue o passo a passo para habilitares a GPU NVIDIA no Windows, usando WSL2 e Docker Desktop, e configurares o serviço **deepseek** para usar a GPU:

1. **Verificar versão do Windows**
   Assegura-te de que estás a usar Windows 10 (versão 21H2 ou superior) ou Windows 11, pois só nestas versões o WSL2 com GPU é suportado.
2. **Instalar e atualizar o WSL2**
   Abre o PowerShell como Administrador e executa:

   ```
   wsl --install
   wsl --update
   ```

   Aguarda que cada comando termine antes de prosseguir.
3. **Instalar uma distribuição Linux**
   Pela Microsoft Store, instala uma distro (por exemplo Ubuntu). Confirma com:

   ```
   wsl -l -v
   ```

   Deves ver a tua distro em `<span>VERSÃO 2</span>` e estado `<span>Running</span>`.
4. **Instalar driver NVIDIA com suporte a WSL2**
   Descarrega e instala o driver "NVIDIA GeForce Game Ready" (R495+), ou o equivalente Quadro, do site oficial da NVIDIA.
5. **Configurar o Docker Desktop**

   * Instala o Docker Desktop para Windows.
   * Em **Settings → General**, ativa **Use the WSL 2 based engine**.
   * Em **Settings → Resources → WSL Integration**, habilita a integração com a tua distro Linux.
6. **Validar acesso à GPU no Docker**
   Dentro da tua distro WSL (ex.: Ubuntu), executa:

   ```
   docker run --rm -it --gpus=all ubuntu nvidia-smi
   ```

   Se vires as tuas GPUs listadas, está correcto.
7. **Editar o **`<span><strong>docker-compose.yml</strong></span>`** para deepseek**
   No bloco do serviço **deepseek**, adiciona:

   ```
   services:
     deepseek:
       image: ollama/ollama:latest
       container_name: deepseek
       deploy:
         resources:
           reservations:
             devices:
               - driver: nvidia
                 count: 1
                 capabilities: [gpu]
       environment:
         - OLLAMA_FORCE_CPU=false
       ports:
         - "11434:11434"
       volumes:
         - ollama_data:/root/.ollama
       restart: always
   volumes:
     ollama_data:
   ```
8. **Reiniciar o ambiente Docker**

   ```
   docker compose down
   docker compose up -d
   ```
9. **Confirmar que deepseek usa a GPU**

   ```
   docker compose exec deepseek nvidia-smi
   ```

   Deves obter a mesma listagem de GPUs que viste anteriormente.

Assim, o Ollama no container **deepseek** irá usar a GPU para acelerar a inferência de modelos.
