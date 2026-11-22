"""A one-column text PDF from CV markdown with the standard library only, for machines with no Edge or Chrome.

Plain on purpose (it is what an ATS reads): Helvetica, headings in bold, bullets, links kept as visible text.
Letters outside Western European (Turkish s-cedilla, g-breve, dotless i ...) are written as their closest ASCII
letter, because the built-in PDF fonts have no glyph for them. The text stays selectable and searchable.
"""
import re

PAGE_W, PAGE_H, MARGIN = 595, 842, 46  # A4 in points
ASCII = str.maketrans({"ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G", "ı": "i", "İ": "I", "ń": "n", "ł": "l", "Ł": "L",
                       "ś": "s", "ź": "z", "ż": "z", "ć": "c", "ą": "a", "ę": "e", "č": "c", "š": "s", "ž": "z",
                       "ř": "r", "ě": "e", "ő": "o", "ű": "u", "–": "-", "—": "-", "“": '"', "”": '"', "’": "'",
                       "‘": "'", "…": "...", "•": "-", "·": "|", "€": "EUR"})


def _plain(s):
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s)
    return s.translate(ASCII).encode("cp1252", "replace").decode("cp1252")


def _esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text, size, width):
    per = max(10, int(width / (size * 0.5)))  # Helvetica averages about half an em per letter
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > per:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return out + [line] if line else out


def render(md):
    """Markdown text -> PDF bytes."""
    rows = []  # (font, size, gap_before, indent, text)
    for raw in md.splitlines():
        s = raw.strip()
        if not s:
            continue
        if m := re.match(r"(#{1,3})\s+(.+?)\s*#*$", s):
            lvl = len(m.group(1))
            rows.append(("F2", (17, 11.5, 10.5)[lvl - 1], (0, 8, 4)[lvl - 1], 0, _plain(m.group(2)).upper() if lvl == 2 else _plain(m.group(2))))
        elif s[:2] in ("- ", "* ", "• "):
            rows.append(("F1", 10, 1.5, 12, "- " + _plain(s[2:].strip())))
        else:
            rows.append(("F1", 10, 1.5, 0, _plain(s)))
    pages, ops, y = [], [], PAGE_H - MARGIN
    for font, size, gap, indent, text in rows:
        lead = size * 1.3
        lines = _wrap(text, size, PAGE_W - 2 * MARGIN - indent)
        if y - gap - lead * len(lines[:2]) < MARGIN:  # keep at least two lines together
            pages.append(ops)
            ops, y = [], PAGE_H - MARGIN
        y -= gap
        for ln in lines:
            if y - lead < MARGIN:
                pages.append(ops)
                ops, y = [], PAGE_H - MARGIN
            y -= lead
            hang = 7 if indent and ln is not lines[0] else 0
            ops.append(f"BT /{font} {size} Tf {MARGIN + indent + hang} {y:.1f} Td ({_esc(ln)}) Tj ET")
    pages.append(ops)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    kids = []
    for ops in pages:
        body = "\n".join(ops).encode("cp1252", "replace")
        objs.append(b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream")
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>"
                    % (PAGE_W, PAGE_H, len(objs)))
        kids.append(len(objs))
    objs[1] = ("<< /Type /Pages /Count %d /Kids [%s] >>" % (len(kids), " ".join(f"{k} 0 R" for k in kids))).encode()
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)
