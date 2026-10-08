"""
Runs inside the api image in CI: the parts of the image that the test suite
can't check because they only exist on Linux.

    docker run --rm -e OCR_ENABLED=true -v "$PWD/.github/ci:/ci:ro" <api image> python /ci/image_selftest.py
"""

import io
import subprocess

# Kerberos SSO: gssapi is compiled in the build stage and needs libgssapi-krb5 at runtime.
import gssapi  # noqa: F401
import gssapi.raw  # noqa: F401  (the compiled extension: fails here if the shared library is missing)

print("gssapi ok")

# Tesseract with both OCR languages.
langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, check=True).stdout.split()
assert {"spa", "eng"} <= set(langs), f"tesseract languages: {langs}"
print("tesseract languages", langs[1:])

# A scanned PDF (image only, no text layer) goes through the app's real OCR path.
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app.services.extract import extract  # noqa: E402
from app.services.text import fold  # noqa: E402

page = Image.new("L", (1700, 500), 255)
# Pillow's built-in font has no accented letters: plain ASCII text.
ImageDraw.Draw(page).text((80, 180), "Presupuesto anual de obras 2025", fill=0, font=ImageFont.load_default(size=80))
pdf = io.BytesIO()
page.save(pdf, format="PDF", resolution=200)

result = extract("pdf", pdf.getvalue())
print("ocr", result.method, repr(result.text))
assert result.method == "ocr", result.method
assert "presupuesto" in fold(result.text) and "anual" in fold(result.text), result.text
print("image self-test passed")
