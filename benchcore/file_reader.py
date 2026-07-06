"""Universal input-file reader for benchmark auditing.

If a task provides a file, the auditor must be able to read it. This dispatches
by file type to the right extractor (spreadsheets, Word, PowerPoint, PDF, text)
and returns a compact text profile the LLM auditors can reason over. Unknown
types fall back to a best-effort text read; the caller can then let an LLM decide
how to interpret them.
"""
from __future__ import annotations

import warnings
from pathlib import Path

warnings.filterwarnings("ignore")


def _xlsx(path: Path, max_chars: int) -> str:
    import pandas as pd
    xl = pd.ExcelFile(path)
    out = [f"sheets={xl.sheet_names}"]
    for sh in xl.sheet_names[:3]:
        df = xl.parse(sh, header=None, nrows=12)
        out.append(f"-- sheet '{sh}' --\n" + df.to_string(max_colwidth=12)[: max_chars // 2])
    return "\n".join(out)


def _docx(path: Path, max_chars: int) -> str:
    from docx import Document
    d = Document(str(path))
    paras = [p.text for p in d.paragraphs if p.text.strip()]
    tables = []
    for t in d.tables[:3]:
        for row in t.rows[:8]:
            tables.append(" | ".join(c.text for c in row.cells))
    body = "\n".join(paras[:60])
    if tables:
        body += "\n[tables]\n" + "\n".join(tables[:24])
    return f"({len(d.paragraphs)} paras, {len(d.tables)} tables)\n" + body[:max_chars]


def _pptx(path: Path, max_chars: int) -> str:
    from pptx import Presentation
    prs = Presentation(str(path))
    texts = []
    for i, slide in enumerate(prs.slides):
        s = " | ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame and sh.text_frame.text.strip())
        if s:
            texts.append(f"[slide {i+1}] {s}")
    return f"({len(prs.slides)} slides)\n" + "\n".join(texts)[:max_chars]


def _pdf(path: Path, max_chars: int, max_pages: int = 8) -> str:
    import pdfplumber
    with pdfplumber.open(str(path)) as pdf:
        n = len(pdf.pages)
        txt = []
        for pg in pdf.pages[:max_pages]:
            txt.append(pg.extract_text() or "")
        body = "\n".join(txt)
    return f"({n}-page PDF, showing first {min(n, max_pages)} pages)\n" + body[:max_chars]


def _plain(path: Path, max_chars: int) -> str:
    return path.read_text(encoding="utf-8", errors="replace")[:max_chars]


_DISPATCH = {
    ".xlsx": _xlsx, ".xls": _xlsx,
    ".docx": _docx, ".doc": _docx,
    ".pptx": _pptx,
    ".pdf": _pdf,
    ".csv": _plain, ".txt": _plain, ".md": _plain, ".json": _plain,
}


def read_file(path, max_chars: int = 3000) -> str:
    """Return a compact text profile of any supported input file."""
    path = Path(path)
    if not path.exists():
        return f"[{path.name}] (文件不存在)"
    ext = path.suffix.lower()
    reader = _DISPATCH.get(ext)
    try:
        if reader is None:
            return f"FILE {path.name} (类型 {ext} 暂无专用解析器, 尝试纯文本)\n" + _plain(path, max_chars)
        return f"FILE {path.name} [{ext}]\n" + reader(path, max_chars)
    except Exception as e:
        return f"FILE {path.name} [{ext}] (读取失败: {e})"


def search_file(path, terms: list[str], max_pages: int = 200) -> dict:
    """Search a (large) file's full text for terms; returns term -> found context.

    Lets value-rubric verification locate specific figures in big documents
    (e.g. a 193-page annual report) without sending the whole file to an LLM.
    """
    path = Path(path)
    ext = path.suffix.lower()
    text = ""
    try:
        if ext == ".pdf":
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                text = "\n".join((p.extract_text() or "") for p in pdf.pages[:max_pages])
        elif ext in (".docx", ".doc"):
            from docx import Document
            text = "\n".join(p.text for p in Document(str(path)).paragraphs)
        else:
            text = read_file(path, 200000)
    except Exception as e:
        return {"_error": str(e)}
    out = {}
    low = text.lower()
    for t in terms:
        idx = low.find(t.lower())  # case-insensitive: 'purchase order' must match 'Purchase Order'
        out[t] = text[max(0, idx - 40): idx + 60].replace("\n", " ") if idx >= 0 else None
    return out
