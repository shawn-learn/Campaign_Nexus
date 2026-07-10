"""Read (width, height) and MIME from an image's header bytes — no Pillow dependency.

Supports the formats a browser can render as a Leaflet imageOverlay: PNG, JPEG, GIF, WebP.
Raises ``BadImage`` for anything we can't size (so uploads fail loudly, not with a 0x0 map).
"""

from __future__ import annotations

import struct


class BadImage(ValueError):
    pass


def sniff(data: bytes) -> tuple[str, int, int]:
    """Return (mime, width, height). Raises BadImage if the format isn't recognized."""
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        # IHDR width/height are the two big-endian uint32 at offset 16.
        w, h = struct.unpack(">II", data[16:24])
        return "image/png", w, h

    if data[:3] == b"GIF":
        w, h = struct.unpack("<HH", data[6:10])
        return "image/gif", w, h

    if len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", *_webp_size(data)

    if data[:2] == b"\xff\xd8":
        return "image/jpeg", *_jpeg_size(data)

    raise BadImage("unsupported image format (use PNG, JPEG, GIF, or WebP)")


def _jpeg_size(data: bytes) -> tuple[int, int]:
    # Walk the marker segments to the Start-Of-Frame, which carries height/width.
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        # SOF0..SOF15 except DHT(C4)/JPG(C8)/DAC(CC) hold the frame dimensions.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return w, h
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
        i += 2 + seg_len
    raise BadImage("could not read JPEG dimensions")


def _webp_size(data: bytes) -> tuple[int, int]:
    fmt = data[12:16]
    if fmt == b"VP8 ":  # lossy
        w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return w, h
    if fmt == b"VP8L":  # lossless
        b = data[21:25]
        bits = struct.unpack("<I", b)[0]
        w = (bits & 0x3FFF) + 1
        h = ((bits >> 14) & 0x3FFF) + 1
        return w, h
    if fmt == b"VP8X":  # extended
        w = (data[24] | (data[25] << 8) | (data[26] << 16)) + 1
        h = (data[27] | (data[28] << 8) | (data[29] << 16)) + 1
        return w, h
    raise BadImage("could not read WebP dimensions")
