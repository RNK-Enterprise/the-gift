"""Draws the app's illustrations (app/img/*.svg) in the logo's navy and gold.
Run from the repo root: python3 design/make_illustrations.py"""
from pathlib import Path

OUT = Path("app/img")


def svg(w, h, body, extra=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'{extra}{body}</svg>\n')


files = {}
# Flat, soft, on a transparent ground so they sit on either theme.
files['dawn.svg'] = svg(640, 320, '''<defs>
    <radialGradient id="sun" cx=".5" cy="1" r=".6"><stop offset="0" stop-color="#f5c56b" stop-opacity=".95"/><stop offset=".35" stop-color="#f5c56b" stop-opacity=".35"/><stop offset="1" stop-color="#f5c56b" stop-opacity="0"/></radialGradient>
    <linearGradient id="h1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1d3f9e"/><stop offset="1" stop-color="#e8b552" stop-opacity=".25"/></linearGradient>
    <linearGradient id="h2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0e2a6e"/><stop offset="1" stop-color="#3a63d8" stop-opacity=".2"/></linearGradient>
  </defs>
  <rect width="640" height="320" fill="url(#sun)"/>
  <g stroke="#f5c56b" stroke-opacity=".35" stroke-width="3" stroke-linecap="round">
    <path d="M320 200V70M320 200 230 92M320 200 410 92M320 200 168 134M320 200 472 134M320 200 132 184M320 200 508 184"/>
  </g>
  <circle cx="320" cy="222" r="58" fill="#f5c56b"/>
  <path d="M0 236c90-40 170-46 250-20s170 34 250 4 100-30 140-26V320H0z" fill="url(#h2)"/>
  <path d="M0 262c110-34 210-28 300 0s210 30 340-8V320H0z" fill="url(#h1)"/>''')
files['music.svg'] = svg(640, 320, '''<defs>
    <linearGradient id="w" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#e8b552"/><stop offset="1" stop-color="#3a63d8"/></linearGradient>
  </defs>
  <g fill="none" stroke="url(#w)" stroke-linecap="round">
    <path d="M20 170c40 0 40-70 80-70s40 140 80 140 40-200 80-200 40 260 80 260 40-200 80-200 40 140 80 140 40-70 80-70" stroke-width="5" stroke-opacity=".9"/>
    <path d="M20 170c40 0 40-40 80-40s40 80 80 80 40-120 80-120 40 160 80 160 40-120 80-120 40 80 80 80 40-40 80-40" stroke-width="3" stroke-opacity=".45"/>
  </g>
  <g fill="#f5c56b">
    <path d="M496 70v62a18 14 0 1 1-8-12V84l52-12v50a18 14 0 1 1-8-12V70z" opacity=".95"/>
    <path d="M120 236v34a12 9 0 1 1-6-8v-34l30-6v4z" opacity=".6"/>
  </g>''')
files['together.svg'] = svg(640, 320, '''<defs>
    <linearGradient id="p" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e8b552" stop-opacity=".9"/><stop offset="1" stop-color="#e8b552" stop-opacity=".35"/></linearGradient>
    <linearGradient id="q" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a63d8" stop-opacity=".9"/><stop offset="1" stop-color="#3a63d8" stop-opacity=".35"/></linearGradient>
    <linearGradient id="r" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f5c56b" stop-opacity=".95"/><stop offset="1" stop-color="#f5c56b" stop-opacity=".4"/></linearGradient>
  </defs>
  <ellipse cx="320" cy="282" rx="230" ry="22" fill="#e8b552" opacity=".1"/>
  <g><circle cx="196" cy="128" r="34" fill="url(#q)"/><path d="M136 276c0-56 26-96 60-96s60 40 60 96z" fill="url(#q)"/></g>
  <g><circle cx="444" cy="128" r="34" fill="url(#r)"/><path d="M384 276c0-56 26-96 60-96s60 40 60 96z" fill="url(#r)"/></g>
  <g><circle cx="320" cy="104" r="40" fill="url(#p)"/><path d="M250 276c0-66 30-112 70-112s70 46 70 112z" fill="url(#p)"/></g>
  <g fill="none" stroke="#e7f4f8" stroke-opacity=".9" stroke-width="6" stroke-linejoin="round">
    <path d="M320 236c-16-12-38-16-60-14v52c22-2 44 2 60 14 16-12 38-16 60-14v-52c-22-2-44 2-60 14z" fill="#070b14" fill-opacity=".55"/>
    <path d="M320 236v52"/>
  </g>
  <g fill="#e7f4f8" opacity=".85">
    <path d="M500 40h96a14 14 0 0 1 14 14v40a14 14 0 0 1-14 14h-58l-22 18v-18h-16a14 14 0 0 1-14-14V54a14 14 0 0 1 14-14z" opacity=".22"/>
    <circle cx="526" cy="74" r="6"/><circle cx="548" cy="74" r="6"/><circle cx="570" cy="74" r="6"/>
  </g>''')
files['journey.svg'] = svg(640, 320, '''<defs>
    <linearGradient id="m" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a63d8" stop-opacity=".55"/><stop offset="1" stop-color="#3a63d8" stop-opacity=".08"/></linearGradient>
    <linearGradient id="n" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e8b552" stop-opacity=".5"/><stop offset="1" stop-color="#e8b552" stop-opacity=".08"/></linearGradient>
  </defs>
  <circle cx="470" cy="70" r="30" fill="#f5c56b" opacity=".9"/>
  <path d="M0 300 210 90l90 90 70-60 270 180z" fill="url(#m)"/>
  <path d="M60 320 300 150l120 90 80-50 140 130z" fill="url(#n)"/>
  <path d="M120 312c60-10 90-40 130-60s70-10 100-40 30-60 70-72" fill="none" stroke="#f5c56b" stroke-width="5" stroke-linecap="round" stroke-dasharray="2 14"/>
  <g fill="#f5c56b"><circle cx="120" cy="312" r="7"/><circle cx="250" cy="252" r="7"/><circle cx="350" cy="212" r="7"/><circle cx="420" cy="140" r="9"/></g>''')
files['hymn.svg'] = svg(512, 512, f'''<defs>
    <linearGradient id="hb" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b2466"/><stop offset="1" stop-color="#020a1f"/></linearGradient>
    <radialGradient id="hg" cx=".3" cy=".25" r=".8"><stop offset="0" stop-color="#f5c56b" stop-opacity=".35"/><stop offset="1" stop-color="#f5c56b" stop-opacity="0"/></radialGradient>
  </defs>
  <rect width="512" height="512" fill="url(#hb)"/><rect width="512" height="512" fill="url(#hg)"/>
  <g fill="none" stroke="#f5c56b" stroke-width="14" stroke-linejoin="round" stroke-linecap="round" opacity=".95">
    <path d="M256 300c-30-22-72-28-112-25v120c40-3 82 3 112 25 30-22 72-28 112-25V275c-40-3-82 3-112 25z"/><path d="M256 300v120"/>
  </g>
  <path d="M232 96v118a30 24 0 1 1-14-20V122l96-22v92a30 24 0 1 1-14-20V96z" fill="#e7f4f8" opacity=".9"/>''')


for name, content in files.items():
    (OUT / name).write_text(content)
    print(name, len(content))
