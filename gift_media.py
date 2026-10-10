"""
The Gift — uploaded media: profile pictures, artist photos and songs.

Files live under GIFT_DATA_DIR/media/, named by a random id and never by
anything the uploader chose. A file is kept only if its first bytes say it
is a format we serve (JPEG, PNG or WebP pictures; MP3, AAC/M4A, Ogg, WAV
or FLAC audio). The Content-Type the browser claimed is ignored, so an
upload can't be HTML or SVG pretending to be a picture. Pictures are
resized in the browser before upload, so the image limit is small.
"""

import os
import secrets
from pathlib import Path

LIMITS = {"image": 3 * 1024 * 1024, "audio": 40 * 1024 * 1024}
UPLOAD_MAX = max(LIMITS.values())
CHUNK = 256 * 1024


def sniff(head):
    """(kind, mime, ext) from a file's first bytes, or None."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg", ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png", ".png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image", "image/webp", ".webp"
    if head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0
                                   and head[1] & 0x06 != 0):  # MPEG audio frame sync (not AAC ADTS)
        return "audio", "audio/mpeg", ".mp3"
    if head[4:8] == b"ftyp" and head[8:12] in (b"M4A ", b"M4B ", b"mp42", b"isom", b"dash", b"mp41"):
        return "audio", "audio/mp4", ".m4a"
    if len(head) > 1 and head[0] == 0xFF and head[1] & 0xF6 == 0xF0:  # AAC ADTS
        return "audio", "audio/aac", ".aac"
    if head.startswith(b"OggS"):
        return "audio", "audio/ogg", ".ogg"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio", "audio/wav", ".wav"
    if head.startswith(b"fLaC"):
        return "audio", "audio/flac", ".flac"
    return None


def new_id():
    return secrets.token_urlsafe(16)


def media_dir(data_dir):
    d = Path(data_dir) / "media"
    d.mkdir(parents=True, exist_ok=True)
    return d


def receive(stream, length, data_dir):
    """Copy an upload body to a temporary file in the media folder, in
    chunks (never whole into memory). Returns its path; caller cleans up."""
    tmp = media_dir(data_dir) / f".upload-{secrets.token_hex(8)}"
    left = length
    with open(tmp, "wb") as f:
        while left > 0:
            chunk = stream.read(min(CHUNK, left))
            if not chunk:
                break
            f.write(chunk)
            left -= len(chunk)
    if left:
        tmp.unlink(missing_ok=True)
        raise ValueError("upload ended early")
    return tmp


def remove(data_dir, media_id, ext):
    try:
        os.unlink(media_dir(data_dir) / f"{media_id}{ext}")
    except FileNotFoundError:
        pass


def parse_range(header, size):
    """'bytes=START-END' → (start, end) inclusive, or None for a range we
    won't serve. Only single ranges: that is what audio players ask for."""
    if not header or not header.startswith("bytes=") or "," in header:
        return None
    start, _, end = header[6:].strip().partition("-")
    try:
        if start == "":  # the last N bytes
            n = int(end)
            if n <= 0:
                return None
            return max(0, size - n), size - 1
        first = int(start)
        last = int(end) if end else size - 1
    except ValueError:
        return None
    if first >= size or last < first:
        return None
    return first, min(last, size - 1)
