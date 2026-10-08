"""Text extraction and the search text helpers."""

import pytest

from app.services import extract
from app.services.extract import ExtractionError, OcrUnavailable
from app.services.text import fold, parse_query, snippet, words

from . import docs


def test_word_powerpoint_excel_and_opendocument():
    assert extract.extract("docx", docs.docx("Presupuesto de la campaña", "de información")).text == (
        "Presupuesto de la campaña\nde información"
    )
    assert extract.extract("pptx", docs.pptx("Slide one", "Slide two")).text == "Slide one\nSlide two"
    xl = extract.extract("xlsx", docs.xlsx("Ventas 2025", "Cliente", "Importe")).text
    assert xl.splitlines() == ["Ventas 2025", "Cliente", "Importe"]
    assert extract.extract("odt", docs.odt("Acta de la reunión")).text == "Acta de la reunión"


def test_plain_text_in_windows_encodings_and_html():
    assert extract.extract("txt", "Año de gestión".encode("cp1252")).text == "Año de gestión"
    assert extract.extract("txt", "Año".encode("utf-16")).text == "Año"
    html = b"<html><style>p{}</style><body><p>Hola &amp; adi&oacute;s</p><script>x()</script></body></html>"
    assert extract.extract("html", html).text.split() == ["Hola", "&", "adiós"]


def test_pdf_text_layer():
    result = extract.extract("pdf", docs.pdf("Quarterly sales report", "Second page here"))
    assert result.method == "text"
    assert "Quarterly sales report" in result.text and "Second page" in result.text


def test_scanned_pdf_goes_to_ocr(monkeypatch):
    monkeypatch.setattr(extract, "tesseract_available", lambda: True)
    monkeypatch.setattr(extract, "ocr_image", lambda png: "texto escaneado" if png.startswith(b"\x89PNG") else "")
    result = extract.extract("pdf", docs.pdf("", ""))
    assert result.method == "ocr" and result.text == "texto escaneado\ntexto escaneado"


def test_short_pages_are_text_not_scans(monkeypatch):
    # A slide deck exported to PDF: little text per page, but text.
    def no_ocr(png):
        raise AssertionError("text pages must not be OCR'd")

    monkeypatch.setattr(extract, "tesseract_available", lambda: True)
    monkeypatch.setattr(extract, "ocr_image", no_ocr)
    result = extract.extract("pdf", docs.pdf("Agenda 2025", "Objetivos"))
    assert result.method == "text" and "Objetivos" in result.text


def test_only_the_scanned_pages_of_a_mixed_pdf_are_ocrd(monkeypatch):
    # A typed report with the signed pages scanned and appended.
    monkeypatch.setattr(extract, "tesseract_available", lambda: True)
    monkeypatch.setattr(extract, "ocr_image", lambda png: "firma del director")
    result = extract.extract("pdf", docs.pdf("Informe tecnico de la obra", ""))
    assert result.method == "ocr" and result.text == "Informe tecnico de la obra\nfirma del director"


def test_mixed_pdf_without_tesseract_keeps_its_text():
    result = extract.extract("pdf", docs.pdf("Informe tecnico de la obra", ""))
    assert result.method == "text" and result.text.startswith("Informe tecnico")


def test_scanned_pdf_without_tesseract_is_flagged():
    with pytest.raises(OcrUnavailable):  # OCR_ENABLED=false in the tests
        extract.extract("pdf", docs.pdf(""))


def test_corrupt_or_protected_files_raise_extraction_errors():
    with pytest.raises(ExtractionError):
        extract.extract("docx", b"\xd0\xcf\x11\xe0 an encrypted Office container")
    with pytest.raises(ExtractionError):
        extract.extract("pdf", b"%PDF-1.4 truncated")


def test_zip_bomb_members_are_refused(monkeypatch):
    monkeypatch.setattr(extract, "MAX_ZIP_MEMBER", 100)
    with pytest.raises(ExtractionError):
        extract.extract("docx", docs.docx("x" * 500))


# ── Text helpers ──────────────────────────────────────────────────────────────

def test_fold_strips_accents_and_keeps_length():
    assert fold("Información CAMPAÑA Über") == "informacion campana uber"
    s = "Ñandú İstanbul ﬁn"
    assert len(fold(s)) == len(s)


def test_names_are_split_into_words():
    assert words("INF-2023_Presupuesto.v2.xlsx") == "inf 2023 presupuesto v2 xlsx"


def test_query_parsing():
    p = parse_query('Presupuesto "plan anual" -borrador INF-2023.pdf or acta')
    assert p.terms == ["presupuesto", "plan", "anual", "inf", "2023", "pdf", "acta"]
    assert p.excluded == ["borrador"]
    assert '"plan anual"' in p.text and "-borrador" in p.text


def test_snippet_highlights_original_text():
    text = "Intro. " * 30 + "El presupuesto de información para 2025 está aprobado. " + "Fin. " * 30
    segs = snippet(text, parse_query("informacion presupuestos").terms)
    hits = [s["text"] for s in segs if s["hit"]]
    assert hits == ["presupuesto", "información"]  # stems match; accents shown as written
    assert segs[0]["text"] == "…" and segs[-1]["text"] == "…"
