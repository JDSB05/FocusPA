import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Ler os dados
df = pd.read_csv('llm_metrics_novo.csv')

# Agrupar pelos modelos
grouped = df.groupby(['model', 'light_model'])[['precision', 'completion_tokens', 'duration_seconds', 'tokens_per_second']].mean().reset_index()

grouped = grouped.rename(columns={
    'model': 'Controller Model',
    'light_model': 'Light Model'
})

# Configurar o estilo global dos gráficos
sns.set_theme(style="whitegrid")

# ---------------------------------------------------------
# Figura 1: Duration vs Throughput (Scatter Plot)
# ---------------------------------------------------------
plt.figure(figsize=(8, 5))
sns.scatterplot(data=grouped, x='duration_seconds', y='tokens_per_second', hue='Controller Model', style='Light Model', s=150)
plt.xlabel('Duration (seconds)')
plt.ylabel('Average Throughput (tokens/second)')
plt.title('Latency vs. Throughput by Model Pairing')
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.savefig('fig_throughput_latency.pdf')
plt.close()

# ---------------------------------------------------------
# Figura 2: Completion Tokens (Bar Chart)
# ---------------------------------------------------------
plt.figure(figsize=(8, 5))
sns.barplot(data=grouped, x='Controller Model', y='completion_tokens', hue='Light Model')
plt.xlabel('Controller Model')
plt.ylabel('Average Completion Tokens')
plt.title('Verbosity: Completion Tokens by Model Pairing')
plt.legend(title='Light Model', bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.savefig('fig_completion_tokens.pdf')
plt.close()

# ---------------------------------------------------------
# Figura 3: Precision (Bar Chart)
# ---------------------------------------------------------
plt.figure(figsize=(8, 5))
sns.barplot(data=grouped, x='Controller Model', y='precision', hue='Light Model')
plt.xlabel('Controller Model')
plt.ylabel('Average Precision (%)')
plt.title('Anomaly Detection Precision by Model Pairing')
plt.legend(title='Light Model', bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.savefig('fig_precision.pdf')
plt.close()

print("As três figuras foram geradas com sucesso!")