// The Gift — service worker. Network first, always: when online you get the
// current app and texts; when offline you get the last copy you saw. Only
// the app itself and public library data are kept, never account or group
// data (those requests go straight to the network).

const CACHE = 'gift-app-v3';
const SHELL = [
  '/app/', '/app/app.css', '/app/manifest.webmanifest',
  '/app/js/main.js', '/app/js/ui.js', '/app/js/api.js', '/app/js/store.js', '/app/js/bible.js', '/app/js/dates.js',
  '/app/js/progress.js', '/app/js/player.js',
  '/app/js/views/today.js', '/app/js/views/read.js', '/app/js/views/plans.js', '/app/js/views/journal.js',
  '/app/js/views/community.js', '/app/js/views/churches.js', '/app/js/views/me.js', '/app/js/views/music.js',
  '/app/js/views/premium.js', '/app/js/views/safety.js', '/app/js/sync.js',
  '/app/icons/icon-192.png', '/app/icons/favicon-64.png', '/app/img/logo.jpg',
];
const LIBRARY_API = /^\/api\/(translations|books|chapter|plans|devotional|commentaries|commentary)(\/|$|\?)/;

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k.startsWith('gift-app-') && k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const isShell = url.pathname.startsWith('/app/');
  const isLibrary = LIBRARY_API.test(url.pathname + url.search);
  if (!isShell && !isLibrary) return; // accounts, groups, search, places: network only

  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const res = await fetch(req);
      if (res.ok) cache.put(isShell && req.mode === 'navigate' ? '/app/' : req, res.clone());
      return res;
    } catch (err) {
      // any cache: the app shell, or a translation downloaded for offline (Plus)
      const hit = await caches.match(isShell && req.mode === 'navigate' ? '/app/' : req);
      if (hit) return hit;
      throw err;
    }
  })());
});
