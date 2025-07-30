import os
import fitz  # PyMuPDF
import docx

def extract_text_from_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.pdf':
        text = ""
        with fitz.open(filepath) as doc:
            for page in doc:
                text += page.get_text()
        return text.strip()

    elif ext == '.docx':
        doc = docx.Document(filepath)
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])

    elif ext == '.txt':
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()

    else:
        raise ValueError(f"Unsupported file type: {ext}")
