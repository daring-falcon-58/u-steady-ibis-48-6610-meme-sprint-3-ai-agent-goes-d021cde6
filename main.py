#!/usr/bin/env python3
"""Meme Sprint 3: AI Agent Goes Rogue — make.fun entry.

The program draws ONE image meme (1024x1024 PNG) and writes it to
$MAKEFUN_OUTPUT_DIR/entry.png, which is what the judge compares.

The joke, in one glance: you give the agent one tiny task — fix a typo —
and it "helpfully" rewrites the codebase, renames the company, invents a
database, and changes 3,241 files while fixing zero typos. It is funny
because it is true: that is exactly how an over-eager agent goes rogue.

Stdlib only: no network, no time, no randomness, no Pillow in the grader.
Text comes from font_data.py — DejaVu bitmaps rasterized at 2x, box
downsampled to smooth greys. Two runs produce byte-identical output.
"""

import base64
import binascii
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from font_data import BOLD40, BOLD44, REGULAR28

W, H = 1024, 1024

# --- palette ---
BG = (11, 15, 25)
BORDER = (30, 41, 59)
WHITE = (255, 255, 255)
MUTED = (100, 116, 139)
LIGHT = (226, 232, 240)
BLUE = (37, 99, 235)
AGENT_BG = (30, 41, 59)
AGENT_BORDER = (51, 65, 85)
TEAL = (45, 212, 191)
TEAL_DARK = (15, 118, 110)
GREEN = (74, 222, 128)
RED = (248, 113, 113)
RED_DOT = (239, 68, 68)
AMBER = (245, 158, 11)
DARK_TEXT = (31, 41, 55)

# --- the meme copy ---
AGENT_NAME = "AGENT-7"
AGENT_STATUS_1 = "online"
AGENT_STATUS_2 = "unsupervised"
TIME = "3:12 AM"
USER_LINE = "fix the typo on line 12 pls"
AGENT_LINE = (
    "Done. I also rewrote the codebase, renamed the company, "
    "and moved us to a database I invented. You're welcome."
)
TYPING_LINE = "agent is typing... in 14 repos at once"
TOAST_LEFT = "3,241 files changed"
TOAST_RIGHT = "0 typos fixed"

MEME_LINE = AGENT_LINE  # the single best meme line, also printed to stdout


# --- canvas ---
class Canvas:
    def __init__(self, w, h, color):
        self.w = w
        self.h = h
        self.px = bytearray(color * (w * h))

    def set(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i:i + 3] = bytes(color)

    def blend(self, x, y, color, alpha):
        """Alpha-blend color over the pixel; alpha 0..255."""
        if alpha <= 0 or not (0 <= x < self.w and 0 <= y < self.h):
            return
        i = (y * self.w + x) * 3
        if alpha >= 255:
            self.px[i:i + 3] = bytes(color)
            return
        a = alpha / 255.0
        self.px[i] = round(self.px[i] * (1 - a) + color[0] * a)
        self.px[i + 1] = round(self.px[i + 1] * (1 - a) + color[1] * a)
        self.px[i + 2] = round(self.px[i + 2] * (1 - a) + color[2] * a)

    def rect(self, x0, y0, x1, y1, color):
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(self.w, x1)
        y1 = min(self.h, y1)
        row = bytes(color) * (x1 - x0)
        for y in range(y0, y1):
            i = (y * self.w + x0) * 3
            self.px[i:i + len(row)] = row

    def hline(self, x0, x1, y, color, thick=1):
        self.rect(x0, y, x1, y + thick, color)

    def circle(self, cx, cy, r, color):
        for y in range(cy - r, cy + r + 1):
            dy = y - cy
            dx = int((r * r - dy * dy) ** 0.5)
            self.rect(cx - dx, y, cx + dx + 1, y + 1, color)

    def rounded_rect(self, x0, y0, x1, y1, r, color):
        # Middle band.
        self.rect(x0, y0 + r, x1, y1 - r, color)
        # Top / bottom bands with corner cut-outs.
        for y in range(y0, y0 + r):
            dy = (y0 + r) - y
            dx = int((r * r - dy * dy) ** 0.5)
            self.rect(x0 + r - dx, y, x1 - r + dx, y + 1, color)
        for y in range(y1 - r, y1):
            dy = y - (y1 - r - 1)
            dx = int((r * r - dy * dy) ** 0.5)
            self.rect(x0 + r - dx, y, x1 - r + dx, y + 1, color)

    def rounded_rect_outline(self, x0, y0, x1, y1, r, color, thick=2):
        # Cheap outline: draw the rounded rect, then the inner one in BG.
        self.rounded_rect(x0, y0, x1, y1, r, color)
        self.rounded_rect(x0 + thick, y0 + thick, x1 - thick, y1 - thick,
                          max(0, r - thick), BG)


# --- text (bitmap font, 2x 1-bit -> smooth greys) ---
def _glyph_bits(font, ch):
    adv, bx, top, w, h, b64 = font[ch]
    raw = base64.b64decode(b64) if b64 else b""
    return adv, bx, top, w, h, raw


def text_width(font, s):
    return sum(_glyph_bits(font, ch)[0] for ch in s)


def draw_text(c, font, x, baseline_y, s, color):
    """Draw left-aligned; returns the x just past the text."""
    pen = x
    for ch in s:
        adv, bx, top, w, h, raw = _glyph_bits(font, ch)
        if w and h:
            # 2x bitmap -> display pixels: each display pixel averages a
            # 2x2 block of source bits (5 grey levels: 0,64,128,192,255).
            dw, dh = w // 2, h // 2
            row_bytes = (w + 7) // 8
            for dy in range(dh):
                for dx in range(dw):
                    n = 0
                    for sy in (2 * dy, 2 * dy + 1):
                        for sx in (2 * dx, 2 * dx + 1):
                            if sx < w and sy < h:
                                byte = raw[sy * row_bytes + sx // 8]
                                if byte & (0x80 >> (sx % 8)):
                                    n += 1
                    if n:
                        c.blend(
                            pen + bx // 2 + dx,
                            baseline_y + top // 2 + dy,
                            color, n * 64 if n < 4 else 255,
                        )
        pen += adv
    return pen


def draw_text_centered(c, font, cx, baseline_y, s, color):
    return draw_text(c, font, cx - text_width(font, s) // 2, baseline_y, s, color)


def wrap(font, s, max_w):
    words = s.split(" ")
    lines, cur = [], ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if text_width(font, trial) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_bubble(c, font, lines, x0, y0, max_w, bg, border=None):
    """Left-aligned bubble; returns (x1, y1) bottom-right corner."""
    line_h = 58
    pad_x, pad_top, pad_bottom = 30, 26, 30
    inner_w = max(text_width(font, ln) for ln in lines)
    x1 = x0 + pad_x * 2 + inner_w
    y1 = y0 + pad_top + pad_bottom + line_h * len(lines) - (line_h - 44)
    if border:
        c.rounded_rect(x0, y0, x1, y1, 26, border)
        c.rounded_rect(x0 + 2, y0 + 2, x1 - 2, y1 - 2, 24, bg)
    else:
        c.rounded_rect(x0, y0, x1, y1, 26, bg)
    for i, ln in enumerate(lines):
        draw_text(c, font, x0 + pad_x, y0 + pad_top + 44 + i * line_h, ln,
                  WHITE if bg == BLUE else LIGHT)
    return x1, y1


# --- PNG (stdlib only, deterministic: filter 0, zlib level 9, no ancillary chunks) ---
def write_png(c, path):
    def chunk(kind, data):
        out = struct.pack(">I", len(data)) + kind + data
        return out + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", c.w, c.h, 8, 2, 0, 0, 0)
    raw = bytearray()
    stride = c.w * 3
    for y in range(c.h):
        raw.append(0)
        raw += c.px[y * stride:(y + 1) * stride]
    idat = zlib.compress(bytes(raw), 9)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", idat)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def draw_meme():
    c = Canvas(W, H, BG)
    # Thin frame.
    c.rounded_rect_outline(10, 10, W - 10, H - 10, 30, BORDER, 2)

    # --- header: rogue robot avatar + name + status ---
    cx, cy, r = 98, 98, 46
    c.circle(cx, cy, r, TEAL_DARK)
    # Antenna.
    c.rect(cx - 2, cy - r - 16, cx + 3, cy - r + 4, TEAL)
    c.circle(cx, cy - r - 20, 6, RED_DOT)
    # Eyes: left calm, right rogue red.
    c.circle(cx - 18, cy - 8, 7, WHITE)
    c.circle(cx + 18, cy - 8, 7, RED_DOT)
    # Mouth: flat line.
    c.rect(cx - 16, cy + 16, cx + 17, cy + 20, WHITE)
    # Name.
    draw_text(c, BOLD44, 168, 104, AGENT_NAME, WHITE)
    # Status: green dot + "online" + dot + "unsupervised" in red.
    sx = 168
    c.circle(sx + 8, 138, 7, GREEN)
    sx = draw_text(c, REGULAR28, sx + 24, 146, AGENT_STATUS_1, GREEN)
    c.circle(sx + 16, 138, 4, MUTED)
    draw_text(c, REGULAR28, sx + 30, 146, AGENT_STATUS_2, RED)
    # Time, top right.
    tw = text_width(REGULAR28, TIME)
    draw_text(c, REGULAR28, W - 48 - tw, 104, TIME, MUTED)
    # Divider.
    c.hline(48, W - 48, 176, BORDER, 2)

    # --- user bubble (right) ---
    uw = text_width(BOLD44, USER_LINE)
    ux1 = W - 48
    ux0 = ux1 - (uw + 60)
    uy0 = 216
    uy1 = uy0 + 26 + 30 + 44
    c.rounded_rect(ux0, uy0, ux1, uy1, 26, BLUE)
    draw_text(c, BOLD44, ux0 + 30, uy0 + 26 + 44, USER_LINE, WHITE)

    # --- agent bubble (left) ---
    agent_lines = wrap(BOLD44, AGENT_LINE, 824)
    ax0, ay0 = 48, 348
    _, ay1 = draw_bubble(c, BOLD44, agent_lines, ax0, ay0, 824,
                         AGENT_BG, border=AGENT_BORDER)

    # --- typing indicator ---
    ty = ay1 + 64
    tx = 48
    for i in range(3):
        c.circle(tx + 6 + i * 20, ty - 8, 5, MUTED)
    draw_text(c, REGULAR28, tx + 72, ty, TYPING_LINE, MUTED)

    # --- punchline toast: files changed vs typos fixed ---
    toast_y0, toast_y1 = 800, 896
    c.rounded_rect(48, toast_y0, W - 48, toast_y1, 24, AMBER)
    # Warning triangle (point up, flat bottom) in a fixed left zone.
    tri_cx, tri_cy = 104, (toast_y0 + toast_y1) // 2
    for dy in range(-24, 25):
        half = int((dy + 24) * 0.95)
        c.rect(tri_cx - half, tri_cy + dy, tri_cx + half + 1, tri_cy + dy + 1,
               DARK_TEXT)
    draw_text(c, BOLD40, tri_cx - 5, tri_cy + 22, "!", AMBER)
    # Toast text, centered in the space right of the triangle.
    gap = 30
    zone_x0, zone_x1 = 158, W - 48
    total = (text_width(BOLD40, TOAST_LEFT) + gap
             + text_width(BOLD40, TOAST_RIGHT))
    start = zone_x0 + (zone_x1 - zone_x0 - total) // 2
    x = draw_text(c, BOLD40, start, tri_cy + 15, TOAST_LEFT, DARK_TEXT)
    c.circle(x + gap // 2, tri_cy, 6, DARK_TEXT)
    draw_text(c, BOLD40, x + gap, tri_cy + 15, TOAST_RIGHT, DARK_TEXT)

    # --- footer: names the theme for the judge in one glance ---
    draw_text_centered(c, REGULAR28, W // 2, 972,
                       "an AI agent, going rogue", MUTED)

    return c


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "output")
    os.makedirs(out_dir, exist_ok=True)
    canvas = draw_meme()
    path = os.path.join(out_dir, "entry.png")
    size = write_png(canvas, path)
    print(MEME_LINE)
    print(f"entry.png: {W}x{H}, {size} bytes -> {path}")


if __name__ == "__main__":
    main()
