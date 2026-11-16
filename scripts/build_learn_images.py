#!/usr/bin/env python3
"""Generate the illustrations for the Learn Data Cleaning page (standard library only).

Run from anywhere:  python3 scripts/build_learn_images.py
Writes one SVG per topic into app/static/img/learn/. The SVGs are plain local files: no external
fonts, images or URLs. Colours are CSS classes with a dark-mode override inside each SVG, so the
pictures follow the visitor's light/dark setting when loaded through an <img> tag.
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parents[1] / "app" / "static" / "img" / "learn"
W, H = 640, 300

STYLE = """
.bg{fill:#fff;stroke:#d7ddd9;stroke-width:1.5}
.cell{fill:#fff;stroke:#b9c3bd;stroke-width:1.4}
.hdr{fill:#f6f8f7;stroke:#b9c3bd;stroke-width:1.4}
.gap{fill:url(#hatch);stroke:#b9c3bd;stroke-width:1.4}
.pad{fill:url(#hatch);stroke:none}
.ok{fill:#e2f1e8;stroke:#17724a;stroke-width:1.6}
.mark{fill:#fff0a0;stroke:#c9a800;stroke-width:1.6}
.bad{fill:#fdecea;stroke:#b3261e;stroke-width:1.6}
.info{fill:#e8f0f7;stroke:#1f4e79;stroke-width:1.6}
.sel{fill:none;stroke:#17724a;stroke-width:2.6}
.handle{fill:#17724a;stroke:#fff;stroke-width:2}
.accfill{fill:#17724a}
.onacc{fill:#fff;font-weight:700}
.hatchline{stroke:#56655d;stroke-opacity:.5;stroke-width:1.3}
.t{fill:#18231e}
.tb{fill:#18231e;font-weight:700}
.s{fill:#56655d}
.sb{fill:#56655d;font-weight:700}
.acc{fill:#0f5836;font-weight:700}
.mk{fill:#4d3f00}
.bd{fill:#b3261e;font-weight:700}
.nf{fill:#1f4e79;font-weight:700}
.wt{fill:#8a5300;font-weight:700}
.line{stroke:#56655d;stroke-width:1.6;fill:none}
.arrow{stroke:#17724a;stroke-width:2.4;fill:none}
.arrowhead{fill:#17724a}
.strike{stroke:#b3261e;stroke-width:2.2;fill:none}
.bar{fill:#b9c3bd}
.baracc{fill:#17724a}
.accline{stroke:#17724a;stroke-width:2.6;fill:none}
.dashacc{stroke:#17724a;stroke-width:2;stroke-dasharray:6 4;fill:none}
.warnline{stroke:#8a5300;stroke-width:2.2;stroke-dasharray:6 4;fill:none}
.dot{fill:#56655d}
.dotwarn{fill:#8a5300}
.dashed{stroke-dasharray:5 4}
.f{font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.m{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
@media (prefers-color-scheme:dark){
.bg{fill:#171e1b;stroke:#2b3732}
.cell{fill:#1d2622;stroke:#3d4c45}
.hdr{fill:#232e29;stroke:#3d4c45}
.gap{stroke:#3d4c45}
.ok{fill:#1b3a2b;stroke:#4cc38a}
.mark{fill:#5a4e10;stroke:#b39b22}
.bad{fill:#3a1c1a;stroke:#ff9a92}
.info{fill:#1a2a3a;stroke:#9cc4ec}
.sel{stroke:#4cc38a}
.handle{fill:#4cc38a;stroke:#171e1b}
.accfill{fill:#4cc38a}
.onacc{fill:#07140e}
.hatchline{stroke:#9aaba2;stroke-opacity:.5}
.t,.tb{fill:#e6ede9}
.s,.sb{fill:#9aaba2}
.acc{fill:#7bd9ab}
.mk{fill:#fff3b0}
.bd{fill:#ff9a92}
.nf{fill:#9cc4ec}
.wt{fill:#f0c36b}
.line{stroke:#9aaba2}
.arrow{stroke:#4cc38a}
.arrowhead{fill:#4cc38a}
.strike{stroke:#ff9a92}
.bar{fill:#3d4c45}
.baracc{fill:#4cc38a}
.accline{stroke:#4cc38a}
.dashacc{stroke:#4cc38a}
.warnline{stroke:#f0c36b}
.dot{fill:#9aaba2}
.dotwarn{fill:#f0c36b}
}
"""

DEFS = """<defs>
<style>%s</style>
<pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" class="hatchline"/></pattern>
<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="12" markerHeight="12" markerUnits="userSpaceOnUse" orient="auto"><path class="arrowhead" d="M0 0L10 5L0 10z"/></marker>
</defs>""" % STYLE

TEXT_FOR = {"mark": "mk", "bad": "bd", "ok": "t", "info": "t", "cell": "t", "hdr": "sb"}


class Doc:
    def __init__(self, filename: str, title: str, desc: str) -> None:
        self.filename, self.title, self.desc = filename, title, desc
        self.parts: list[str] = []

    # -- primitives ------------------------------------------------------------------------
    def add(self, s: str) -> None:
        self.parts.append(s)

    def rect(self, x, y, w, h, cls, rx=3) -> None:
        self.add(f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>')

    def text(self, x, y, s, cls="t", size=14, anchor="middle", mono=False) -> None:
        fam = "m" if mono else "f"
        self.add(f'<text class="{cls} {fam}" x="{x}" y="{y}" font-size="{size}" '
                 f'text-anchor="{anchor}">{escape(s)}</text>')

    def ctext(self, cx, cy, s, cls="t", size=14, anchor="middle", mono=False) -> None:
        """Text vertically centred on cy."""
        self.text(cx, round(cy + size * 0.36, 1), s, cls, size, anchor, mono)

    def lines(self, x, y, items, cls="s", size=12.5, step=17, anchor="start") -> None:
        for i, s in enumerate(items):
            c = cls[i] if isinstance(cls, (list, tuple)) else cls
            self.text(x, y + i * step, s, c, size, anchor)

    def line(self, x1, y1, x2, y2, cls="line") -> None:
        self.add(f'<path class="{cls}" d="M{x1} {y1}L{x2} {y2}"/>')

    def arrow(self, x1, y1, x2, y2) -> None:
        self.add(f'<path class="arrow" d="M{x1} {y1}L{x2} {y2}" marker-end="url(#ah)"/>')

    def curve(self, d: str) -> None:
        self.add(f'<path class="arrow" d="{d}" marker-end="url(#ah)"/>')

    def strike(self, x1, y, x2) -> None:
        self.line(x1, y, x2, y, "strike")

    # -- spreadsheet pieces ----------------------------------------------------------------
    def cell(self, x, y, w, h, s, cls="cell", tcls=None, size=14, mono=True, align="middle", rx=2) -> None:
        """A cell. s=None draws a hatched empty cell (on a coloured band when cls is not 'cell')."""
        if s is None:
            if cls not in ("cell", "gap"):
                self.rect(x, y, w, h, cls, rx)
            self.rect(x, y, w, h, "gap", rx)
            return
        self.rect(x, y, w, h, cls, rx)
        tc = tcls or TEXT_FOR.get(cls, "t")
        if align == "start":
            self.ctext(x + 11, y + h / 2, s, tc, size, "start", mono)
        elif align == "end":
            self.ctext(x + w - 11, y + h / 2, s, tc, size, "end", mono)
        else:
            self.ctext(x + w / 2, y + h / 2, s, tc, size, "middle", mono)

    def grid(self, x, y, widths, rh, header, rows, hh=28) -> float:
        """rows: list of rows; a spec is 'text', None (empty) or (text_or_None, cls). Returns bottom y."""
        cy = y
        if header:
            cx = x
            for w, name in zip(widths, header):
                self.rect(cx, cy, w, hh, "hdr", 2)
                self.ctext(cx + w / 2, cy + hh / 2, name, "sb", 12.5, mono=False)
                cx += w
            cy += hh
        for row in rows:
            cx = x
            for w, spec in zip(widths, row):
                text, cls = spec if isinstance(spec, tuple) else (spec, "cell")
                self.cell(cx, cy, w, rh, text, cls)
                cx += w
            cy += rh
        return cy

    # -- output ----------------------------------------------------------------------------
    def render(self) -> str:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
                f'role="img" aria-labelledby="ttl dsc">\n<title id="ttl">{escape(self.title)}</title>\n'
                f'<desc id="dsc">{escape(self.desc)}</desc>\n{DEFS}\n'
                f'<rect class="bg" x="1" y="1" width="{W - 2}" height="{H - 2}" rx="6"/>\n'
                + "\n".join(self.parts) + "\n</svg>\n")


# ===================================================================================== images
def dedupe() -> Doc:
    d = Doc("dedupe.svg", "Duplicate rows removed",
            "Five rows on the left include two repeats of earlier rows, struck through. On the right only "
            "the first copy of each row remains, giving three rows.")
    d.text(40, 36, "Before: 5 rows", "sb", 13, "start")
    rows = [("1001", "Ann"), ("1002", "Bo"), ("1001", "Ann"), ("1003", "Cy"), ("1002", "Bo")]
    dup = {2, 4}
    spec = [[(a, "bad" if i in dup else "cell"), (b, "bad" if i in dup else "cell")] for i, (a, b) in enumerate(rows)]
    d.grid(40, 50, [74, 96], 36, ["Order", "Customer"], spec)
    for i in dup:
        ym = 78 + i * 36 + 18
        d.strike(34, ym, 216)
        d.text(226, ym + 4, "repeat", "bd", 12.5, "start")
    d.arrow(290, 168, 372, 168)
    d.text(331, 152, "keep the first", "s", 12.5)
    d.text(410, 36, "After: 3 rows", "sb", 13, "start")
    d.grid(410, 50, [74, 96], 36, ["Order", "Customer"], [[(a, "ok"), (b, "ok")] for a, b in [rows[0], rows[1], rows[3]]])
    d.text(410, 214, "The first copy of each", "s", 12.5, "start")
    d.text(410, 231, "row is the one kept.", "s", 12.5, "start")
    return d


def missing() -> Doc:
    d = Doc("missing.svg", "A missing value and three ways to handle it",
            "An Age column with one empty, selected cell. Three arrows lead to the choices: fill it with a "
            "value, remove that row, or keep it missing.")
    d.text(40, 38, "Age column", "sb", 13, "start")
    d.grid(40, 50, [110], 40, ["Age"], [["12"], ["15"], [None], ["11"]])
    gy = 50 + 28 + 80
    d.rect(40, gy, 110, 40, "sel", 2)
    d.rect(145, gy + 35, 10, 10, "handle", 1)
    d.text(40, 262, "An empty cell is a missing value.", "s", 13, "start")
    d.text(340, 40, "You choose, column by column", "sb", 13, "start")
    boxes = [("Fill it with a value", "mean, median, most common, or your own"),
             ("Remove that row", "when the row is not worth keeping"),
             ("Keep it missing", "unknown stays unknown")]
    for i, (a, b) in enumerate(boxes):
        y = 56 + i * 76
        d.rect(340, y, 280, 58, "cell", 3)
        d.text(356, y + 24, a, "tb", 14.5, "start")
        d.text(356, y + 44, b, "s", 12.5, "start")
        d.curve(f"M158 {gy + 20} C 250 {gy + 20}, 250 {y + 29}, 332 {y + 29}")
    return d


def mean() -> Doc:
    d = Doc("mean.svg", "Mean imputation",
            "Bars for three prices, 2.50, 3.50 and 3.00, with a dashed line at their mean of 3.00. The missing "
            "fourth bar is hatched and reaches the mean line.")
    base, scale, bw = 232, 46, 60
    d.text(40, 36, "Prices of four items, one unknown", "sb", 13, "start")
    d.line(50, base, 420, base)
    for name, v, x in [("Tea", 2.5, 80), ("Coffee", 3.5, 160), ("Milk", None, 240), ("Juice", 3.0, 320)]:
        if v is None:
            mh = 3.0 * scale
            d.rect(x, base - mh, bw, mh, "gap dashed", 2)
            d.text(x + bw / 2, base - mh - 8, "3.00", "acc", 14)
        else:
            h = v * scale
            d.rect(x, base - h, bw, h, "bar", 2)
            d.text(x + bw / 2, base - h - 8, f"{v:.2f}", "t", 13)
        d.text(x + bw / 2, base + 20, name, "s", 13)
    d.line(56, base - 3.0 * scale, 410, base - 3.0 * scale, "dashacc")
    d.text(58, base - 3.0 * scale - 8, "mean 3.00", "acc", 13, "start")
    d.text(440, 84, "How it works", "tb", 14, "start")
    d.lines(440, 108, ["Add up the known values,", "divide by how many there are:"], "s", 12.5, 18)
    d.text(440, 156, "(2.50 + 3.50 + 3.00) ÷ 3", "t", 12, "start", mono=True)
    d.text(440, 180, "= 3.00", "acc", 15, "start")
    d.lines(440, 214, ["Rounded to the column's", "own decimal places."], "s", 12.5, 17)
    return d


def median() -> Doc:
    d = Doc("median.svg", "Median imputation",
            "A number line with a stack of three salaries near 30 to 34 thousand and one salary of 250 thousand "
            "far to the right. The mean marker sits far from the stack. The median marker sits on it.")
    d.text(40, 38, "Four known salaries, one of them huge", "sb", 13, "start")
    ax = 190
    d.line(50, ax, 592, ax)
    for v, lab in [(0, "0"), (100, "100k"), (200, "200k")]:
        x = 60 + 2 * v
        d.line(x, ax - 5, x, ax + 5)
        d.text(x, ax + 22, lab, "s", 12)
    for cy in (181, 167, 153):
        d.add(f'<circle class="dot" cx="124" cy="{cy}" r="6.5"/>')
    d.add(f'<circle class="dot" cx="560" cy="181" r="6.5"/>')
    d.text(560, 163, "250k", "t", 13)
    d.text(124, 238, "30k, 32k, 34k", "s", 12)
    d.line(126, 104, 126, 144, "accline")
    d.text(120, 98, "median 33k", "acc", 14, "end")
    d.line(233, 104, 233, ax, "warnline")
    d.text(241, 98, "mean 86.5k", "wt", 14, "start")
    d.text(410, 136, "One huge value pulls the mean up", "wt", 13)
    d.text(320, 270, "The median is the middle value, so extremes barely move it.", "s", 13)
    return d


def mode() -> Doc:
    d = Doc("mode.svg", "Mode imputation",
            "A bar chart where the Pune bar is the tallest and highlighted, next to an empty city cell that is "
            "filled with Pune.")
    d.text(40, 38, "How often each city appears", "sb", 13, "start")
    base = 232
    d.line(50, base, 290, base)
    d.rect(80, base - 120, 80, 120, "baracc", 2)
    d.text(120, base - 129, "3", "tb", 15)
    d.rect(180, base - 40, 80, 40, "bar", 2)
    d.text(220, base - 49, "1", "tb", 15)
    d.text(120, base + 20, "Pune", "tb", 13)
    d.text(220, base + 20, "Delhi", "s", 13)
    d.rect(68, base - 170, 104, 24, "ok", 12)
    d.text(120, base - 154, "most common", "acc", 12)
    d.text(380, 84, "Empty city", "sb", 12.5, "start")
    d.cell(380, 92, 150, 42, None)
    d.arrow(455, 142, 455, 180)
    d.text(468, 166, "fill with the mode", "s", 12.5, "start")
    d.cell(380, 190, 150, 42, "Pune", "mark", size=16)
    d.lines(380, 262, ["Tie? The smallest number, or the", "first A to Z for text, wins."], "s", 12, 16)
    return d


def custom() -> Doc:
    d = Doc("custom-value.svg", "Custom value imputation",
            "An empty cell, an arrow to a text box where a value is typed, and an arrow to the cell filled "
            "with that value. Three small cards list what fits number, date and Yes/No columns.")
    d.text(90, 86, "Empty", "sb", 12.5)
    d.cell(30, 96, 120, 46, None)
    d.arrow(158, 119, 200, 119)
    d.text(320, 86, "You type it", "sb", 12.5)
    d.rect(206, 96, 228, 46, "cell", 3)
    d.rect(206, 96, 228, 46, "sel", 3)
    d.text(222, 119.5, "Pending review", "t", 15, "start", mono=True)
    d.line(222 + 14 * 9 + 6, 106, 222 + 14 * 9 + 6, 132, "accline")
    d.arrow(442, 119, 478, 119)
    d.text(552, 86, "Filled", "sb", 12.5)
    d.cell(486, 96, 136, 46, "Pending review", "mark", size=12.5)
    cards = [("Number column", "type a number"), ("Date column", "type YYYY-MM-DD"),
             ("Yes/No column", "pick a value already there")]
    for i, (a, b) in enumerate(cards):
        x = 30 + i * 200
        d.rect(x, 190, 186, 62, "cell", 3)
        d.text(x + 14, 215, a, "tb", 13.5, "start")
        d.text(x + 14, 236, b, "s", 12.5, "start")
    d.text(30, 280, "CleanSheet checks the value fits the column before using it.", "s", 12.5, "start")
    return d


def lookup() -> Doc:
    d = Doc("lookup.svg", "Group-based imputation as an exact lookup",
            "Rows grouped by customer ID in two colours. An empty name in the C01 group is filled from the C01 "
            "row above it, while the lone C03 row stays empty.")
    d.text(30, 42, "Before", "sb", 13, "start")
    d.text(300, 42, "After", "sb", 13, "start")
    band = {"C01": "ok", "C02": "info", "C03": "cell"}
    keys = ["C01", "C02", "C01", "C02", "C03"]
    names = ["Ann Lee", "Bo Chen", None, "Bo Chen", None]
    before = [[(k, band[k]), (n, band[k]) if n else (None, band[k])] for k, n in zip(keys, names)]
    after_names = ["Ann Lee", "Bo Chen", "Ann Lee", "Bo Chen", None]
    after = []
    for i, (k, n) in enumerate(zip(keys, after_names)):
        if i == 2:
            after.append([(k, band[k]), (n, "mark")])
        else:
            after.append([(k, band[k]), (n, band[k]) if n else (None, band[k])])
    d.grid(30, 54, [60, 110], 34, ["ID", "Name"], before)
    d.grid(300, 54, [60, 110], 34, ["ID", "Name"], after)
    d.arrow(208, 170, 292, 170)
    d.text(250, 154, "look up the ID", "s", 12)
    d.rect(484, 82, 146, 170, "cell", 3)
    d.lines(496, 106, ["One answer per ID"], "tb", 12.5, 16)
    d.lines(496, 128, ["C01 is always Ann Lee,", "so that gap is filled.", "C03 is not known,", "so it stays empty."],
            "s", 11.5, 16)
    d.lines(496, 200, ["An ID with two", "different names is", "never used."], "wt", 11.5, 16)
    return d


def formula() -> Doc:
    d = Doc("formula.svg", "Formula-based recovery",
            "Quantity times unit price equals revenue. With both sources present the empty revenue cell is "
            "calculated as 12.00. In a second row the quantity is missing, so revenue stays empty.")

    def sub_cell(x, y, w, h, sub, val, cls="cell"):
        if val is None:
            d.cell(x, y, w, h, None)
        else:
            d.rect(x, y, w, h, cls, 2)
        d.text(x + w / 2, y + 15, sub, "s", 11.5)
        if val is not None:
            d.text(x + w / 2, y + h - 14, val, "mk" if cls == "mark" else "t", 17, mono=True)

    d.text(50, 46, "Every source value is present", "sb", 13, "start")
    sub_cell(50, 56, 100, 56, "Qty", "3")
    d.text(166, 90, "×", "tb", 22)
    sub_cell(182, 56, 110, 56, "Unit price", "4.00")
    d.text(308, 90, "=", "tb", 22)
    sub_cell(324, 56, 100, 56, "Revenue", None)
    d.arrow(432, 84, 474, 84)
    sub_cell(480, 56, 110, 56, "Revenue", "12.00", "mark")
    d.text(50, 152, "A source value is missing", "sb", 13, "start")
    sub_cell(50, 162, 100, 56, "Qty", None)
    d.text(166, 196, "×", "tb", 22)
    sub_cell(182, 162, 110, 56, "Unit price", "2.50")
    d.text(308, 196, "=", "tb", 22)
    sub_cell(324, 162, 100, 56, "Revenue", None)
    d.add('<circle class="bad" cx="456" cy="190" r="14"/>')
    d.line(447, 181, 465, 199, "strike")
    d.text(480, 195, "stays empty", "bd", 13.5, "start")
    d.text(320, 262, "Also works for revenue − cost = margin. A row is filled only when every source is present.",
           "s", 12.5)
    return d


def text_std() -> Doc:
    d = Doc("text-standardization.svg", "Text standardization",
            "Four messy spellings of New York flow through four steps, trim, collapse spaces, change case and "
            "find and replace, into one standard value.")
    pills = ["1  Trim", "2  Collapse spaces", "3  Change case", "4  Find & replace"]
    for i, p in enumerate(pills):
        x = 20 + i * 150
        d.rect(x, 20, 130, 32, "info", 16)
        d.ctext(x + 65, 36, p, "nf", 12.5)
        if i < 3:
            d.line(x + 130, 36, x + 150, 36)
    d.text(40, 86, "Messy", "sb", 12.5, "start")
    messy = ["new··york", "NEW YORK", "New York·", "nyc"]
    for i, m in enumerate(messy):
        y = 94 + i * 42
        d.cell(40, y, 160, 34, m, "bad", size=14.5)
        d.arrow(206, y + 17, 420, 164 + i * 10)
    d.text(430, 142, "One standard value", "sb", 12.5, "start")
    d.cell(430, 150, 170, 52, "New York", "ok", size=17)
    d.text(430, 232, "Title Case, plus the rule", "s", 12.5, "start")
    d.text(430, 249, "nyc → New York", "s", 12.5, "start")
    d.text(40, 280, "A dot (·) marks a space.", "s", 12, "start")
    return d


def trim() -> Doc:
    d = Doc("trim.svg", "Whitespace trimming",
            "A cell with hatched padding either side of the name Ann Lee, shown as not equal to a clean Ann Lee "
            "cell. After trimming, both cells are equal.")
    d.text(147, 40, "space", "s", 11.5)
    d.text(284, 40, "spaces", "s", 11.5)
    d.rect(130, 48, 180, 46, "cell", 2)
    d.rect(131, 49, 34, 44, "pad", 0)
    d.rect(257, 49, 52, 44, "pad", 0)
    d.ctext(211, 71, "Ann Lee", "t", 15, mono=True)
    d.text(350, 81, "≠", "tb", 30)
    d.cell(390, 48, 180, 46, "Ann Lee", "cell", size=15)
    d.text(320, 118, "They look the same, but the computer sees two different values.", "s", 13)
    d.arrow(320, 132, 320, 168)
    d.text(336, 155, "trim", "acc", 13.5, "start")
    d.cell(130, 182, 180, 46, "Ann Lee", "ok", size=15)
    d.text(350, 214, "=", "tb", 30)
    d.cell(390, 182, 180, 46, "Ann Lee", "ok", size=15)
    d.text(320, 262, "Now they match, so duplicate checks and lookups work.", "s", 13)
    return d


def replace() -> Doc:
    d = Doc("find-replace.svg", "Find and replace",
            "A rule that finds USA and replaces it with United States, applied to a column. USA and usa change. "
            "U.S.A. is a different spelling, so it needs its own rule.")
    d.text(60, 38, "Find", "sb", 12.5, "start")
    d.cell(60, 46, 170, 42, "USA", "cell", size=15)
    d.rect(60, 46, 170, 42, "sel", 2)
    d.arrow(238, 67, 284, 67)
    d.text(292, 38, "Replace with", "sb", 12.5, "start")
    d.cell(292, 46, 200, 42, "United States", "ok", size=15)
    d.text(508, 62, "Exact text only,", "s", 12, "start")
    d.text(508, 79, "not patterns.", "s", 12, "start")
    d.text(70, 120, "Before", "sb", 12.5, "start")
    d.text(300, 120, "After", "sb", 12.5, "start")
    before = [("USA", "mark"), ("usa", "mark"), ("U.S.A.", "cell"), ("United States", "cell")]
    after = [("United States", "mark"), ("United States", "mark"), ("U.S.A.", "cell"), ("United States", "cell")]
    for i, ((b, bc), (a, ac)) in enumerate(zip(before, after)):
        y = 128 + i * 38
        d.cell(70, y, 160, 34, b, bc, size=14)
        d.cell(300, y, 160, 34, a, ac, size=14)
    d.arrow(238, 195, 292, 195)
    d.lines(476, 214, ["U.S.A. is spelled", "differently, so it", "needs its own rule."], "wt", 12, 16)
    return d


def type_conv() -> Doc:
    d = Doc("type-conversion.svg", "Data type conversion",
            "Three conversions. The text 1,200 becomes the number 1200. The text 2024-03-05 becomes a date. The "
            "text 12.5 cannot become a whole number, so that column is skipped.")
    d.text(60, 32, "As text", "sb", 12.5, "start")
    d.text(326, 32, "After converting", "sb", 12.5, "start")
    rows = [(44, '"1,200"', "whole number"), (110, '"2024-03-05"', "date"), (176, '"12.5"', "whole number")]
    for i, (y, src, label) in enumerate(rows):
        d.cell(60, y, 170, 46, src, "cell", size=14.5, align="start")
        d.arrow(238, y + 23, 316, y + 23)
        d.text(277, y + 14, label, "s", 11.5)
    d.cell(326, 44, 160, 46, "1200", "ok", size=15, align="end")
    d.rect(326, 110, 160, 46, "ok", 2)
    d.rect(336, 122, 20, 20, "cell", 2)
    d.rect(336, 122, 20, 6, "accfill", 2)
    d.add('<circle class="dot" cx="342" cy="134" r="1.6"/><circle class="dot" cx="350" cy="134" r="1.6"/>'
          '<circle class="dot" cx="342" cy="139" r="1.6"/><circle class="dot" cx="350" cy="139" r="1.6"/>')
    d.ctext(366, 133, "2024-03-05", "t", 14.5, "start", mono=True)
    d.cell(326, 176, 160, 46, "skipped", "bad", size=15)
    d.text(500, 64, "Comma removed.", "s", 12, "start")
    d.text(500, 130, "Checked: a real date.", "s", 12, "start")
    d.lines(500, 194, ["12.5 is not whole:", "column skipped,", "originals stay."], "s", 12, 16)
    d.text(320, 266, "One invalid value is enough to skip the column. Nothing is half-converted.", "s", 12.5)
    return d


def dates() -> Doc:
    d = Doc("date-standardization.svg", "Date standardization",
            "Three spellings of the same date, 05-Mar-2024, March 5 2024 and 05/03/2024, all become 2024-03-05. "
            "A note explains that 03/04/2024 is ambiguous, so CleanSheet asks which order is used.")
    d.text(40, 50, "Different spellings", "sb", 12.5, "start")
    for i, s in enumerate(["05-Mar-2024", "March 5, 2024", "05/03/2024"]):
        y = 60 + i * 50
        d.cell(40, y, 180, 38, s, "cell", size=14.5)
        d.arrow(228, y + 19, 402, 120 + i * 13)
    d.text(412, 96, "One standard: YYYY-MM-DD", "sb", 12.5, "start")
    d.cell(412, 104, 190, 54, "2024-03-05", "ok", size=18)
    d.rect(40, 218, 560, 62, "info", 3)
    d.add('<circle class="accfill" cx="72" cy="249" r="14"/>')
    d.text(72, 255, "?", "onacc", 17)
    d.text(98, 243, "Is 03/04/2024 the 3rd of April or March 4th? If the column cannot settle it,", "t", 12.5, "start")
    d.text(98, 262, "CleanSheet asks which order it uses. It does not guess.", "t", 12.5, "start")
    return d


def binary() -> Doc:
    d = Doc("binary.svg", "Binary column conversion",
            "Three two-state columns, TRUE and FALSE, 1 and 0, and Y and N, each converted to Yes and No. A note "
            "says a column of only 1s and 0s may be a number and needs confirming.")
    d.text(30, 32, "Before", "sb", 12.5, "start")
    d.text(298, 32, "After", "sb", 12.5, "start")
    for i, (a, b) in enumerate([("TRUE", "FALSE"), ("1", "0"), ("Y", "N")]):
        y = 44 + i * 58
        d.cell(30, y, 92, 42, a, "cell", size=14.5)
        d.cell(130, y, 92, 42, b, "cell", size=14.5)
        d.arrow(234, y + 21, 286, y + 21)
        d.cell(298, y, 92, 42, "Yes", "ok", size=14.5)
        d.cell(398, y, 92, 42, "No", "ok", size=14.5)
    d.lines(504, 106, ["Only 1s and 0s?", "You confirm it is", "a flag, not a", "number."], "wt", 12, 16)
    d.text(30, 240, "Each column picks its own style: TRUE/FALSE, Yes/No or 1/0.", "s", 13, "start")
    d.text(30, 262, "Empty cells stay empty.", "s", 13, "start")
    return d


def identifier() -> Doc:
    d = Doc("identifier.svg", "Identifier handling",
            "The ID 00123 sits in a cell with a lock icon and stays as text. The number 123 is crossed out, and "
            "the actions average, change case and convert to number are crossed out as never applied to an ID.")
    d.text(50, 60, "Customer ID", "sb", 12.5, "start")
    d.cell(50, 70, 160, 56, "00123", "ok", size=22)
    d.add('<rect class="accfill" x="226" y="98" width="24" height="18" rx="3"/>')
    d.add('<path class="accline" d="M231 98v-7a7 7 0 0 1 14 0v7"/>')
    d.text(50, 148, "Kept as text: the zeros stay.", "s", 13, "start")
    d.cell(50, 178, 100, 40, "123", "bad", size=18)
    d.strike(44, 198, 156)
    d.lines(164, 194, ["As a number, the", "zeros would be lost."], "s", 12.5, 16)
    d.text(350, 52, "Never done to an ID", "tb", 14, "start")
    for i, s in enumerate(["Average (mean or median)", "Change the case", "Convert to a number"]):
        y = 64 + i * 44
        d.cell(350, y, 270, 34, s, "bad", size=13.5, mono=False, align="start")
        d.line(598, y + 10, 610, y + 24, "strike")
        d.line(610, y + 10, 598, y + 24, "strike")
    d.text(350, 216, "Allowed", "tb", 14, "start")
    d.lines(350, 236, ["Look it up from a related column,", "type a value, remove rows, or keep."], "s", 12.5, 17)
    return d


BUILDERS = [dedupe, missing, mean, median, mode, custom, lookup, formula, text_std, trim, replace,
            type_conv, dates, binary, identifier]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for build in BUILDERS:
        doc = build()
        (OUT / doc.filename).write_text(doc.render(), encoding="utf-8")
        print("wrote", OUT / doc.filename)


if __name__ == "__main__":
    main()
