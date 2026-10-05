'use strict';
// WORD-CORRELATION (concordance) engine for Joel / TagAngBiblia. Standalone.
// Builds a co-occurrence map lazily on first correlate()/occurrences() call.
const fs = require('fs');
const path = require('path');

const PY_PATH = path.join(__dirname, "../../python/TagAngBiblia/Joel.py");

function _parsePy(pyPath) {
  const src = fs.readFileSync(pyPath, 'utf8');
  const nameMatch = src.match(/^NAME = (.+)$/m);
  const bookMatch = src.match(/^BOOK = (.+)$/m);
  const chaptersMatch = src.match(/^CHAPTERS = (\{[\s\S]*\})\s*$/m);
  const toJs = (lit) => new Function('"use strict"; return (' + lit + ');')();
  return {
    name: nameMatch ? toJs(nameMatch[1]) : null,
    book: bookMatch ? toJs(bookMatch[1]) : null,
    chapters: toJs(chaptersMatch[1]),
  };
}

const TOKEN_RE = /[\p{L}\p{M}\p{N}'’]+/gu;  // any script, incl. combining marks

let _data = null;
function _load() {
  if (!_data) _data = _parsePy(PY_PATH);
  return _data;
}

let _occ = null;  // Map<word, Array<{chapter, verse}>>
let _cooc = null; // Map<word, Map<otherWord, count>>
function _ensureBuilt() {
  const data = _load();
  if (_cooc) return;
  _occ = new Map();
  _cooc = new Map();
  for (const [chStr, verses] of Object.entries(data.chapters)) {
    const chapter = Number(chStr);
    for (const [vStr, text] of Object.entries(verses)) {
      const verse = Number(vStr);
      const words = text.toLowerCase().match(TOKEN_RE) || [];
      const unique = [...new Set(words)];

      for (const w of unique) {
        let list = _occ.get(w);
        if (!list) _occ.set(w, (list = []));
        list.push({ chapter, verse });
      }
      for (const w of unique) {
        let partners = _cooc.get(w);
        if (!partners) _cooc.set(w, (partners = new Map()));
        for (const other of unique) {
          if (other === w) continue;
          partners.set(other, (partners.get(other) || 0) + 1);
        }
      }
    }
  }
}

/** Every verse (in this book/translation) containing `word`. */
function occurrences(word) {
  _ensureBuilt();
  const data = _load();
  const list = _occ.get(word.toLowerCase()) || [];
  return list.map(({ chapter, verse }) => ({
    chapter,
    verse,
    text: data.chapters[chapter][verse],
  }));
}

/** Words that most often co-occur with `word` in the same verse. */
function correlate(word, opts = {}) {
  const { topN = 20 } = opts;
  _ensureBuilt();
  const partners = _cooc.get(word.toLowerCase());
  if (!partners) return [];
  return [...partners.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN)
    .map(([w, count]) => ({ word: w, count }));
}

module.exports = {
  get name() { return _load().name; },
  get book() { return _load().book; },
  occurrences,
  correlate,
};
