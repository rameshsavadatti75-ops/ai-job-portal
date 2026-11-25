import os
import pdfplumber
from docx import Document


def extract_text_from_file(filepath):
    if not filepath or not os.path.exists(filepath):
        return ""

    ext = os.path.splitext(filepath)[1].lower()
    chunks = []

    if ext == ".pdf":
        try:
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        chunks.append(page_text)
        except Exception as exc:
            print(f"PDF parsing error: {exc}")

    elif ext == ".docx":
        try:
            doc = Document(filepath)
            for para in doc.paragraphs:
                if para.text and para.text.strip():
                    chunks.append(para.text.strip())
            for table in doc.tables:
                for row in table.rows:
                    row_vals = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
                    if row_vals:
                        chunks.append(" | ".join(row_vals))
        except Exception as exc:
            print(f"DOCX parsing error: {exc}")

    return "\n".join(chunks)