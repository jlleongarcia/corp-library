"""Minimal but genuine documents (Office, OpenDocument, PDF) built in memory for the tests."""

import io
import zipfile
from xml.sax.saxutils import escape

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _zip(members: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, xml in members.items():
            zf.writestr(name, xml.encode("utf-8"))
    return buf.getvalue()


def docx(*paragraphs: str) -> bytes:
    body = "".join(f"<w:p><w:r><w:t xml:space='preserve'>{escape(p)}</w:t></w:r></w:p>" for p in paragraphs)
    return _zip({
        "[Content_Types].xml": "<Types/>",
        "word/document.xml": f"<w:document xmlns:w='{W}'><w:body>{body}</w:body></w:document>",
    })


def pptx(*slides: str) -> bytes:
    members = {"[Content_Types].xml": "<Types/>"}
    for i, text in enumerate(slides, 1):
        members[f"ppt/slides/slide{i}.xml"] = (
            f"<p:sld xmlns:p='p' xmlns:a='{A}'><a:p><a:r><a:t>{escape(text)}</a:t></a:r></a:p></p:sld>"
        )
    return _zip(members)


def xlsx(sheet: str, *strings: str) -> bytes:
    shared = "".join(f"<si><t>{escape(s)}</t></si>" for s in strings)
    return _zip({
        "[Content_Types].xml": "<Types/>",
        "xl/workbook.xml": f"<workbook xmlns='{S}'><sheets><sheet name='{escape(sheet)}' sheetId='1'/></sheets></workbook>",
        "xl/sharedStrings.xml": f"<sst xmlns='{S}'>{shared}</sst>",
    })


def odt(*paragraphs: str) -> bytes:
    ns = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    body = "".join(f"<text:p>{escape(p)}</text:p>" for p in paragraphs)
    return _zip({"content.xml": f"<office:document-content xmlns:office='o' xmlns:text='{ns}'>{body}</office:document-content>"})


def pdf(*pages: str) -> bytes:
    """One page per string (ASCII, Helvetica). An empty string is a page with no text, like a scan."""
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    kids = []
    for i, text in enumerate(pages):
        page, content = 4 + 2 * i, 5 + 2 * i
        kids.append(f"{page} 0 R")
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode() if text else b""
        objects[page] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content} 0 R >>"
        ).encode()
        objects[content] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode()

    out = b"%PDF-1.4\n"
    offsets = {}
    for k in sorted(objects):
        offsets[k] = len(out)
        out += b"%d 0 obj\n" % k + objects[k] + b"\nendobj\n"
    xref, size = len(out), max(objects) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    out += b"".join(b"%010d 00000 n \n" % offsets[k] for k in range(1, size))
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref)
    return out
