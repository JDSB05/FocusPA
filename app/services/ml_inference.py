import os
import joblib
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)

class AlphaDetector:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AlphaDetector, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        # Utilizar um modelo leve para gerar vetores densos (embeddings) consistentes
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
        raiz_projeto = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
        model_path = os.path.join(raiz_projeto, 'models', 'alpha_svm.joblib')
        print(f"[ML Inference] Tentando carregar modelo SVM de {model_path}...")
        
        if os.path.exists(model_path):
            self.svm_model = joblib.load(model_path)
            logger.info("[ML Inference] Modelo SVM carregado com sucesso.")
            print("[ML Inference] Modelo SVM carregado com sucesso.")
        else:
            self.svm_model = None
            logger.warning("[ML Inference] Modelo SVM não encontrado. Treino offline necessário.")

    def is_anomaly(self, log_text: str) -> bool:
        """
        Converte o texto do log num vetor e submete-o ao Support Vector Machine.
        Retorna True se for anomalia, False se for ruído benigno.
        """
        if not self.svm_model:
            return False # Fallback open se o modelo não existir
            
        vector = self.encoder.encode([log_text])
        prediction = self.svm_model.predict(vector)
        return prediction == 1 # Assumindo 1 = Anomalia, 0 = Normal