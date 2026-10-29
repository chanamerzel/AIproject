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


_uri_cache: dict[tuple, list[str]] = {}


def enrich_stored_text(stored: str, cv_path: str | None) -> str:
    """Add click-target URLs from a saved PDF when the visible text only says GitHub or LinkedIn."""
    text = stored or ""
    path = Path(cv_path) if cv_path else None
    if path is None or path.suffix.lower() != ".pdf" or not path.is_file():
        return text
    return _append_links(text, _cached_pdf_uris(path))


def _cached_pdf_uris(path: Path) -> list[str]:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    cached = _uri_cache.get(key)
    if cached is not None:
        return cached
    uris = _pdf_uris(path.read_bytes())
    if len(_uri_cache) > 32:
        _uri_cache.clear()
    _uri_cache[key] = uris
    return uris


def _pdf_text(data: bytes) -> str:
    from io import BytesIO

    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        visible = "\n".join(page.extract_text() or "" for page in reader.pages)
        return _append_links(visible, _uris_from_reader(reader))
    except Exception:
        return ""


def _pdf_uris(data: bytes) -> list[str]:
    from io import BytesIO

    try:
        from pypdf import PdfReader

        return _uris_from_reader(PdfReader(BytesIO(data)))
    except Exception:
        return []


def _uris_from_reader(reader) -> list[str]:
    found: list[str] = []
    for page in reader.pages:
        annots = page.get("/Annots") or []
        if hasattr(annots, "get_object"):
            annots = annots.get_object()
        for annot in annots:
            obj = annot.get_object() if hasattr(annot, "get_object") else annot
            action = obj.get("/A") if obj else None
            if action is not None and hasattr(action, "get_object"):
                action = action.get_object()
            uri = action.get("/URI") if action else None
            if uri:
                found.append(str(uri))
    return found


def _append_links(text: str, links: list[str]) -> str:
    fresh = []
    for link in links:
        cleaned = (link or "").strip()
        if cleaned and cleaned not in text and cleaned not in fresh:
            fresh.append(cleaned)
    if not fresh:
        return (text or "").strip()
    return ((text or "").rstrip() + "\n" + "\n".join(fresh)).strip()
