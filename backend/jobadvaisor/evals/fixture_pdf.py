"""A dependency-free writer for fixture PDFs: plain text set in Helvetica, so tests and the
field-filling eval make their PDFs from demo text instead of committing binary files."""

import textwrap

LINES_PER_PAGE = 60


def minimal_pdf(text: str) -> bytes:
    """A PDF whose pages hold `text`, wrapped at 90 characters, 60 lines per page; `pypdf`
    reads the text back. Characters outside Latin-1 become "?"; empty text gives one blank
    page."""
    lines = [wrapped for line in text.splitlines()
             for wrapped in (textwrap.wrap(line, 90) or [""])]
    pages = [lines[i:i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)] or [[]]
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
                   b" ".join(b"%d 0 R" % (4 + 2 * n) for n in range(len(pages))), len(pages)),
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
               b"/Encoding /WinAnsiEncoding >>"]
    for n, page in enumerate(pages):
        stream = b"BT /F1 10 Tf 12 TL 50 800 Td " + b"".join(
            b"(%s) Tj T* " % _escape(line) for line in page) + b"ET"
        objects += [b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                    b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (5 + 2 * n),
                    b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, xref)
    return bytes(out)


def _escape(line: str) -> bytes:
    raw = line.encode("latin-1", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
