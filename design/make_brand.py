"""Builds every app/brand image from design/the-gift-logo.png (the source of
truth). Run from the repo root: python3 design/make_brand.py
Needs Pillow and numpy (dev machine only; nothing here runs on the server)."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SRC = Image.open('design/the-gift-logo.png').convert('RGB')
ICONS, IMG = Path('app/icons'), Path('app/img')
MARK_BOX = (100, 105, 1154, 795)   # the book and cross, with a margin
MARK_MID = 464 - MARK_BOX[1]       # visual centre of the mark inside the crop


def background(size):
    """The logo's navy, glowing a little toward the centre."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    d = np.sqrt((xx - size / 2) ** 2 + (yy - size * .44) ** 2) / (size * .72)
    t = np.clip(d, 0, 1)[..., None]
    inner, outer = np.array([2, 26, 68], np.float32), np.array([0, 7, 28], np.float32)
    return Image.fromarray((inner * (1 - t) + outer * t).astype(np.uint8), 'RGB')


def feathered(img, edge):
    w, h = img.size
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((edge, edge, w - edge, h - edge), radius=edge, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(edge / 2))


def mark_on_navy(size, width_fraction):
    """The book and cross, centred on navy, `width_fraction` of the canvas wide."""
    crop = SRC.crop(MARK_BOX)
    scale = size * width_fraction / 955  # 955 px: the mark's own width in the source
    crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.LANCZOS)
    canvas = background(size)
    x = (size - crop.width) // 2
    y = round(size / 2 - MARK_MID * scale)
    canvas.paste(crop, (x, y), feathered(crop, max(8, round(40 * scale))))
    return canvas


def rounded(img, radius_fraction=.22):
    s = img.size[0]
    big = img.resize((s * 4, s * 4), Image.LANCZOS)
    m = Image.new('L', big.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, s * 4 - 1, s * 4 - 1), radius=round(s * 4 * radius_fraction), fill=255)
    big = big.convert('RGBA')
    big.putalpha(m)
    return big.resize((s, s), Image.LANCZOS)


if __name__ == '__main__':
    master = mark_on_navy(1024, .80)
    rounded(master).resize((512, 512), Image.LANCZOS).save(ICONS / 'icon-512.png', optimize=True)
    rounded(master).resize((192, 192), Image.LANCZOS).save(ICONS / 'icon-192.png', optimize=True)
    master.resize((180, 180), Image.LANCZOS).save(ICONS / 'apple-touch-icon.png', optimize=True)
    master.resize((512, 512), Image.LANCZOS).save(ICONS / 'play-icon-512.png', optimize=True)  # Play listing
    # maskable: Android may crop to a circle 80% wide, so the mark sits well inside
    mark_on_navy(1024, .60).resize((512, 512), Image.LANCZOS).save(ICONS / 'maskable-512.png', optimize=True)
    for px in (32, 64):  # favicons: the mark alone reads best when tiny
        rounded(mark_on_navy(256, .92), .18).resize((px, px), Image.LANCZOS).save(ICONS / f'favicon-{px}.png', optimize=True)
    SRC.resize((720, 720), Image.LANCZOS).save(IMG / 'logo.jpg', quality=88, optimize=True, progressive=True)
    SRC.crop((0, 760, 1254, 1120)).resize((627, 180), Image.LANCZOS).save(IMG / 'wordmark.jpg', quality=88, optimize=True)
    print('done')
