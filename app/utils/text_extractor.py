import textract
import os

def extract_text_from_file(filepath):
    try:
        return textract.process(filepath).decode("utf-8")
    except Exception as e:
        return f"[Erro ao extrair texto: {e}]"