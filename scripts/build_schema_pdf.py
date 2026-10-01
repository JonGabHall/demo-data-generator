"""Export the maintained schema guide as a portable, selectable-text PDF."""

from __future__ import annotations

from pathlib import Path
import re
import textwrap


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "docs" / "schema.md"
OUTPUT = ROOT / "docs" / "Indoors_Demo_Asset_Schema.pdf"
PAGE_WIDTH = 612
PAGE_HEIGHT = 792
MARGIN = 54
LINE_HEIGHT = 13
LINES_PER_PAGE = 48


def _pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _document_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    in_mermaid = False
    for raw_line in markdown.splitlines():
        if raw_line.startswith("```mermaid"):
            in_mermaid = True
            lines.extend(("Schema relationships", "Facilities -> Levels -> Units", "Units -> Indoor Asset Location -> Asset Lifecycle", "Facilities -> Exterior Asset Points", "Asset Lifecycle -> Inspections, Repairs, Work Orders, External References, Field Work, Media"))
            continue
        if in_mermaid:
            if raw_line == "```":
                in_mermaid = False
            continue
        if raw_line.startswith("#"):
            heading = raw_line.lstrip("#").strip()
            lines.extend(("", heading.upper()))
            continue
        if raw_line.startswith("|"):
            cells = [cell.strip() for cell in raw_line.strip("|").split("|")]
            if not all(re.fullmatch(r"-+", cell.replace(" ", "")) for cell in cells):
                lines.append(" | ".join(cells))
            continue
        text = raw_line.replace("`", "").strip()
        if text:
            lines.extend(textwrap.wrap(text, width=86, break_long_words=False) or [""])
        else:
            lines.append("")
    return lines


def _page_stream(lines: list[str], page_number: int) -> bytes:
    commands = ["BT", "/F1 10 Tf", f"{MARGIN} {PAGE_HEIGHT - MARGIN} Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append(f"0 -{LINE_HEIGHT} Td")
        commands.append(f"({_pdf_text(line)}) Tj")
    commands.extend(("ET", "BT", "/F1 8 Tf", f"{PAGE_WIDTH - MARGIN - 55} 30 Td", f"(Page {page_number}) Tj", "ET"))
    return "\n".join(commands).encode("ascii", "replace")


def build_pdf() -> None:
    lines = _document_lines(SOURCE.read_text(encoding="utf-8"))
    pages = [lines[index : index + LINES_PER_PAGE] for index in range(0, len(lines), LINES_PER_PAGE)]
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_object_numbers = [4 + index * 2 for index in range(len(pages))]
    objects.append(
        f"<< /Type /Pages /Kids [{' '.join(f'{number} 0 R' for number in page_object_numbers)}] /Count {len(pages)} >>".encode()
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for page_number, page_lines in enumerate(pages, start=1):
        page_object = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] /Resources << /Font << /F1 3 0 R >> >> /Contents {4 + (page_number - 1) * 2 + 1} 0 R >>"
        stream = _page_stream(page_lines, page_number)
        objects.append(page_object.encode())
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, object_data in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode())
        pdf.extend(object_data)
        pdf.extend(b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    OUTPUT.write_bytes(pdf)


if __name__ == "__main__":
    build_pdf()
    print(OUTPUT)