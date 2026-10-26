#!/usr/bin/env python3
"""Render the independent Cybertwip Earth--Mars study to HTML and PDF.

Dependencies: Markdown, reportlab. No network requests or remote page assets.
Telemetry is optional until the application exporter supplies a real run.
The full JSON/CSV inputs remain intact; document plots are display summaries.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import io
import json
import math
import os
import re
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import escape
from pathlib import Path

import markdown
from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle, XPreformatted


HERE = Path(__file__).resolve().parent
PALETTE = ("#155e82", "#c36a18", "#20865c", "#8d4f91")
CSS = """
:root{color-scheme:light;--ink:#172a3a;--line:#cdd9e2;--navy:#102d43}
*{box-sizing:border-box}body{margin:0;color:var(--ink);background:#e9eef3;
font:16px/1.65 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1120px;
margin:28px auto;background:white;padding:48px 60px;box-shadow:0 8px 35px #102d4315}
.eyebrow{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#486478}
h1{font-size:34px;line-height:1.2;color:var(--navy);margin:16px 0 24px}h2{font-size:24px;
line-height:1.3;color:var(--navy);margin:44px 0 18px;border-bottom:2px solid var(--line);padding-bottom:8px}
h3{font-size:19px;margin-top:28px}p{margin:13px 0}a{color:#075d85}table{border-collapse:collapse;
width:100%;font-size:13px;line-height:1.45;margin:22px 0;overflow-wrap:anywhere}th,td{padding:10px 12px;
border:1px solid var(--line);vertical-align:top}th{background:#e9f1f6;text-align:left}tr:nth-child(even){background:#f8fafb}
pre{font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#f0f4f7;
padding:18px;border-left:4px solid #628aa1;white-space:pre-wrap;overflow-wrap:anywhere}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.88em}
figure{margin:26px 0;border:1px solid var(--line);padding:18px;break-inside:avoid}
figure svg{width:100%;height:auto}figcaption{font-size:12px;color:#4a6577;margin-top:10px}
.status{padding:14px 18px;border:1px solid #a5bdcc;background:#edf5f9;margin:20px 0}
.missing{border-color:#cfa775;background:#fff6ea}details{background:#f2f6f9;padding:12px 18px}
small,.manifest{font-size:11px;color:#536b7b}.manifest{overflow-wrap:anywhere}ol,ul{padding-left:25px}
@media(max-width:760px){main{padding:24px 18px;margin:0}h1{font-size:27px}table{font-size:11px}
th,td{padding:7px 6px}}@media print{body{background:white}main{padding:0;margin:0;box-shadow:none;
max-width:none}details{display:none}h2{break-after:avoid}pre,table{font-size:10px}a{text-decoration:none}
figure{break-inside:avoid}@page{size:A4;margin:17mm}}
"""


def finite(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def field(sample: dict, *names: str):
    for name in names:
        value = sample
        for part in name.split("."):
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = value[part]
        if value is not None:
            return value
    return None


def number(sample: dict, *names: str) -> float | None:
    return finite(field(sample, *names))


def vector(value) -> tuple[float, float, float] | None:
    if isinstance(value, dict):
        value = [value.get(k, value.get(k.lower())) for k in ("X", "Y", "Z")]
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    values = tuple(finite(v) for v in value[:3])
    return values if all(v is not None for v in values) else None


def fmt(value, places=3) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    num = finite(value)
    if num is not None:
        if abs(num) >= 1e7 or 0 < abs(num) < 1e-4:
            return f"{num:.{places}e}"
        return f"{num:,.{places}f}"
    return "not supplied" if value is None else str(value)


def table(headers: list[str], rows: list[list]) -> str:
    html = "<table><thead><tr>" + "".join(f"<th>{escape(str(h))}</th>" for h in headers) + "</tr></thead><tbody>"
    for row in rows:
        html += "<tr>" + "".join(f"<td>{escape(fmt(cell) if not isinstance(cell, str) else cell)}</td>" for cell in row) + "</tr>"
    return html + "</tbody></table>"


@dataclass
class Chart:
    identifier: str
    title: str
    x_label: str
    y_label: str
    series: list[tuple[str, list[tuple[float, float]]]]
    caption: str

    def geometry(self):
        width, height = 760, 270
        left, right, bottom, top = 78, 20, 48, 48
        values = [p for _, points in self.series for p in points]
        x0, x1 = min(p[0] for p in values), max(p[0] for p in values)
        y0, y1 = min(p[1] for p in values), max(p[1] for p in values)
        if x1 <= x0:
            x1 = x0 + 1
        padding = (y1 - y0) * .06 if y1 > y0 else max(1, abs(y0) * .05)
        y0, y1 = y0 - padding, y1 + padding

        def project(point):
            x = left + (point[0] - x0) / (x1 - x0) * (width - left - right)
            y = bottom + (point[1] - y0) / (y1 - y0) * (height - top - bottom)
            return x, y

        return width, height, left, right, bottom, top, x0, x1, y0, y1, project

    @staticmethod
    def tick(value: float) -> str:
        return f"{value:.2g}" if abs(value) >= 10000 or 0 < abs(value) < .01 else f"{value:.3g}"

    def svg(self) -> str:
        width, height, left, right, bottom, top, x0, x1, y0, y1, project = self.geometry()
        parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(self.title)}">',
                 '<rect width="100%" height="100%" fill="white"/>',
                 f'<text x="{left}" y="20" font-size="15" font-weight="600" fill="#102d43">{escape(self.title)}</text>']
        for i in range(5):
            fraction = i / 4
            x = left + fraction * (width - left - right)
            y = bottom + fraction * (height - top - bottom)
            parts += [f'<line x1="{x}" y1="{height-bottom}" x2="{x}" y2="{top}" stroke="#e2e8ed"/>',
                      f'<line x1="{left}" y1="{height-y}" x2="{width-right}" y2="{height-y}" stroke="#e2e8ed"/>',
                      f'<text x="{x}" y="{height-bottom+18}" font-size="11" text-anchor="middle">{self.tick(x0+fraction*(x1-x0))}</text>',
                      f'<text x="{left-8}" y="{height-y+4}" font-size="11" text-anchor="end">{self.tick(y0+fraction*(y1-y0))}</text>']
        for i, (label, points) in enumerate(self.series):
            color = PALETTE[i % len(PALETTE)]
            coords = " ".join(f"{project(p)[0]:.3f},{height-project(p)[1]:.3f}" for p in points)
            parts += [f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="1.7"/>',
                      f'<text x="{left+i*180}" y="36" font-size="11" fill="{color}">{escape(label)}</text>']
        parts += [f'<text x="{(left+width-right)/2}" y="{height-4}" text-anchor="middle" font-size="11">{escape(self.x_label)}</text>',
                  f'<text x="12" y="{top-10}" font-size="10">{escape(self.y_label)}</text>', '</svg>']
        return "".join(parts)

    def drawing(self, available_width: float) -> Drawing:
        width, height, left, right, bottom, top, x0, x1, y0, y1, project = self.geometry()
        drawing = Drawing(width, height)
        drawing.add(Rect(0, 0, width, height, fillColor=colors.white, strokeColor=None))
        drawing.add(String(left, height - 20, self.title, fontName="StudyBold", fontSize=13, fillColor=colors.HexColor("#102d43")))
        for i in range(5):
            fraction = i / 4
            x = left + fraction * (width-left-right)
            y = bottom + fraction * (height-top-bottom)
            drawing.add(Line(x, bottom, x, height-top, strokeColor=colors.HexColor("#e2e8ed")))
            drawing.add(Line(left, y, width-right, y, strokeColor=colors.HexColor("#e2e8ed")))
            drawing.add(String(x, bottom-18, self.tick(x0+fraction*(x1-x0)), fontName="Study", fontSize=10, textAnchor="middle"))
            drawing.add(String(left-8, y-3, self.tick(y0+fraction*(y1-y0)), fontName="Study", fontSize=10, textAnchor="end"))
        for i, (label, points) in enumerate(self.series):
            color = colors.HexColor(PALETTE[i % len(PALETTE)])
            drawing.add(PolyLine([coordinate for point in points for coordinate in project(point)], strokeColor=color, strokeWidth=1.4, fillColor=None))
            drawing.add(String(left+i*180, height-36, label, fontName="Study", fontSize=10, fillColor=color))
        drawing.add(String((left+width-right)/2, 4, self.x_label, textAnchor="middle", fontName="Study", fontSize=10))
        drawing.add(String(12, height-top+10, self.y_label, fontName="Study", fontSize=9))
        scale = available_width / width
        drawing.scale(scale, scale)
        drawing.width, drawing.height = width * scale, height * scale
        return drawing


def downsample(points: list[tuple[float, float]], maximum=750) -> list[tuple[float, float]]:
    if len(points) <= maximum:
        return points
    indices = {round(i * (len(points) - 1) / (maximum - 1)) for i in range(maximum)}
    return [points[i] for i in sorted(indices)]


def telemetry_section(path: Path, csv_path: Path, relative_root: Path) -> tuple[str, list[Chart], dict]:
    info = {"ingested": False, "path": str(path), "csv_path": str(csv_path)}
    heading = '<section id="application-evidence"><h2>15. Ingested application telemetry evidence</h2>'
    if not path.exists():
        return heading + '<div class="status missing">No complete application run has been ingested. The report currently contains mathematical reference cases only. The renderer can be rerun with the exported JSON and CSV.</div></section>', [], info
    packet = json.loads(path.read_text())
    if not isinstance(packet, dict):
        raise ValueError("Telemetry must be an object with samples and run metadata")
    samples = packet.get("samples", [])
    events = packet.get("events", [])
    if not isinstance(samples, list) or not all(isinstance(s, dict) for s in samples):
        raise ValueError("Telemetry samples must be a list of objects")
    if not isinstance(events, list):
        events = []
    run, profile = packet.get("run", {}), packet.get("vehicle_profile", {})
    run = run if isinstance(run, dict) else {}
    profile = profile if isinstance(profile, dict) else {}
    records = [(s, number(s, "sim_seconds", "simulation_seconds", "elapsed_seconds", "time_s")) for s in samples]
    valid = [(s, t) for s, t in records if t is not None]
    warnings = []
    if len(valid) != len(samples):
        warnings.append(f"{len(samples)-len(valid)} samples have no finite simulation time and cannot be plotted.")
    monotonic = all(valid[i][1] >= valid[i-1][1] for i in range(1, len(valid)))
    if not monotonic:
        warnings.append("Sample times are not monotonic in the source file; plots are sorted for display only.")
    valid.sort(key=lambda item: item[1])
    csv_count = None
    if csv_path.exists():
        with csv_path.open(newline="") as stream:
            csv_count = sum(1 for _ in csv.DictReader(stream))
        if csv_count != len(samples):
            warnings.append(f"CSV has {csv_count} data rows while JSON has {len(samples)} samples; investigate the difference.")
    else:
        warnings.append("The CSV attachment was not supplied.")
    phases = []
    for sample, _ in valid:
        phase = str(sample.get("phase", "unknown"))
        if phase not in phases:
            phases.append(phase)
    success = run.get("final_phase") == "LANDED" and finite(run.get("landings")) is not None and finite(run.get("landings")) > 0
    info.update({"ingested": True, "samples": len(samples), "events": len(events), "csv_data_rows": csv_count,
                 "source_time_monotonic": monotonic, "observed_phases": phases, "exporter_reports_landing": success,
                 "warnings": warnings, "schema_version": packet.get("schema_version")})
    vehicle_id = str(profile.get("id", profile.get("name", "unidentified vehicle")))
    html = heading + '<div class="status">'
    html += f'Ingested <strong>{len(samples):,} state records</strong> and <strong>{len(events):,} event records</strong> for <strong>{escape(vehicle_id)}</strong>. '
    html += "The exporter reports a completed landing." if success else "A completed landing is not established by the supplied run metadata."
    html += ' These are simulated records, not observed Starship flight telemetry.</div>'
    if warnings:
        html += '<div class="status missing">' + '<br/>'.join(escape(w) for w in warnings) + '</div>'
    links = [(os.path.relpath(path, relative_root), "Complete JSON state/event attachment")]
    if csv_path.exists():
        links.append((os.path.relpath(csv_path, relative_root), "Complete CSV state attachment"))
    html += '<p>' + ' · '.join(f'<a href="{escape(link)}">{escape(label)}</a>' for link, label in links) + '</p>'
    html += '<h3>15.1 Vehicle and run metadata</h3>'
    rows = [["schema_version", packet.get("schema_version")]]
    rows += [["vehicle." + str(k), v] for k, v in profile.items()]
    rows += [["run." + str(k), v] for k, v in run.items()]
    html += table(["Exporter field", "Recorded value"], rows)
    html += '<p>Metadata above is reproduced as supplied. Unknown inputs remain unknown. In particular, EX-1 transfer-Isp and mass values must not be relabeled as SpaceX Starship specifications.</p>'
    html += '<h3>15.2 Recorded phase spans</h3>'
    phase_rows = []
    for phase in phases:
        matching = [(s, t) for s, t in valid if str(s.get("phase", "unknown")) == phase]
        first, last = matching[0], matching[-1]
        phase_rows.append([phase, len(matching), fmt(first[1]/86400, 6), fmt(last[1]/86400, 6),
                           fmt(number(first[0], "fuel_kg", "propellant_kg")), fmt(number(last[0], "fuel_kg", "propellant_kg"))])
    html += table(["Phase", "Records", "First day", "Last day", "First fuel kg", "Last fuel kg"], phase_rows)
    html += '<p>Spans above bound recorded samples, not exact event transition times; exact transition messages and times are retained in the event attachment. Sparse or missing phases are reported rather than synthesized.</p>'
    charts = []

    def series(*names, factor=1, selection=None):
        output = []
        for sample, t in valid:
            if selection and not selection(sample):
                continue
            value = number(sample, *names)
            if value is not None:
                output.append((t / 86400, value * factor))
        return downsample(output)

    fuel, mass = series("fuel_kg", "propellant_kg", factor=.001), series("mass_kg", factor=.001)
    if len(fuel) >= 2 and len(mass) >= 2:
        charts.append(Chart("mass", vehicle_id + " mass and propellant", "Simulation day", "tonnes", [("Total mass", mass), ("Propellant", fuel)],
                            "Full mission; lines connect recorded samples. Burn discontinuities and jettison events must be interpreted using the event history."))
    speed_points, xy = [], []
    for sample, t in valid:
        velocity = vector(field(sample, "velocity_m_s", "heliocentric_velocity_m_s"))
        position = vector(field(sample, "position_m", "heliocentric_position_m"))
        if velocity:
            speed_points.append((t / 86400, math.sqrt(sum(v*v for v in velocity)) / 1000))
        if position:
            xy.append((position[0] / 149597870700, position[1] / 149597870700))
    if len(speed_points) >= 2:
        charts.append(Chart("speed", vehicle_id + " heliocentric speed", "Simulation day", "km/s", [("Speed", downsample(speed_points))],
                            "Position/velocity units and heliocentric interpretation follow the exporter contract; this is not speed relative to the Martian surface."))
    if len(xy) >= 2:
        charts.append(Chart("trajectory", vehicle_id + " trajectory projection", "Heliocentric X (AU)", "Y (AU)", [("Recorded path", downsample(xy))],
                            "Projection onto two exporter inertial axes. Vertical scales follow axis ranges; this plot does not flatten the integrated 3D state."))
    terminal = [(s, t) for s, t in valid if any(word in str(s.get("phase", "")).upper() for word in ("DESCENT", "LANDING", "LANDED"))]
    if terminal:
        first_time = terminal[0][1]
        points = [(t-first_time, number(s, "altitude_m")) for s, t in terminal]
        points = [p for p in points if p[1] is not None]
        if len(points) >= 2:
            charts.append(Chart("terminal", vehicle_id + " terminal altitude", "Seconds from first terminal record", "metres", [("Altitude", downsample(points))],
                                "Terminal/landed samples only. Height definition and terrain datum follow the exporter; contact outcome is read separately from run/events."))
    rf_margin = series("rf.margin_db", "rf_margin_db")
    if len(rf_margin) >= 2:
        charts.append(Chart("rf-margin", vehicle_id + " reported RF margin", "Simulation day", "dB", [("Link margin", rf_margin)],
                            "Link margin is conditional on the exporter RF assumptions. Occultation, clear-path flags and receiver settings remain in the complete records."))
    html += '<h3>15.3 Representative profile plots</h3>'
    for chart in charts:
        html += f'<figure id="chart-{chart.identifier}">{chart.svg()}<figcaption>{escape(chart.caption)}</figcaption></figure>'
    if not charts:
        html += '<p>No sufficient finite field pairs were available for profile plots.</p>'
    html += '<h3>15.4 Event history and touchdown samples</h3>'
    event_rows = []
    for event in events[:200]:
        if isinstance(event, dict):
            event_rows.append([event.get("utc", "not supplied"), fmt(number(event, "sim_seconds", "elapsed_seconds")),
                               event.get("kind", event.get("phase", "event")), event.get("message", "")])
    if event_rows:
        html += table(["Simulated UTC", "Seconds", "Kind", "Recorded message"], event_rows)
    if len(events) > 200:
        html += f'<p>The document displays the first 200 events; all {len(events):,} events are retained in the JSON attachment.</p>'
    final_rows = []
    for sample, t in valid[-8:]:
        final_rows.append([fmt(t, 6), sample.get("phase", "unknown"), fmt(number(sample, "altitude_m")),
                           fmt(number(sample, "vertical_m_s", "vertical_speed_m_s")),
                           fmt(number(sample, "lateral_m_s", "lateral_speed_m_s")),
                           fmt(number(sample, "fuel_kg")), fmt(number(sample, "contact_force_n", "leg_force_n"))])
    if final_rows:
        html += table(["Seconds", "Phase", "Altitude m", "Vertical m/s", "Lateral m/s", "Fuel kg", "Contact N"], final_rows)
    html += '<p>All source rows, including full position/velocity, attitude and RF fields, remain attached. This report does not replace a covariance/dispersion analysis, independent vehicle-model validation, or operational flight qualification.</p></section>'
    return html, charts, info


def pdf_fonts():
    candidates = [
        ("Study", "/System/Library/Fonts/Supplemental/Arial.ttf"),
        ("StudyBold", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ("StudyMono", "/System/Library/Fonts/Supplemental/Courier New.ttf"),
    ]
    if all(Path(p).exists() for _, p in candidates):
        for name, path in candidates:
            pdfmetrics.registerFont(TTFont(name, path))
        pdfmetrics.registerFontFamily("Study", normal="Study", bold="StudyBold", italic="Study", boldItalic="StudyBold")
    else:
        for name, base in (("Study", "Helvetica"), ("StudyBold", "Helvetica-Bold"), ("StudyMono", "Courier")):
            pdfmetrics.registerFont(pdfmetrics.Font(name, base, "WinAnsiEncoding"))
        pdfmetrics.registerFontFamily("Study", normal="Study", bold="StudyBold", italic="Study", boldItalic="StudyBold")


def inline(element) -> str:
    output = escape(element.text or "")
    for child in element:
        content = inline(child)
        if child.tag in ("strong", "b"):
            output += "<b>" + content + "</b>"
        elif child.tag in ("em", "i"):
            output += "<i>" + content + "</i>"
        elif child.tag == "code":
            output += '<font name="StudyMono" size="8">' + content + '</font>'
        elif child.tag == "a":
            output += '<a href="' + escape(child.get("href", ""), quote=True) + '" color="#075d85">' + content + '</a>'
        elif child.tag == "br":
            output += "<br/>"
        else:
            output += content
        output += escape(child.tail or "")
    return output


def render_pdf(body: str, charts: list[Chart], path: Path):
    pdf_fonts()
    stylesheet = getSampleStyleSheet()
    normal = ParagraphStyle("StudyBody", parent=stylesheet["BodyText"], fontName="Study", fontSize=9.3,
                            leading=13.6, textColor=colors.HexColor("#172a3a"), spaceAfter=8, alignment=TA_LEFT)
    styles = {"p": normal,
              "h1": ParagraphStyle("StudyH1", parent=normal, fontName="StudyBold", fontSize=23, leading=28, spaceAfter=20, spaceBefore=8),
              "h2": ParagraphStyle("StudyH2", parent=normal, fontName="StudyBold", fontSize=15, leading=20, spaceBefore=20, spaceAfter=10, keepWithNext=True),
              "h3": ParagraphStyle("StudyH3", parent=normal, fontName="StudyBold", fontSize=11, leading=16, spaceBefore=12, spaceAfter=8, keepWithNext=True),
              "cell": ParagraphStyle("StudyCell", parent=normal, fontSize=7.3, leading=10.4, spaceAfter=0, wordWrap="CJK"),
              "small": ParagraphStyle("StudySmall", parent=normal, fontSize=7.5, leading=10.5),
              "code": ParagraphStyle("StudyCode", parent=normal, fontName="StudyMono", fontSize=7.2, leading=10.4, leftIndent=8, rightIndent=5,
                                      borderColor=colors.HexColor("#b5cad8"), borderWidth=.6, borderPadding=7, backColor=colors.HexColor("#f0f4f7"))}
    width = A4[0] - 32 * mm
    registry = {"chart-" + c.identifier: c for c in charts}
    root = ET.fromstring("<main>" + body + "</main>")
    story = []

    def walk(element):
        tag = element.tag.split("}")[-1]
        if tag in ("h1", "h2", "h3", "p"):
            story.append(Paragraph(inline(element), styles[tag]))
        elif tag == "pre":
            content = "".join(element.itertext()).strip("\n")
            lines = []
            for line in content.splitlines():
                lines.extend(textwrap.wrap(line, width=103, replace_whitespace=False, drop_whitespace=False) or [""])
            story.append(XPreformatted(escape("\n".join(lines)), styles["code"]))
            story.append(Spacer(1, 6))
        elif tag == "table":
            rows = []
            headers = 0
            for row in element.iter("tr"):
                cells = list(row)
                if not cells:
                    continue
                rows.append([Paragraph(("<b>" + inline(cell) + "</b>") if cell.tag == "th" else inline(cell), styles["cell"]) for cell in cells])
                if any(cell.tag == "th" for cell in cells):
                    headers += 1
            if rows:
                columns = max(len(row) for row in rows)
                for row in rows:
                    row += [Paragraph("", styles["cell"])] * (columns-len(row))
                if columns == 2:
                    ratios = [.39, .61]
                elif columns == 3:
                    ratios = [.24, .38, .38]
                elif columns == 4:
                    ratios = [.25, .17, .20, .38]
                else:
                    ratios = [1 / columns] * columns
                flow = LongTable(rows, colWidths=[width*r for r in ratios], repeatRows=min(headers, 1), hAlign="LEFT")
                flow.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#cdd9e2")),
                                          ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9f1f6")),
                                          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafb")]),
                                          ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                          ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 6),
                                          ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
                story.extend([flow, Spacer(1, 9)])
        elif tag in ("ol", "ul"):
            for index, item in enumerate(element.findall("li"), 1):
                prefix = str(index) + ". " if tag == "ol" else "• "
                story.append(Paragraph(prefix + inline(item), normal))
        elif tag == "figure" and element.get("id") in registry:
            chart = registry[element.get("id")]
            story.append(KeepTogether([chart.drawing(width), Paragraph(chart.caption, styles["small"]), Spacer(1, 10)]))
        elif tag == "div" and element.get("class", "").startswith("status"):
            story.append(Paragraph(inline(element), normal))
        elif tag in ("svg", "figcaption"):
            return
        else:
            for child in element:
                walk(child)

    for child in root:
        walk(child)

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.white)
        canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
        canvas.setStrokeColor(colors.HexColor("#cdd9e2"))
        canvas.line(16*mm, A4[1]-12*mm, A4[0]-16*mm, A4[1]-12*mm)
        canvas.setFont("Study", 7)
        canvas.setFillColor(colors.HexColor("#536b7b"))
        canvas.drawString(16*mm, A4[1]-9*mm, "EARTH–MARS STUDY • INDEPENDENT DRAFT PREPARED FOR CYBERTWIP")
        canvas.drawString(16*mm, 10*mm, "Proposed addressees: SpaceX and NASA • No agency endorsement claimed")
        canvas.drawRightString(A4[0]-16*mm, 10*mm, str(doc.page))
        canvas.restoreState()

    document = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16*mm, rightMargin=16*mm,
                                 topMargin=17*mm, bottomMargin=17*mm,
                                 title="Earth–Mars Mission Mathematics and Simulation Evidence",
                                 author="Independent draft prepared for Cybertwip",
                                 subject="Reproducible mathematical references, public Starship data and experimental EX-1 telemetry")
    document.build(story, onFirstPage=page, onLaterPages=page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=HERE / "earth_mars_mission_study.md")
    parser.add_argument("--telemetry", type=Path, default=HERE / "telemetry/earth_mars_run.json")
    parser.add_argument("--telemetry-csv", type=Path, default=HERE / "telemetry/earth_mars_run.csv")
    parser.add_argument("--html", type=Path, default=HERE / "earth_mars_mission_study.html")
    parser.add_argument("--pdf", type=Path, default=HERE / "earth_mars_mission_study.pdf")
    args = parser.parse_args()
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc"])
    body = md.convert(args.source.read_text())
    evidence, charts, telemetry_info = telemetry_section(args.telemetry, args.telemetry_csv, args.html.parent)
    body += evidence
    inputs = [args.source, Path(__file__).resolve(), HERE/"earth_mars_reference.py", HERE/"earth_mars_reference_results.json", HERE/"starship_public_profile.json"]
    inputs += sorted((HERE/"earth_mars_data").glob("*.json"))
    inputs += [p for p in (args.telemetry, args.telemetry_csv) if p.exists()]
    hashes = {os.path.relpath(p, HERE): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs if p.exists()}
    manifest = {"report_title": "Earth–Mars Mission Mathematics and Simulation Evidence",
                "authorship": "Independent draft prepared for Cybertwip; no US Navy, NASA or SpaceX endorsement claimed",
                "python_packages": {name: importlib.metadata.version(name) for name in ("Markdown", "reportlab")},
                "telemetry": telemetry_info, "input_sha256": hashes,
                "plots": [chart.identifier for chart in charts]}
    body += '<h2>16. Artifact provenance manifest</h2><p>SHA-256 values identify the exact study inputs and telemetry attachments used for this export. Calculated references, public design data and measured simulation outputs have separate source files.</p>'
    body += table(["Input path", "SHA-256"], [[p, digest] for p, digest in hashes.items()])
    body += '<p>Renderer packages: ' + escape(fmt(manifest["python_packages"])) + '.</p>'
    args.html.parent.mkdir(parents=True, exist_ok=True)
    args.pdf.parent.mkdir(parents=True, exist_ok=True)
    html = '<!doctype html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>Earth–Mars Mission Study — Cybertwip draft</title><style>' + CSS + '</style></head><body><main><div class="eyebrow">Engineering study / reproducible references / simulation evidence</div><details><summary>Document contents</summary>' + md.toc + '</details>' + body + '</main></body></html>'
    args.html.write_text(html)
    render_pdf(body, charts, args.pdf)
    manifest["outputs"] = {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in (args.html, args.pdf)}
    manifest_path = args.html.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"html": str(args.html), "pdf": str(args.pdf), "manifest": str(manifest_path),
                      "telemetry": telemetry_info, "plots": manifest["plots"]}, indent=2))


if __name__ == "__main__":
    main()
