from pathlib import Path


def extract_text(file_storage) -> tuple[str, bytes]:
    filename = file_storage.filename or "cv.txt"
    data = file_storage.read()
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        text = _pdf_text(data)
    else:
        text = data.decode("utf-8", errors="ignore")
    return text.strip(), data


def _pdf_text(data: bytes) -> str:
    from io import BytesIO

    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""
