"""Turn uploaded files into plain text.

Supported:
- Documents: PDF (pypdf), Word .docx (read straight from the zip's XML, no extra library), .txt / .md
- Teams transcripts: .vtt (WebVTT with <v Speaker> tags), Teams .docx export ("Name   0:03" then the line), plain text

Uploads are untrusted: size and type are checked, and nothing is executed or written to disk.
"""
import io
import re
import zipfile
from dataclasses import dataclass, field
from html import unescape

from fastapi import HTTPException, UploadFile

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_CHARS = 100_000            # what the knowledge base stores per document
DOC_TYPES = {".pdf", ".docx", ".txt", ".md"}
TRANSCRIPT_TYPES = {".vtt", ".docx", ".txt"}


@dataclass
class Extracted:
    text: str
    filename: str
    kind: str                    # pdf | docx | text | vtt
    pages: int = 0
    truncated: bool = False
    speakers: list[str] = field(default_factory=list)


def _ext(name: str) -> str:
    m = re.search(r"(\.[A-Za-z0-9]+)$", name or "")
    return m.group(1).lower() if m else ""


def safe_name(name: str) -> str:
    """Keep only the file name, without any path, and only safe characters."""
    base = re.split(r"[\\/]", name or "upload")[-1]
    return re.sub(r"[^\w.\- ()]", "_", base)[:120] or "upload"


async def read_upload(file: UploadFile, allowed: set[str]) -> tuple[bytes, str, str]:
    name = safe_name(file.filename or "")
    ext = _ext(name)
    if ext not in allowed:
        raise HTTPException(422, f"Unsupported file type '{ext or 'none'}'. Allowed: {', '.join(sorted(allowed))}")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File is larger than 10 MB")
    if not data:
        raise HTTPException(422, "The file is empty")
    return data, name, ext


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _pdf_text(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise HTTPException(422, "This PDF is password-protected")
        pages = [(p.extract_text() or "").strip() for p in reader.pages]
    except PdfReadError:
        raise HTTPException(422, "This file isn't a readable PDF")
    return "\n\n".join(p for p in pages if p), len(pages)


def _docx_paragraphs(data: bytes) -> list[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError):
        raise HTTPException(422, "This file isn't a readable Word document")
    paras = []
    for p in re.split(r"</w:p>", xml):
        p = re.sub(r"<w:tab[^>]*/>", "\t", p)
        p = re.sub(r"<w:br[^>]*/>", "\n", p)
        text = unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))).strip()
        if text:
            paras.append(text)
    return paras


def _clean(text: str) -> tuple[str, bool]:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > MAX_CHARS:
        return text[:MAX_CHARS], True
    return text, False


async def document_text(file: UploadFile) -> Extracted:
    data, name, ext = await read_upload(file, DOC_TYPES)
    pages = 0
    if ext == ".pdf":
        text, pages = _pdf_text(data)
        kind = "pdf"
    elif ext == ".docx":
        text, kind = "\n\n".join(_docx_paragraphs(data)), "docx"
    else:
        text, kind = _decode(data), "text"
    text, truncated = _clean(text)
    if len(text) < 20:
        hint = " It may be a scanned image; export it with selectable text." if ext == ".pdf" else ""
        raise HTTPException(422, f"Couldn't find any readable text in this file.{hint}")
    return Extracted(text, name, kind, pages, truncated)


# ---------------------------------------------------------------- transcripts
_VTT_TIME = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?[.,]\d{1,3}\s*-->\s*")
_VTT_VOICE = re.compile(r"<v(?:\.[^ >]+)?\s+([^>]+)>(.*?)(?:</v>|$)", re.S)
_TEAMS_DOCX_HEAD = re.compile(r"^(?P<name>[^\d\n][^\n]{0,80}?)\s{2,}(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*$")
_SPEAKER_LINE = re.compile(r"^(?P<name>[A-Z][\w.'\- ]{1,40}?)\s*:\s+(?P<text>.+)$")
# Labels people type in notes that look like "Name: text" but aren't speakers.
_NOT_SPEAKERS = {"decision", "decisions", "action", "action item", "actions", "todo", "note", "notes", "follow-up",
                 "follow up", "ai", "agenda", "summary", "question", "risk", "update", "subject", "re", "fyi"}


def _speaker_match(line: str):
    m = _SPEAKER_LINE.match(line)
    return m if m and m.group("name").strip().lower() not in _NOT_SPEAKERS else None


def _merge(turns: list[tuple[str, str]]) -> tuple[str, list[str]]:
    """Join consecutive lines from the same speaker; return 'Name: text' lines + speakers in order."""
    merged: list[list[str]] = []
    for speaker, text in turns:
        text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", text))).strip()
        if not text:
            continue
        if merged and merged[-1][0] == speaker:
            merged[-1][1] += " " + text
        else:
            merged.append([speaker, text])
    speakers = list(dict.fromkeys(s for s, _ in merged if s))
    return "\n".join(f"{s}: {t}" if s else t for s, t in merged), speakers


def _parse_vtt(raw: str) -> list[tuple[str, str]]:
    turns, in_cue = [], False
    for line in raw.splitlines():
        line = line.strip()
        if _VTT_TIME.match(line):
            in_cue = True
            continue
        if not line:
            in_cue = False
            continue
        if not in_cue or line.startswith(("WEBVTT", "NOTE")):
            continue
        m = _VTT_VOICE.search(line)
        if m:
            turns.append((m.group(1).strip(), m.group(2)))
        elif (s := _speaker_match(line)):
            turns.append((s.group("name").strip(), s.group("text")))
        else:
            turns.append(("", line))
    return turns


def _parse_lines(lines: list[str]) -> list[tuple[str, str]]:
    """Teams .docx export ('Name   0:03' then the text) or plain 'Name: text' lines."""
    turns, current = [], ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if m := _TEAMS_DOCX_HEAD.match(line):
            current = m.group("name").strip()
        elif m := _speaker_match(line):
            turns.append((m.group("name").strip(), m.group("text")))
        elif not re.fullmatch(r"[\d:.\s\->]+", line):  # skip bare timestamps
            turns.append((current, line))
    return turns


async def transcript_text(file: UploadFile) -> Extracted:
    data, name, ext = await read_upload(file, TRANSCRIPT_TYPES)
    if ext == ".vtt":
        turns, kind = _parse_vtt(_decode(data)), "vtt"
    elif ext == ".docx":
        turns, kind = _parse_lines(_docx_paragraphs(data)), "docx"
    else:
        raw = _decode(data)
        turns, kind = (_parse_vtt(raw), "vtt") if raw.lstrip().startswith("WEBVTT") else (_parse_lines(raw.splitlines()), "text")
    text, speakers = _merge(turns)
    text, truncated = _clean(text)
    if len(text) < 20:
        raise HTTPException(422, "Couldn't find any spoken lines in this transcript")
    return Extracted(text, name, kind, 0, truncated, speakers[:50])
