"""
The Gift — "churches near me", from OpenStreetMap.

The browser never talks to a third party: it sends a rounded location here,
and this server asks OpenStreetMap's Overpass API (places of worship tagged
religion=christian) and Nominatim (turning a typed town into coordinates).
So visitors' IP addresses stay with us, positions leave rounded to ~1 km,
and both services' usage policies are respected: a descriptive User-Agent,
one request at a time, at most one Nominatim call per second, and answers
cached for a day.

Map data © OpenStreetMap contributors, ODbL. The app shows that credit.
Set GIFT_PLACES=0 to switch the feature off (no outbound requests at all).
"""

import json
import math
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict

OVERPASS_URL = os.environ.get("GIFT_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
NOMINATIM_URL = os.environ.get("GIFT_NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
USER_AGENT = "TheGift/1.3 (+https://gift.rnkstudios.uk; free Bible library)"
ENABLED = os.environ.get("GIFT_PLACES", "1") != "0"

RADII = (2000, 5000, 10000, 25000)  # metres
RETRY_AFTER = 2.0  # seconds; the public Overpass server sheds load with 429/504
CACHE_SECONDS = 86400
MAX_RESULTS = 80


class PlacesError(Exception):
    pass


def _log(what, err):
    # the visitor gets a friendly "try later"; the journal gets the reason
    sys.stderr.write(f"The Gift: {what} failed: {err!r}\n")


class _TTLCache:
    def __init__(self, size):
        self.size = size
        self.data = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            hit = self.data.get(key)
            if hit and time.time() - hit[0] < CACHE_SECONDS:
                self.data.move_to_end(key)
                return hit[1]
            return None

    def put(self, key, value):
        with self.lock:
            self.data[key] = (time.time(), value)
            while len(self.data) > self.size:
                self.data.popitem(last=False)


def _fetch(url, data=None, timeout=25):
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read(4 * 1024 * 1024).decode("utf-8"))


def distance_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _web(url):
    url = (url or "").strip()
    if url and "://" not in url and "." in url and " " not in url:
        url = "https://" + url
    return url if url.lower().startswith(("http://", "https://")) else ""


def _place(el, lat0, lon0):
    tags = el.get("tags") or {}
    lat = el.get("lat", (el.get("center") or {}).get("lat"))
    lon = el.get("lon", (el.get("center") or {}).get("lon"))
    if lat is None or lon is None:
        return None
    street = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x)
    town = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village") or ""
    address = ", ".join(x for x in (street, town, tags.get("addr:postcode", "")) if x)
    return {
        "id": f"{el.get('type', 'node')}/{el.get('id')}",
        "name": tags.get("name") or tags.get("name:en") or "",
        "denomination": (tags.get("denomination") or "").replace("_", " "),
        "address": address,
        "website": _web(tags.get("website") or tags.get("contact:website")),
        "phone": (tags.get("phone") or tags.get("contact:phone") or "")[:40],
        "service_times": (tags.get("service_times") or "")[:200],
        "wheelchair": tags.get("wheelchair", ""),
        "lat": round(lat, 6), "lon": round(lon, 6),
        "distance": round(distance_m(lat0, lon0, lat, lon)),
    }


class Places:
    def __init__(self, fetch=_fetch, retry_after=RETRY_AFTER):
        self.fetch = fetch
        self.retry_after = retry_after
        self._churches = _TTLCache(500)
        self._geocode = _TTLCache(500)
        self._overpass = threading.Lock()
        self._nominatim = threading.Lock()
        self._nominatim_last = 0.0

    def churches(self, lat, lon, radius):
        if not ENABLED:
            raise PlacesError("The church finder is switched off on this server.")
        lat, lon = round(lat, 2), round(lon, 2)  # ~1 km: enough to search, not to locate
        key = (lat, lon, radius)
        hit = self._churches.get(key)
        if hit is not None:
            return hit
        query = (f'[out:json][timeout:20];'
                 f'nwr["amenity"="place_of_worship"]["religion"="christian"]'
                 f'(around:{radius},{lat},{lon});out center tags 400;')
        if not self._overpass.acquire(timeout=30):
            raise PlacesError("The map service is busy. Try again in a moment.")
        try:
            data = self._overpass_query(query)
        finally:
            self._overpass.release()
        places = [p for p in (_place(el, lat, lon) for el in data.get("elements", [])) if p]
        places.sort(key=lambda p: (not p["name"], p["distance"]))
        places = places[:MAX_RESULTS]
        self._churches.put(key, places)
        return places

    def _overpass_query(self, query):
        body = urllib.parse.urlencode({"data": query}).encode()
        for attempt in (1, 2):
            try:
                return self.fetch(OVERPASS_URL, body)
            except Exception as e:  # network, HTTP or JSON trouble: all mean "not now"
                busy = isinstance(e, (urllib.error.URLError, TimeoutError)) and \
                    getattr(e, "code", 504) in (429, 502, 503, 504)
                _log(f"Overpass request (attempt {attempt})", e)
                if attempt == 1 and busy:
                    time.sleep(self.retry_after)  # overloaded: one polite retry
                    continue
                raise PlacesError("Couldn't reach the map service. Try again later.") from e

    def geocode(self, q):
        if not ENABLED:
            raise PlacesError("The church finder is switched off on this server.")
        q = " ".join(q.split())[:120]
        key = q.lower()
        hit = self._geocode.get(key)
        if hit is not None:
            return hit
        url = NOMINATIM_URL + "?" + urllib.parse.urlencode(
            {"format": "jsonv2", "limit": 5, "q": q, "addressdetails": 0})
        with self._nominatim:  # their policy: at most one request per second
            wait = 1.0 - (time.monotonic() - self._nominatim_last)
            if wait > 0:
                time.sleep(wait)
            try:
                data = self.fetch(url)
            except Exception as e:
                _log("Nominatim request", e)
                raise PlacesError("Couldn't look that place up. Try again later.") from e
            finally:
                self._nominatim_last = time.monotonic()
        out = []
        for r in data if isinstance(data, list) else []:
            try:
                out.append({"name": r.get("display_name", "")[:200],
                            "lat": round(float(r["lat"]), 4), "lon": round(float(r["lon"]), 4)})
            except (KeyError, TypeError, ValueError):
                continue
        self._geocode.put(key, out)
        return out
