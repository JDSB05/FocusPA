import os
import fitz  # PyMuPDF
import docx

def clean_text(text):
    # Remove NULL chars e normaliza
    return text.replace("\x00", "").strip()

def extract_text_from_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.pdf':
        text = ""
        with fitz.open(filepath) as doc:
            for page in doc:
                text += page.get_text()
        return clean_text(text)

    elif ext == '.docx':
        doc = docx.Document(filepath)
        return clean_text("\n".join([p.text for p in doc.paragraphs if p.text.strip()]))

    elif ext == '.txt':
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return clean_text(f.read())

    else:
        raise ValueError(f"Unsupported file type: {ext}")
