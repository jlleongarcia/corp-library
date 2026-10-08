"""
Text extraction from document bytes.

- PDF: the text layer, via pdfium. A PDF with (almost) no text is a scan: its
  pages are rendered and read with Tesseract OCR (Spanish + English).
- Word / Excel / PowerPoint (2007+) and OpenDocument: these are zip files of
  XML; the text is read straight from the XML, no Office libraries needed.
- Plain text formats (txt, csv, html, ...): decoded, tags stripped.

Everything else (legacy .doc/.xls/.ppt, images, video, CAD, archives) is
searchable by name, path and metadata only. Only bytes already in memory are
handled here; reading files from the share is the indexer's job.
"""

import html
import io
import logging
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from xml.etree import ElementTree

from ..config import settings

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {"txt", "csv", "tsv", "md", "log", "json", "xml", "html", "htm", "ini", "cfg", "sql", "yml", "yaml"}
WORD_EXTENSIONS = {"docx", "docm", "dotx", "dotm"}
EXCEL_EXTENSIONS = {"xlsx", "xlsm", "xltx", "xltm"}
POWERPOINT_EXTENSIONS = {"pptx", "pptm", "ppsx", "ppsm", "potx"}
ODF_EXTENSIONS = {"odt", "ods", "odp"}
EXTRACTABLE = TEXT_EXTENSIONS | WORD_EXTENSIONS | EXCEL_EXTENSIONS | POWERPOINT_EXTENSIONS | ODF_EXTENSIONS | {"pdf"}

MAX_ZIP_MEMBER = 64 * 1024 * 1024  # uncompressed bytes read from one zip member (zip bombs)
MIN_PAGE_TEXT = 5  # a PDF page with fewer characters than this is a scan (scans have ~none)
OCR_DPI = 300
OCR_PAGE_TIMEOUT = 120  # seconds


class ExtractionError(Exception):
    """The file couldn't be read (corrupt, password-protected, ...)."""


class OcrUnavailable(ExtractionError):
    """A scanned PDF, but Tesseract isn't installed or is disabled."""


@dataclass
class Extracted:
    text: str
    method: str  # text | ocr


def can_extract(extension: str) -> bool:
    return extension in EXTRACTABLE


def initial_status(extension: str, size: int) -> str:
    """Indexing status of a new (or changed) file: whether its text is worth reading."""
    if not can_extract(extension):
        return "metadata"
    if size > settings.extract_max_size:
        return "too_large"
    return "pending"


def extract(extension: str, data: bytes) -> Extracted:
    if extension == "pdf":
        return _pdf(data)
    if extension in TEXT_EXTENSIONS:
        text = _decode(data)
        if extension in {"html", "htm", "xml"}:
            text = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", text)))
        return Extracted(text, "text")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if extension in WORD_EXTENSIONS:
                parts = ["word/document.xml", "word/footnotes.xml", "word/endnotes.xml"]
                parts += sorted(n for n in zf.namelist() if re.fullmatch(r"word/(header|footer)\d*\.xml", n))
                return Extracted(_ooxml_text(zf, parts, para="p"), "text")
            if extension in POWERPOINT_EXTENSIONS:
                slides = sorted(
                    (n for n in zf.namelist() if re.fullmatch(r"ppt/(slides/slide|notesSlides/notesSlide)\d+\.xml", n)),
                    key=lambda n: (n.startswith("ppt/notes"), int(re.search(r"(\d+)\.xml$", n).group(1))),
                )
                return Extracted(_ooxml_text(zf, slides, para="p"), "text")
            if extension in EXCEL_EXTENSIONS:
                sheets = _sheet_names(zf)
                strings = _ooxml_text(zf, ["xl/sharedStrings.xml"], para="si")
                return Extracted("\n".join(filter(None, [sheets, strings])), "text")
            if extension in ODF_EXTENSIONS:
                return Extracted(_odf_text(zf), "text")
    except zipfile.BadZipFile as exc:
        # Password-protected Office files are not zips but encrypted containers.
        raise ExtractionError("not a valid Office file (password-protected or corrupt)") from exc
    raise ExtractionError(f"no extractor for .{extension}")


# ── Plain text ────────────────────────────────────────────────────────────────

def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")  # what Windows tools write in Spain


# ── Office Open XML / OpenDocument ────────────────────────────────────────────

def _read_member(zf: zipfile.ZipFile, name: str) -> bytes | None:
    try:
        info = zf.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_ZIP_MEMBER:
        raise ExtractionError(f"{name} is too large to read ({info.file_size} bytes)")
    with zf.open(info) as f:
        return f.read(MAX_ZIP_MEMBER + 1)[:MAX_ZIP_MEMBER]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _ooxml_text(zf: zipfile.ZipFile, parts: list[str], para: str) -> str:
    """Text of the <t> elements, one line per paragraph (<p>) or shared string (<si>)."""
    out: list[str] = []
    for name in parts:
        data = _read_member(zf, name)
        if not data:
            continue
        line: list[str] = []
        for _event, el in ElementTree.iterparse(io.BytesIO(data), events=("end",)):
            tag = _local(el.tag)
            if tag == "t" and el.text:
                line.append(el.text)
            elif tag == "tab":
                line.append(" ")
            elif tag == para:
                if line:
                    out.append("".join(line))
                line = []
                el.clear()
        if line:
            out.append("".join(line))
    return "\n".join(out)


def _sheet_names(zf: zipfile.ZipFile) -> str:
    data = _read_member(zf, "xl/workbook.xml")
    if not data:
        return ""
    root = ElementTree.fromstring(data)
    return "\n".join(el.get("name", "") for el in root.iter() if _local(el.tag) == "sheet")


def _odf_text(zf: zipfile.ZipFile) -> str:
    data = _read_member(zf, "content.xml")
    if not data:
        return ""
    root = ElementTree.fromstring(data)
    return "\n".join(
        "".join(el.itertext()) for el in root.iter() if _local(el.tag) in ("p", "h")
    )


# ── PDF ───────────────────────────────────────────────────────────────────────

def _pdf(data: bytes) -> Extracted:
    """
    The text layer of each page; a page without one (a scan, possibly appended
    to a typed document) is read with OCR instead.
    """
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise ExtractionError(f"unreadable PDF ({exc})") from exc
    try:
        pages: list[str] = []
        scanned: list[int] = []
        for i in range(len(pdf)):
            page = pdf[i]
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            textpage.close()
            page.close()
            pages.append(text)
            if len(text.strip()) < MIN_PAGE_TEXT:
                scanned.append(i)

        to_ocr = scanned[: settings.ocr_max_pages]
        if to_ocr and not tesseract_available():
            if len(scanned) == len(pages):
                raise OcrUnavailable("scanned PDF, OCR not available")
            to_ocr = []  # keep the pages that have text
        for i in to_ocr:
            pages[i] = _ocr_page(pdf, i)
        return Extracted("\n".join(pages), "ocr" if to_ocr else "text")
    finally:
        pdf.close()


@lru_cache(maxsize=1)
def tesseract_available() -> bool:
    return bool(settings.ocr_enabled and shutil.which(settings.tesseract_cmd))


def _ocr_page(pdf, index: int) -> str:
    page = pdf[index]
    image = page.render(scale=OCR_DPI / 72, grayscale=True).to_pil()
    page.close()
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return ocr_image(buf.getvalue())


def ocr_image(png: bytes) -> str:
    try:
        result = subprocess.run(
            [settings.tesseract_cmd, "stdin", "stdout", "-l", settings.ocr_languages],
            input=png, capture_output=True, timeout=OCR_PAGE_TIMEOUT, check=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError("OCR timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise ExtractionError(f"OCR failed: {exc.stderr.decode(errors='replace')[:200]}") from exc
    return result.stdout.decode("utf-8", errors="replace")
