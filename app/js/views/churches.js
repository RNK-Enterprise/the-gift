// Churches near you, from OpenStreetMap (via our server, which rounds the
// location to ~1 km before asking). Exact distances are worked out here in
// the browser, from the precise position, which never leaves the device.

import * as api from '../api.js';
import { h, icon, loading, errorBox, toast } from '../ui.js';
import { segmented } from '../main.js';
import * as store from '../store.js';

const RADII = [[2000, '2 km'], [5000, '5 km'], [10000, '10 km'], [25000, '25 km']];
const MILES = /^en-(US|GB|LR|MM)$/i.test(navigator.language || '');

function distance(lat1, lon1, lat2, lon2) {
  const rad = Math.PI / 180;
  const a = Math.sin(((lat2 - lat1) * rad) / 2) ** 2
    + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(((lon2 - lon1) * rad) / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(a));
}

function fmtDistance(m) {
  if (MILES) {
    const mi = m / 1609.34;
    return mi < 0.1 ? `${Math.round(m * 1.094)} yd` : `${mi.toFixed(mi < 10 ? 1 : 0)} mi`;
  }
  return m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(m < 10000 ? 1 : 0)} km`;
}

function placeCard(p) {
  const osm = `https://www.openstreetmap.org/${p.id}`;
  const directions = `https://www.openstreetmap.org/directions?to=${p.lat}%2C${p.lon}`;
  return h('article', { class: 'card place' },
    h('div', { class: 'place-top' },
      h('h3', { text: p.name || 'Church (name not listed)' }),
      h('span', { class: 'dist', text: fmtDistance(p.distance) })),
    p.denomination ? h('div', {}, h('span', { class: 'pill', text: p.denomination[0].toUpperCase() + p.denomination.slice(1) })) : null,
    p.address ? h('p', { class: 'addr', text: p.address }) : null,
    p.service_times ? h('p', { class: 'times', text: `Services: ${p.service_times}` }) : null,
    h('div', { class: 'links' },
      p.website && /^https?:\/\//i.test(p.website) ? h('a', { class: 'btn sm', href: p.website, target: '_blank', rel: 'noopener noreferrer' }, icon('globe'), 'Website') : null,
      p.phone ? h('a', { class: 'btn sm', href: `tel:${p.phone.replace(/[^+\d]/g, '')}` }, icon('phone'), 'Call') : null,
      h('a', { class: 'btn sm', href: directions, target: '_blank', rel: 'noopener noreferrer' }, icon('route'), 'Directions'),
      h('a', { class: 'btn ghost sm', href: osm, target: '_blank', rel: 'noopener noreferrer' }, 'Map')));
}

export async function render(root) {
  const saved = store.load('churchSearch', null); // {label, lat, lon, radius} — a place name, not a GPS fix
  let radius = (saved && saved.radius) || 5000;
  let origin = null; // {lat, lon, label, precise}
  const results = h('div');
  const town = h('input', { class: 'input', type: 'search', placeholder: 'Town, city or postcode', 'aria-label': 'Town, city or postcode',
    value: saved && saved.label ? saved.label : '' });
  const geoList = h('div', { class: 'geo-results' });

  const search = async () => {
    if (!origin) return;
    geoList.replaceChildren();
    results.replaceChildren(loading());
    try {
      const { places } = await api.get('churches', {
        lat: origin.lat.toFixed(2), lon: origin.lon.toFixed(2), radius });
      for (const p of places) p.distance = distance(origin.lat, origin.lon, p.lat, p.lon);
      places.sort((a, b) => (!a.name - !b.name) || a.distance - b.distance);
      const inRange = places.filter((p) => p.distance <= radius * 1.05);
      results.replaceChildren(
        h('p', { class: 'muted', text: inRange.length
          ? `${inRange.length} church${inRange.length === 1 ? '' : 'es'} within ${RADII.find((x) => x[0] === radius)[1]} of ${origin.label}`
          : `No churches are mapped within ${RADII.find((x) => x[0] === radius)[1]} of ${origin.label}. Try a wider distance.` }),
        h('div', { class: 'places' }, inRange.map(placeCard)),
        h('p', { class: 'attrib' }, 'Church data © ', h('a', { href: 'https://www.openstreetmap.org/copyright', target: '_blank', rel: 'noopener' }, 'OpenStreetMap contributors'),
          '. Something missing or wrong? Anyone can ', h('a', { href: 'https://www.openstreetmap.org/fixthemap', target: '_blank', rel: 'noopener' }, 'add it to the map'), '.'));
    } catch (e) {
      results.replaceChildren(errorBox(e, search));
    }
  };

  const useLocation = () => {
    if (!navigator.geolocation) { toast("This browser can't share its location"); return; }
    results.replaceChildren(loading());
    navigator.geolocation.getCurrentPosition((pos) => {
      origin = { lat: pos.coords.latitude, lon: pos.coords.longitude, label: 'you', precise: true };
      search();
    }, (err) => {
      results.replaceChildren(h('div', { class: 'empty' }, h('h3', { text: "Couldn't get your location" }),
        h('p', { text: err.code === 1 ? 'Location permission was declined. Search for your town instead.' : 'Search for your town instead.' })));
    }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
  };

  const findTown = async (e) => {
    e && e.preventDefault();
    const q = town.value.trim();
    if (q.length < 2) return;
    geoList.replaceChildren(loading());
    try {
      const { results: found } = await api.get('geocode', { q });
      if (!found.length) { geoList.replaceChildren(h('p', { class: 'muted', text: 'No place found with that name.' })); return; }
      const pick = (g) => {
        const label = g.name.split(',').slice(0, 2).join(',');
        origin = { lat: g.lat, lon: g.lon, label, precise: false };
        store.save('churchSearch', { label, lat: g.lat, lon: g.lon, radius });
        town.value = label;
        search();
      };
      if (found.length === 1) pick(found[0]);
      else geoList.replaceChildren(...found.map((g) => h('button', { type: 'button', text: g.name, on: { click: () => pick(g) } })));
    } catch (err) {
      geoList.replaceChildren(errorBox(err));
    }
  };

  root.append(h('div', { class: 'page' },
    h('header', { class: 'page-head' }, h('p', { class: 'eyebrow', text: 'Churches' }),
      h('h1', { text: 'Find a church near you' }),
      h('p', { class: 'sub', text: 'Christian churches from OpenStreetMap, the free community map. Your location is rounded to about a kilometre before we look anything up, and it is never stored.' })),
    h('section', { class: 'card locate' },
      h('button', { class: 'btn primary', type: 'button', on: { click: useLocation } }, icon('locate'), 'Use my location'),
      h('div', { class: 'muted small center', text: 'or' }),
      h('form', { on: { submit: findTown } }, town, h('button', { class: 'btn', type: 'submit' }, icon('search'), 'Search')),
      geoList,
      h('div', { class: 'row wrap' }, h('span', { class: 'muted small', text: 'Within' }),
        segmented(RADII.map(([v, l]) => [v, l]), radius, (v) => {
          radius = v;
          if (saved || origin) store.save('churchSearch', { ...(store.load('churchSearch', {}) || {}), radius });
          search();
        }))),
    results));

  if (saved && saved.lat != null) {
    origin = { lat: saved.lat, lon: saved.lon, label: saved.label, precise: false };
    search();
  }
  return null;
}
