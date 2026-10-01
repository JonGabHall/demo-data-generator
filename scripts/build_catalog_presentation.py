"""Build the editable catalog workflow PowerPoint and PDF with PowerPoint COM."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
from typing import Any, Iterable

import win32com.client


SLIDE_WIDTH = 960
SLIDE_HEIGHT = 540

COLORS = {
    "navy": "17324D",
    "teal": "0B7285",
    "blue": "2878B5",
    "coral": "E76F51",
    "gold": "E9B44C",
    "green": "3D8361",
    "ink": "1F2D38",
    "muted": "5D6B75",
    "line": "D4DEE3",
    "paper": "F7F9F8",
    "white": "FFFFFF",
    "pale_teal": "DDF0F2",
    "pale_blue": "E4EEF8",
    "pale_coral": "FCE6E0",
    "pale_gold": "FBF1D4",
    "pale_green": "E1F1E7",
}

FACILITIES = (
    ("Vertex Medical Center", "VMC", 286, 1003, 10, "Reviewed"),
    ("Point Place", "PP", 114, 648, 13, "Hospital"),
    ("Line Lake", "LL", 114, 644, 18, "Hospital"),
    ("Node North", "NN", 120, 658, 9, "Hospital"),
    ("Rohdran Cove", "RC", 128, 736, 11, "Hospital"),
    ("Admin HQ", "AHQ", 263, 1163, 11, "Office"),
)


def rgb(value: str) -> int:
    value = value.lstrip("#")
    red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    return red + (green << 8) + (blue << 16)


class Deck:
    def __init__(self, presentation: Any) -> None:
        self.presentation = presentation
        presentation.PageSetup.SlideWidth = SLIDE_WIDTH
        presentation.PageSetup.SlideHeight = SLIDE_HEIGHT

    def add_slide(self, title: str, kicker: str, subtitle: str | None = None) -> Any:
        slide = self.presentation.Slides.Add(self.presentation.Slides.Count + 1, 12)
        self.rect(slide, 0, 0, SLIDE_WIDTH, SLIDE_HEIGHT, "paper", line=None)
        self.rect(slide, 0, 0, 12, SLIDE_HEIGHT, "teal", line=None)
        self.text(slide, kicker.upper(), 42, 24, 760, 20, 10, "teal", bold=True)
        self.text(slide, title, 42, 50, 860, 48, 27, "navy", bold=True)
        if subtitle:
            self.text(slide, subtitle, 44, 99, 850, 32, 11, "muted")
        self.text(
            slide,
            f"INDOORS ASSET CATALOG  |  {self.presentation.Slides.Count:02d}",
            42,
            512,
            870,
            14,
            7.5,
            "muted",
        )
        return slide

    def rect(
        self,
        slide: Any,
        left: float,
        top: float,
        width: float,
        height: float,
        fill: str,
        *,
        line: str | None = "line",
        radius: bool = False,
        transparency: float = 0,
    ) -> Any:
        shape_type = 5 if radius else 1
        shape = slide.Shapes.AddShape(shape_type, left, top, width, height)
        shape.Fill.Solid()
        shape.Fill.ForeColor.RGB = rgb(COLORS[fill])
        shape.Fill.Transparency = transparency / 100 if transparency > 1 else transparency
        if line is None:
            shape.Line.Visible = 0
        else:
            shape.Line.ForeColor.RGB = rgb(COLORS[line])
            shape.Line.Weight = 0.8
        return shape

    def circle(
        self,
        slide: Any,
        left: float,
        top: float,
        diameter: float,
        fill: str,
        *,
        line: str | None = None,
    ) -> Any:
        shape = slide.Shapes.AddShape(9, left, top, diameter, diameter)
        shape.Fill.Solid()
        shape.Fill.ForeColor.RGB = rgb(COLORS[fill])
        if line is None:
            shape.Line.Visible = 0
        else:
            shape.Line.ForeColor.RGB = rgb(COLORS[line])
        return shape

    def text(
        self,
        slide: Any,
        value: str,
        left: float,
        top: float,
        width: float,
        height: float,
        size: float,
        color: str = "ink",
        *,
        bold: bool = False,
        align: int = 1,
        valign: int = 1,
        font: str = "Aptos",
        margin: float = 2,
    ) -> Any:
        shape = slide.Shapes.AddTextbox(1, left, top, width, height)
        frame = shape.TextFrame
        frame.MarginLeft = margin
        frame.MarginRight = margin
        frame.MarginTop = margin
        frame.MarginBottom = margin
        frame.WordWrap = -1
        frame.VerticalAnchor = valign
        text_range = frame.TextRange
        text_range.Text = value
        text_range.Font.Name = font
        text_range.Font.Size = size
        text_range.Font.Bold = -1 if bold else 0
        text_range.Font.Color.RGB = rgb(COLORS[color])
        text_range.ParagraphFormat.Alignment = align
        return shape

    def line(
        self,
        slide: Any,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str = "line",
        *,
        weight: float = 1.5,
        arrow: bool = False,
        dash: bool = False,
    ) -> Any:
        shape = slide.Shapes.AddLine(x1, y1, x2, y2)
        shape.Line.ForeColor.RGB = rgb(COLORS[color])
        shape.Line.Weight = weight
        if arrow:
            shape.Line.EndArrowheadStyle = 3
        if dash:
            shape.Line.DashStyle = 4
        return shape

    def pill(
        self,
        slide: Any,
        value: str,
        left: float,
        top: float,
        width: float,
        fill: str,
        color: str,
    ) -> None:
        self.rect(slide, left, top, width, 22, fill, line=None, radius=True)
        self.text(slide, value, left + 4, top + 1, width - 8, 18, 8.5, color, bold=True, align=2)

    def metric(
        self,
        slide: Any,
        value: str,
        label: str,
        left: float,
        top: float,
        width: float,
        *,
        accent: str = "teal",
    ) -> None:
        self.rect(slide, left, top, width, 92, "white", radius=True)
        self.rect(slide, left, top, 6, 92, accent, line=None, radius=True)
        self.text(slide, value, left + 18, top + 15, width - 28, 35, 24, "navy", bold=True)
        self.text(slide, label, left + 18, top + 56, width - 28, 24, 9.5, "muted")

    def bullet_list(
        self,
        slide: Any,
        items: Iterable[str],
        left: float,
        top: float,
        width: float,
        *,
        size: float = 11,
        line_height: float = 34,
        color: str = "ink",
        accent: str = "teal",
    ) -> None:
        for index, item in enumerate(items):
            y = top + index * line_height
            self.circle(slide, left, y + 7, 8, accent)
            self.text(slide, item, left + 17, y, width - 17, line_height - 2, size, color)


def add_title_slide(deck: Deck) -> None:
    slide = deck.presentation.Slides.Add(1, 12)
    deck.rect(slide, 0, 0, SLIDE_WIDTH, SLIDE_HEIGHT, "navy", line=None)
    deck.rect(slide, 670, 0, 290, 540, "teal", line=None)
    for row in range(6):
        for column in range(4):
            fill = ("pale_teal", "pale_blue", "pale_green", "pale_gold")[(row + column) % 4]
            x = 704 + column * 54
            y = 92 + row * 52
            deck.rect(slide, x, y, 44, 38, fill, line=None, radius=True, transparency=8)
    deck.rect(slide, 704, 226, 206, 28, "coral", line=None, radius=True)
    deck.text(slide, "CENTRAL CORRIDOR", 714, 231, 188, 17, 8.5, "white", bold=True, align=2)
    deck.text(slide, "ARCGIS INDOORS", 54, 51, 510, 24, 11, "gold", bold=True)
    deck.text(slide, "Asset enrichment\nand organizational catalog", 54, 101, 560, 133, 34, "white", bold=True)
    deck.text(
        slide,
        "A deterministic workflow for lifecycle history, procedural facilities, relationships, and optional local narratives.",
        57,
        254,
        525,
        68,
        15,
        "pale_teal",
    )
    deck.pill(slide, "EDITABLE POWERPOINT", 57, 360, 152, "pale_gold", "navy")
    deck.pill(slide, "VALIDATED CATALOG", 220, 360, 152, "pale_green", "green")
    deck.text(slide, "Reporting date: October 1, 2026", 57, 474, 420, 22, 10, "white")
    deck.text(slide, "Synthetic demonstration data", 703, 458, 206, 22, 9.5, "white", bold=True, align=2)


def add_executive_summary(deck: Deck) -> None:
    slide = deck.add_slide(
        "A repeatable catalog, ready for demonstration",
        "Executive outcome",
        "One reviewed facility is preserved; five facilities are generated without CAD or manual room inventories.",
    )
    deck.metric(slide, "6", "Sites and facilities", 44, 151, 190, accent="teal")
    deck.metric(slide, "1,025", "Units across 32 levels", 254, 151, 190, accent="blue")
    deck.metric(slide, "4,852", "Indoor lifecycle assets", 464, 151, 190, accent="coral")
    deck.metric(slide, "0", "Orphan references", 674, 151, 190, accent="green")
    deck.rect(slide, 44, 277, 820, 174, "white", radius=True)
    deck.text(slide, "What the workflow delivers", 66, 300, 300, 24, 14, "navy", bold=True)
    deck.bullet_list(
        slide,
        (
            "Preserves Vertex Medical Center as a reviewed, enriched 1,003-asset slice.",
            "Creates four hospitals and Admin HQ with deterministic procedural floor plans.",
            "Builds validated lifecycle, inspection, repair, work-order, and dependency relationships.",
            "Uses local AI only for optional narrative text; Python remains authoritative.",
        ),
        66,
        337,
        755,
        size=11.5,
        line_height=30,
    )


def add_three_outputs(deck: Deck) -> None:
    slide = deck.add_slide(
        "One source, two controlled outputs",
        "Data lineage",
        "The original geodatabase is never updated in place.",
    )
    stages = (
        ("01", "Vertex_Assets.gdb", "READ-ONLY SOURCE", "Indoors hierarchy\n1,003 indoor assets\nHistory tables empty", "pale_gold", "gold"),
        ("02", "Vertex_Assets_Enriched.gdb", "REVIEWED VERTEX", "Lifecycle planning\n4,154 inspections\n271 repairs | 501 work orders", "pale_teal", "teal"),
        ("03", "Organizational_Asset_Catalog.gdb", "SIX-FACILITY CATALOG", "Vertex preserved\nFive generated facilities\n4,852 lifecycle assets", "pale_green", "green"),
    )
    x_positions = (47, 349, 651)
    for index, (number, name, label, detail, fill, accent) in enumerate(stages):
        left = x_positions[index]
        deck.rect(slide, left, 162, 259, 236, "white", radius=True)
        deck.circle(slide, left + 18, 180, 42, accent)
        deck.text(slide, number, left + 18, 188, 42, 20, 11, "white", bold=True, align=2)
        deck.pill(slide, label, left + 74, 185, 161, fill, accent)
        deck.text(slide, name, left + 20, 242, 219, 56, 15, "navy", bold=True)
        deck.text(slide, detail, left + 20, 311, 219, 73, 11, "muted")
        if index < 2:
            deck.line(slide, left + 265, 280, left + 293, 280, "coral", weight=2.5, arrow=True)
    deck.text(
        slide,
        "GlobalIDs are remapped inside each output; stable business identifiers preserve cross-build identity.",
        93,
        428,
        773,
        35,
        11,
        "navy",
        bold=True,
        align=2,
    )


def add_vertex_enrichment(deck: Deck) -> None:
    slide = deck.add_slide(
        "Vertex enrichment adds history, not source edits",
        "Reviewed facility",
        "Every planning value is synthetic, deterministic, and internally consistent.",
    )
    deck.rect(slide, 44, 151, 280, 305, "navy", line=None, radius=True)
    deck.text(slide, "1,003", 65, 174, 235, 52, 35, "white", bold=True)
    deck.text(slide, "enriched indoor assets", 67, 226, 230, 23, 12, "pale_teal")
    deck.line(slide, 67, 267, 296, 267, "teal", weight=1.5)
    deck.text(slide, "4,154", 67, 287, 95, 34, 22, "gold", bold=True)
    deck.text(slide, "inspections", 164, 293, 124, 22, 11, "white")
    deck.text(slide, "271", 67, 333, 95, 34, 22, "coral", bold=True)
    deck.text(slide, "repairs", 164, 339, 124, 22, 11, "white")
    deck.text(slide, "501", 67, 379, 95, 34, 22, "pale_green", bold=True)
    deck.text(slide, "work orders", 164, 385, 124, 22, 11, "white")

    deck.text(slide, "What is added", 361, 154, 240, 28, 15, "navy", bold=True)
    deck.bullet_list(
        slide,
        (
            "Lifecycle stage, age, expected life, remaining life, and replacement year",
            "Inspection cadence, next maintenance, condition, criticality, and risk",
            "Purchase cost, replacement estimate, vendor, model, and warranty status",
            "Inspection, repair, and work-order histories with direct asset relationships",
        ),
        365,
        198,
        530,
        size=11,
        line_height=48,
        accent="blue",
    )
    deck.rect(slide, 365, 396, 502, 60, "pale_gold", line=None, radius=True)
    deck.text(slide, "Source geometry and Indoors hierarchy remain unchanged.", 386, 413, 460, 24, 12, "navy", bold=True, align=2)


def add_procedural_generation(deck: Deck) -> None:
    slide = deck.add_slide(
        "Scale without CAD or manual room inventories",
        "Procedural facilities",
        "The floor-plan planner is deterministic, dependency-free, and profile-driven.",
    )
    deck.rect(slide, 44, 151, 526, 305, "white", radius=True)
    deck.text(slide, "Representative generated level", 65, 167, 250, 22, 12, "navy", bold=True)
    deck.rect(slide, 73, 208, 468, 216, "pale_blue", line="navy")
    room_labels = ("EXAM", "OFFICE", "STORAGE", "ELEC", "MECH", "TELECOM")
    room_fills = ("pale_teal", "pale_green", "pale_gold", "pale_coral")
    for row in range(2):
        for column in range(6):
            left = 84 + column * 73
            top = 219 if row == 0 else 346
            deck.rect(slide, left, top, 64, 57, room_fills[(row + column) % 4], line="white", radius=True)
            deck.text(
                slide,
                room_labels[(row * 3 + column) % len(room_labels)],
                left + 3,
                top + 19,
                58,
                18,
                7.5,
                "navy",
                bold=True,
                align=2,
            )
    deck.rect(slide, 84, 287, 429, 45, "coral", line=None, radius=True)
    deck.text(slide, "CENTRAL CORRIDOR", 100, 299, 397, 18, 9.5, "white", bold=True, align=2)
    deck.rect(slide, 515, 287, 15, 45, "gold", line=None)

    deck.rect(slide, 598, 151, 312, 305, "navy", line=None, radius=True)
    deck.text(slide, "Inputs", 622, 172, 250, 24, 14, "white", bold=True)
    deck.bullet_list(
        slide,
        (
            "Facility identity and seed",
            "Hospital or office profile",
            "Vertex spatial reference",
            "Synthetic geographic anchor",
        ),
        624,
        210,
        250,
        size=10.5,
        line_height=34,
        color="white",
        accent="gold",
    )
    deck.text(slide, "Outputs", 622, 352, 250, 24, 14, "white", bold=True)
    deck.text(slide, "Stable levels, rooms, names, use types, capacities, amenities, and asset allocation.", 624, 384, 248, 58, 10.5, "pale_teal")


def add_portfolio(deck: Deck) -> None:
    slide = deck.add_slide(
        "Six facilities form one comparable portfolio",
        "Validated catalog",
        "Indoor asset counts vary with room programs rather than cloned floor plans.",
    )
    max_assets = max(item[3] for item in FACILITIES)
    top = 153
    for index, (name, code, units, assets, exterior, profile) in enumerate(FACILITIES):
        y = top + index * 51
        fill = "teal" if code == "VMC" else ("coral" if code == "AHQ" else "blue")
        deck.text(slide, code, 46, y + 4, 48, 19, 9.5, fill, bold=True)
        deck.text(slide, name, 91, y + 1, 173, 23, 10.5, "ink", bold=True)
        deck.rect(slide, 269, y + 3, 420, 20, "line", line=None, radius=True)
        bar_width = 420 * assets / max_assets
        deck.rect(slide, 269, y + 3, bar_width, 20, fill, line=None, radius=True)
        deck.text(slide, f"{assets:,}", 700, y, 70, 25, 10.5, "navy", bold=True, align=3)
        deck.text(slide, f"{units} units", 781, y, 74, 25, 9, "muted", align=3)
        deck.pill(slide, profile.upper(), 860, y + 1, 68, "pale_green" if profile == "Reviewed" else "pale_blue", "green" if profile == "Reviewed" else "blue")
    deck.line(slide, 269, 464, 689, 464, "line")
    deck.text(slide, "INDOOR ASSETS", 269, 470, 180, 16, 7.5, "muted", bold=True)
    deck.text(slide, "TOTAL 4,852  |  EXTERIOR 72  |  LEVELS 32", 545, 470, 383, 16, 8.5, "navy", bold=True, align=3)


def add_lifecycle(deck: Deck) -> None:
    slide = deck.add_slide(
        "Lifecycle distribution is exact by design",
        "Portfolio planning",
        "Facility mixes vary slightly while the organization-wide 20 / 50 / 30 contract remains exact.",
    )
    deck.text(slide, "4,852 lifecycle assets", 45, 153, 300, 34, 18, "navy", bold=True)
    x = 45
    y = 215
    total_width = 840
    segments = (
        (970, "Recently installed", "green", "pale_green", "20%"),
        (2426, "Within service life", "teal", "pale_teal", "50%"),
        (1456, "Retrofit / replacement", "coral", "pale_coral", "30%"),
    )
    current_x = x
    for count, label, accent, pale, percent in segments:
        width = total_width * count / 4852
        deck.rect(slide, current_x, y, width, 55, accent, line=None)
        deck.text(slide, percent, current_x, y + 13, width, 24, 14, "white", bold=True, align=2)
        current_x += width
    card_x = (45, 329, 613)
    for left, (count, label, accent, pale, percent) in zip(card_x, segments):
        deck.rect(slide, left, 310, 252, 127, "white", radius=True)
        deck.rect(slide, left, 310, 252, 8, accent, line=None, radius=True)
        deck.text(slide, f"{count:,}", left + 20, 335, 210, 35, 24, accent, bold=True)
        deck.text(slide, label, left + 20, 377, 210, 22, 11, "navy", bold=True)
        detail = {
            "Recently installed": "At least 184 days; no more than 2 years or 25% of life",
            "Within service life": "Between 20% and 75% of expected service life",
            "Retrofit / replacement": "Between 80% and 105% of expected service life",
        }[label]
        deck.text(slide, detail, left + 20, 405, 210, 31, 8.5, "muted")


def add_data_coverage(deck: Deck) -> None:
    slide = deck.add_slide(
        "The catalog supports planning and operations",
        "Data coverage",
        "Ten controlled asset classes span clinical, technology, safety, and building systems.",
    )
    categories = (
        ("Clinical + diagnostic", "Patient-facing equipment, monitors, imaging, laboratory", "teal"),
        ("Building + electrical", "HVAC, switchgear, plumbing, emergency power", "blue"),
        ("IT + communications", "Workstations, network racks, conferencing, telecom", "gold"),
        ("Safety + security", "Fire alarm, emergency lighting, cameras, access control", "coral"),
        ("Furniture", "Clinical furniture, office furniture, storage", "green"),
    )
    for index, (name, detail, accent) in enumerate(categories):
        y = 151 + index * 62
        deck.circle(slide, 48, y + 4, 34, accent)
        deck.text(slide, str(index + 1), 48, y + 11, 34, 18, 9.5, "white", bold=True, align=2)
        deck.text(slide, name, 95, y, 230, 24, 11.5, "navy", bold=True)
        deck.text(slide, detail, 95, y + 26, 385, 25, 9.5, "muted")
    deck.rect(slide, 528, 151, 360, 309, "navy", line=None, radius=True)
    deck.text(slide, "Planning fields", 554, 175, 280, 28, 15, "white", bold=True)
    deck.bullet_list(
        slide,
        (
            "Expected life: 4 to 30 years by class",
            "Replacement estimates: $250 to $350,000",
            "Condition: operational, maintenance due, offline repair",
            "Criticality: low through critical, rating 1 to 5",
            "Warranty, annual maintenance cost, overdue days, and risk",
            "Inspection cadence: typically 90 to 730 days",
        ),
        557,
        220,
        298,
        size=10.5,
        line_height=36,
        color="white",
        accent="gold",
    )


def add_relationships(deck: Deck) -> None:
    slide = deck.add_slide(
        "Every asset remains connected to place and history",
        "Relationship architecture",
        "GlobalIDs and GUIDs are authoritative within each output; business IDs remain stable across rebuilds.",
    )
    nodes = (
        ("SITE", 45, 170, 105, "navy"),
        ("FACILITY", 184, 170, 120, "teal"),
        ("LEVEL", 338, 170, 105, "blue"),
        ("UNIT", 477, 170, 105, "gold"),
        ("ASSET POINT", 616, 170, 125, "coral"),
        ("LIFECYCLE", 775, 170, 125, "green"),
    )
    for index, (label, left, top, width, fill) in enumerate(nodes):
        deck.rect(slide, left, top, width, 52, fill, line=None, radius=True)
        deck.text(slide, label, left + 4, top + 16, width - 8, 20, 9.5, "white", bold=True, align=2)
        if index < len(nodes) - 1:
            next_left = nodes[index + 1][1]
            deck.line(slide, left + width + 4, top + 26, next_left - 7, top + 26, "muted", weight=1.8, arrow=True)
    children = (
        ("INSPECTIONS", 505, "pale_teal", "teal"),
        ("REPAIRS", 635, "pale_coral", "coral"),
        ("WORK ORDERS", 745, "pale_gold", "gold"),
        ("DEPENDENCIES", 875, "pale_green", "green"),
    )
    for label, center, pale, accent in children:
        left = center - 50
        deck.rect(slide, left, 325, 100, 48, pale, line=accent, radius=True)
        deck.text(slide, label, left + 3, 341, 94, 18, 8.5, accent, bold=True, align=2)
        source_x = 678 if label in ("INSPECTIONS", "REPAIRS", "WORK ORDERS") else 838
        deck.line(slide, source_x, 225, center, 322, accent, weight=1.4, arrow=True)
    deck.rect(slide, 52, 304, 372, 117, "white", radius=True)
    deck.text(slide, "Dual history linkage", 75, 326, 325, 24, 13, "navy", bold=True)
    deck.text(slide, "History rows carry both lifecycle and asset-point GUIDs. This supports lifecycle analysis and direct related records from floor-aware asset popups.", 75, 361, 325, 53, 10.5, "muted")
    deck.pill(slide, "0 ORPHANS", 390, 446, 128, "pale_green", "green")
    deck.pill(slide, "3 DIRECT HISTORY RELATIONSHIPS", 528, 446, 250, "pale_teal", "teal")


def add_llm_boundary(deck: Deck) -> None:
    slide = deck.add_slide(
        "Local AI adds wording, never authority",
        "Deterministic + LLM boundary",
        "A strict localhost response contract and deterministic fallback keep every record complete.",
    )
    deck.rect(slide, 44, 151, 400, 304, "navy", line=None, radius=True)
    deck.text(slide, "DETERMINISTIC PYTHON", 68, 173, 340, 25, 12, "gold", bold=True)
    deck.bullet_list(
        slide,
        (
            "IDs, hierarchy, and geometry",
            "Asset quantities and classes",
            "Dates, cohorts, conditions, and statuses",
            "Costs, warranty, maintenance, and risk",
            "Relationships and validation",
        ),
        72,
        214,
        330,
        size=11,
        line_height=41,
        color="white",
        accent="gold",
    )
    deck.rect(slide, 478, 151, 432, 304, "white", radius=True)
    deck.text(slide, "OPTIONAL LOCAL NARRATOR", 503, 173, 360, 25, 12, "teal", bold=True)
    telemetry = (
        ("5,912", "opportunities", "navy"),
        ("500", "requests sent", "blue"),
        ("498", "accepted", "green"),
        ("5,414", "fallbacks", "coral"),
    )
    for index, (value, label, accent) in enumerate(telemetry):
        left = 503 + (index % 2) * 190
        top = 216 + (index // 2) * 79
        deck.text(slide, value, left, top, 155, 31, 20, accent, bold=True)
        deck.text(slide, label, left, top + 33, 155, 19, 9.5, "muted")
    deck.line(slide, 503, 376, 864, 376, "line")
    deck.text(slide, "Contract", 503, 390, 75, 20, 10, "navy", bold=True)
    deck.text(slide, "localhost only  |  exactly one text field  |  500 characters max", 584, 390, 281, 31, 9, "muted")
    deck.text(slide, "2 transport fallbacks  |  5,412 budget fallbacks  |  0 invalid responses", 503, 427, 361, 21, 8.5, "coral", bold=True)


def add_validation(deck: Deck) -> None:
    slide = deck.add_slide(
        "Validation makes the catalog demonstrably coherent",
        "Quality controls",
        "The manifest is the run audit record; tests protect deterministic behavior and promotion recovery.",
    )
    deck.rect(slide, 44, 151, 249, 306, "green", line=None, radius=True)
    deck.text(slide, "0", 65, 177, 205, 84, 58, "white", bold=True, align=2)
    deck.text(slide, "orphan references", 67, 263, 201, 26, 13, "white", bold=True, align=2)
    deck.line(slide, 74, 313, 263, 313, "pale_green", weight=1.2)
    deck.text(slide, "59", 82, 335, 70, 44, 28, "pale_gold", bold=True)
    deck.text(slide, "non-schema tests", 151, 342, 108, 23, 10.5, "white")
    deck.text(slide, "11", 82, 393, 70, 36, 24, "pale_teal", bold=True)
    deck.text(slide, "notebook code cells compile", 151, 393, 108, 44, 9.5, "white")
    deck.text(slide, "Validated contracts", 333, 154, 280, 27, 15, "navy", bold=True)
    deck.bullet_list(
        slide,
        (
            "Exact Site, Facility, Level, Unit, and asset identities",
            "Complete parentage and relationship GUIDs",
            "Generated geometry containment and room-program continuity",
            "Inspection date bounds and latest-inspection consistency",
            "Exact lifecycle cohorts and imported Vertex preservation",
            "Lock-safe staged promotion with reusable validated recovery",
        ),
        338,
        201,
        550,
        size=11,
        line_height=41,
        accent="green",
    )


def add_operator_workflow(deck: Deck) -> None:
    slide = deck.add_slide(
        "The operator path is controlled and reviewable",
        "Run sequence",
        "Production schema and catalog work runs in the ArcGIS Pro 3.7.2 notebook kernel.",
    )
    steps = (
        ("1", "Configure paths", "Repository and source GDB"),
        ("2", "Preflight", "Environment, source, Ollama"),
        ("3", "Enrich Vertex", "Create separate output"),
        ("4", "Review", "Manifest and relationships"),
        ("5", "Build catalog", "Stage six facilities"),
        ("6", "Validate", "Counts, geometry, GUIDs"),
        ("7", "Promote", "Atomic rename to canonical"),
    )
    for index, (number, title, detail) in enumerate(steps):
        if index < 4:
            left = 47 + index * 220
            top = 166
        else:
            left = 157 + (index - 4) * 220
            top = 324
        deck.circle(slide, left, top, 42, "teal" if index < 5 else "green")
        deck.text(slide, number, left, top + 10, 42, 20, 11, "white", bold=True, align=2)
        deck.text(slide, title, left + 56, top + 1, 145, 24, 11, "navy", bold=True)
        deck.text(slide, detail, left + 56, top + 29, 145, 38, 9, "muted")
        if index in (0, 1, 2, 4, 5):
            deck.line(slide, left + 199, top + 20, left + 215, top + 20, "coral", weight=1.7, arrow=True)
    deck.rect(slide, 47, 455, 862, 32, "pale_gold", line=None, radius=True)
    deck.text(slide, "Close layers, standalone tables, attribute tables, and Catalog views that reference the old catalog before promotion.", 62, 462, 832, 18, 9.5, "navy", bold=True, align=2)


def add_promotion(deck: Deck) -> None:
    slide = deck.add_slide(
        "Staging protects the previous catalog",
        "Promotion and recovery",
        "A validated build is reused after a lock failure; expensive generation does not repeat.",
    )
    stages = (
        ("BUILD", "_building.gdb", "Generate hierarchy, assets, and history", "blue"),
        ("VALIDATE", "manifest.json", "Check counts, geometry, preservation, and relationships", "teal"),
        ("PROMOTE", "canonical .gdb", "Atomically rename validated workspace", "green"),
    )
    for index, (label, artifact, detail, accent) in enumerate(stages):
        left = 49 + index * 292
        deck.rect(slide, left, 170, 245, 156, "white", radius=True)
        deck.rect(slide, left, 170, 245, 9, accent, line=None, radius=True)
        deck.pill(slide, label, left + 18, 193, 91, f"pale_{accent}" if accent != "blue" else "pale_blue", accent)
        deck.text(slide, artifact, left + 18, 234, 206, 28, 14, "navy", bold=True)
        deck.text(slide, detail, left + 18, 274, 206, 40, 9.5, "muted")
        if index < 2:
            deck.line(slide, left + 248, 248, left + 283, 248, "coral", weight=2.2, arrow=True)
    deck.line(slide, 754, 328, 754, 375, "coral", weight=2.2, arrow=True)
    deck.rect(slide, 503, 378, 410, 73, "pale_coral", line="coral", radius=True)
    deck.text(slide, "LOCK DETECTED", 523, 393, 122, 19, 9, "coral", bold=True)
    deck.text(slide, "Keep the validated staging catalog, close old references, and rerun the final workflow cell.", 653, 389, 238, 46, 9.5, "navy")
    deck.rect(slide, 49, 367, 404, 84, "navy", line=None, radius=True)
    deck.text(slide, "Recovery result", 71, 384, 145, 22, 11.5, "gold", bold=True)
    deck.text(slide, "The successful run reused staging and promoted in seconds rather than rebuilding the 27-minute catalog.", 71, 411, 354, 32, 9.5, "white")


def add_use_cases(deck: Deck) -> None:
    slide = deck.add_slide(
        "One catalog supports several demonstration stories",
        "Application patterns",
        "Publish selected layers and relationship classes together for the richest experience.",
    )
    cards = (
        ("PORTFOLIO", "Dashboards", "Compare facilities, lifecycle stages, condition, cost, and risk.", "teal", "pale_teal"),
        ("FLOOR-AWARE", "Related records", "Open inspections, repairs, and work orders from an indoor asset popup.", "blue", "pale_blue"),
        ("CONNECTED", "Knowledge graph", "Explore assets, locations, lifecycle history, and supporting systems.", "coral", "pale_coral"),
        ("REPEATABLE", "Training + testing", "Use stable synthetic data without production credentials or enterprise IDs.", "green", "pale_green"),
    )
    positions = ((45, 155), (480, 155), (45, 318), (480, 318))
    for (eyebrow, title, detail, accent, pale), (left, top) in zip(cards, positions):
        deck.rect(slide, left, top, 393, 135, "white", radius=True)
        deck.rect(slide, left, top, 12, 135, accent, line=None, radius=True)
        deck.pill(slide, eyebrow, left + 27, top + 19, 110, pale, accent)
        deck.text(slide, title, left + 27, top + 54, 332, 28, 16, "navy", bold=True)
        deck.text(slide, detail, left + 27, top + 88, 332, 37, 10, "muted")


def add_boundaries(deck: Deck) -> None:
    slide = deck.add_slide(
        "Clear boundaries keep the demonstration honest",
        "Scope",
        "The catalog is designed for evaluation and storytelling, not as an asserted facility inventory.",
    )
    deck.rect(slide, 44, 151, 408, 306, "pale_green", line=None, radius=True)
    deck.text(slide, "IN SCOPE", 67, 174, 160, 24, 13, "green", bold=True)
    deck.bullet_list(
        slide,
        (
            "Synthetic lifecycle and history records",
            "Procedural hospital and office layouts",
            "Dashboard and related-record workflows",
            "Replacement, warranty, risk, and maintenance planning",
            "Graph-ready system dependencies",
        ),
        70,
        215,
        340,
        size=11,
        line_height=43,
        accent="green",
    )
    deck.rect(slide, 485, 151, 425, 306, "pale_coral", line=None, radius=True)
    deck.text(slide, "OUT OF SCOPE", 509, 174, 190, 24, 13, "coral", bold=True)
    deck.bullet_list(
        slide,
        (
            "Claims about real equipment inventory",
            "Reconstruction of actual building plans",
            "Utility-network asset modeling",
            "Live enterprise records or credentials",
            "Hosted forms, portal IDs, or image binaries",
        ),
        512,
        215,
        350,
        size=11,
        line_height=43,
        accent="coral",
    )


def add_close(deck: Deck) -> None:
    slide = deck.presentation.Slides.Add(deck.presentation.Slides.Count + 1, 12)
    deck.rect(slide, 0, 0, SLIDE_WIDTH, SLIDE_HEIGHT, "navy", line=None)
    deck.text(slide, "READY FOR DEMONSTRATION", 52, 48, 510, 23, 11, "gold", bold=True)
    deck.text(slide, "A coherent catalog with\nroom to become a product", 52, 93, 560, 102, 31, "white", bold=True)
    deck.text(slide, "Next actions", 53, 234, 210, 29, 15, "pale_teal", bold=True)
    deck.bullet_list(
        slide,
        (
            "Publish asset and history layers with relationship classes",
            "Configure floor awareness and related-record popups",
            "Build portfolio and replacement-planning dashboards",
            "Model system dependencies as graph relationships",
            "Decide whether enrichment becomes a toolbox tool",
        ),
        57,
        276,
        520,
        size=11.5,
        line_height=37,
        color="white",
        accent="gold",
    )
    deck.rect(slide, 641, 62, 263, 407, "white", line=None, radius=True)
    deck.text(slide, "Validated result", 667, 87, 210, 27, 14, "navy", bold=True)
    metrics = (("6", "facilities"), ("1,025", "units"), ("4,852", "assets"), ("0", "orphans"))
    for index, (value, label) in enumerate(metrics):
        top = 137 + index * 70
        accent = ("teal", "blue", "coral", "green")[index]
        deck.text(slide, value, 668, top, 103, 36, 24, accent, bold=True)
        deck.text(slide, label, 774, top + 8, 100, 22, 10.5, "muted")
        if index < 3:
            deck.line(slide, 668, top + 52, 877, top + 52, "line")
    deck.text(slide, "Documentation and source", 667, 427, 210, 18, 8.5, "muted", bold=True)
    deck.text(slide, "github.com/JonGabHall/demo-data-generator", 667, 447, 210, 30, 8.5, "teal")
    deck.text(slide, "Synthetic demonstration data  |  October 1, 2026", 53, 505, 520, 17, 8, "pale_teal")


def build_presentation(output: Path, pdf_output: Path, preview_dir: Path | None = None) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf_output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    pdf_output.unlink(missing_ok=True)
    if preview_dir:
        shutil.rmtree(preview_dir, ignore_errors=True)
        preview_dir.mkdir(parents=True, exist_ok=True)

    application = win32com.client.DispatchEx("PowerPoint.Application")
    application.Visible = True
    application.DisplayAlerts = 0
    presentation = application.Presentations.Add()
    try:
        deck = Deck(presentation)
        add_title_slide(deck)
        add_executive_summary(deck)
        add_three_outputs(deck)
        add_vertex_enrichment(deck)
        add_procedural_generation(deck)
        add_portfolio(deck)
        add_lifecycle(deck)
        add_data_coverage(deck)
        add_relationships(deck)
        add_llm_boundary(deck)
        add_validation(deck)
        add_operator_workflow(deck)
        add_promotion(deck)
        add_use_cases(deck)
        add_boundaries(deck)
        add_close(deck)

        presentation.SaveAs(str(output.resolve()), 24)
        slide_count = presentation.Slides.Count
        presentation.Close()
        presentation = application.Presentations.Open(
            str(output.resolve()),
            False,
            False,
            False,
        )
        presentation.SaveAs(str(pdf_output.resolve()), 32)
        if preview_dir:
            for index in range(1, slide_count + 1):
                presentation.Slides(index).Export(
                    str((preview_dir / f"slide-{index:02d}.png").resolve()),
                    "PNG",
                    1600,
                    900,
                )
        return slide_count
    finally:
        try:
            presentation.Close()
        except Exception:
            pass
        try:
            application.Quit()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    repository = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--output",
        type=Path,
        default=repository / "docs" / "Indoors_Asset_Catalog_Workflow.pptx",
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=repository / "docs" / "Indoors_Asset_Catalog_Workflow.pdf",
    )
    parser.add_argument("--preview-dir", type=Path)
    arguments = parser.parse_args()

    if sys.platform != "win32":
        raise RuntimeError("PowerPoint COM generation requires Windows and Microsoft PowerPoint.")
    slide_count = build_presentation(arguments.output, arguments.pdf, arguments.preview_dir)
    print(f"Created {arguments.output} with {slide_count} slides")
    print(f"Created {arguments.pdf}")
    if arguments.preview_dir:
        print(f"Exported previews to {arguments.preview_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
