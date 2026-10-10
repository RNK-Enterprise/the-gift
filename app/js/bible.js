// Book names, references and text folding shared by the views.

export const OT = ['Genesis', 'Exodus', 'Leviticus', 'Numbers', 'Deuteronomy', 'Joshua', 'Judges', 'Ruth',
  'I Samuel', 'II Samuel', 'I Kings', 'II Kings', 'I Chronicles', 'II Chronicles', 'Ezra', 'Nehemiah', 'Esther',
  'Job', 'Psalms', 'Proverbs', 'Ecclesiastes', 'Song of Solomon', 'Isaiah', 'Jeremiah', 'Lamentations',
  'Ezekiel', 'Daniel', 'Hosea', 'Joel', 'Amos', 'Obadiah', 'Jonah', 'Micah', 'Nahum', 'Habakkuk', 'Zephaniah',
  'Haggai', 'Zechariah', 'Malachi'];
export const NT = ['Matthew', 'Mark', 'Luke', 'John', 'Acts', 'Romans', 'I Corinthians', 'II Corinthians',
  'Galatians', 'Ephesians', 'Philippians', 'Colossians', 'I Thessalonians', 'II Thessalonians', 'I Timothy',
  'II Timothy', 'Titus', 'Philemon', 'Hebrews', 'James', 'I Peter', 'II Peter', 'I John', 'II John', 'III John',
  'Jude', 'Revelation of John'];
const OT_SET = new Set(OT);
const NT_SET = new Set(NT);

export function testament(book) {
  return OT_SET.has(book) ? 'ot' : NT_SET.has(book) ? 'nt' : 'other';
}

// The library names books the way the source files do ("I Samuel",
// "Revelation of John"); people read "1 Samuel" and "Revelation".
export function bookName(book) {
  if (book === 'Revelation of John') return 'Revelation';
  return book.replace(/^(IV|III|II|I) /, (m, r) => `${{ I: 1, II: 2, III: 3, IV: 4 }[r]} `);
}

// one psalm is "Psalm 23"; the book is "Psalms"
const chapterBook = (b) => (b === 'Psalms' ? 'Psalm' : bookName(b));

export function refLabel({ b, c, v, v2 }) {
  if (!c) return bookName(b);
  let s = `${chapterBook(b)} ${c}`;
  if (v) s += `:${v}`;
  if (v2 && v2 !== v) s += `–${v2}`;
  return s;
}

// A label for an arbitrary set of selected verse numbers: 3, 5–7, 9
export function versesLabel(b, c, verses) {
  const vs = [...verses].sort((x, y) => x - y);
  const runs = [];
  for (const v of vs) {
    const last = runs[runs.length - 1];
    if (last && v === last[1] + 1) last[1] = v; else runs.push([v, v]);
  }
  return `${chapterBook(b)} ${c}:${runs.map(([a, z]) => (a === z ? a : `${a}–${z}`)).join(', ')}`;
}

export function readHash({ t, b, c, v }) {
  const p = new URLSearchParams({ t, b, c });
  if (v) p.set('v', v);
  return `#/read?${p}`;
}

// ---------------------------------------------------------- parsing refs

const ROMAN = { 1: 'i', 2: 'ii', 3: 'iii', 4: 'iv', i: 'i', ii: 'ii', iii: 'iii', iv: 'iv' };
// abbreviations that aren't simply the start of a book's name
const ALIASES = {
  gn: 'Genesis', ex: 'Exodus', lv: 'Leviticus', nm: 'Numbers', nb: 'Numbers', dt: 'Deuteronomy',
  jsh: 'Joshua', jdg: 'Judges', jgs: 'Judges', rth: 'Ruth', sm: 'Samuel', kgs: 'Kings', ki: 'Kings',
  chr: 'Chronicles', ch: 'Chronicles', nh: 'Nehemiah', jb: 'Job', ps: 'Psalms', psa: 'Psalms', pss: 'Psalms',
  psalm: 'Psalms', prv: 'Proverbs', pr: 'Proverbs', qoh: 'Ecclesiastes', ec: 'Ecclesiastes',
  song: 'Song of Solomon', sos: 'Song of Solomon', sng: 'Song of Solomon', cant: 'Song of Solomon',
  canticles: 'Song of Solomon', 'song of songs': 'Song of Solomon', isa: 'Isaiah', is: 'Isaiah',
  ezk: 'Ezekiel', dn: 'Daniel', jl: 'Joel', am: 'Amos', jnh: 'Jonah', mc: 'Micah', hb: 'Habakkuk',
  hg: 'Haggai', zc: 'Zechariah', ml: 'Malachi', mt: 'Matthew', mk: 'Mark', mrk: 'Mark', lk: 'Luke',
  jn: 'John', jhn: 'John', rm: 'Romans', php: 'Philippians', phil: 'Philippians', th: 'Thessalonians',
  thess: 'Thessalonians', tm: 'Timothy', phlm: 'Philemon', phm: 'Philemon', jas: 'James', jm: 'James',
  pt: 'Peter', pet: 'Peter', jud: 'Jude', rv: 'Revelation of John', rev: 'Revelation of John',
  revelation: 'Revelation of John', revelations: 'Revelation of John', sir: 'Sirach', ecclus: 'Sirach',
  wis: 'Wisdom', macc: 'Maccabees', mac: 'Maccabees', tob: 'Tobit', jdt: 'Judith', bar: 'Baruch',
};

function splitBook(name) {
  // "I Samuel" → ['i', 'samuel']; "Song of Solomon" → ['', 'songofsolomon']
  const m = /^(IV|III|II|I) (.+)$/.exec(name);
  return m ? [m[1].toLowerCase(), squash(m[2])] : ['', squash(name)];
}
const squash = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, '');

export function findBook(text, books, { exact = false } = {}) {
  let m = /^\s*([1-4]|iv|iii|ii|i)(?:\s+|(?=[a-z]))(.+)$/i.exec(text);
  let num = '';
  let rest = text;
  if (m && (/^\d/.test(m[1]) || /\s/.test(text.slice(m[1].length, m[1].length + 1)))) {
    num = ROMAN[m[1].toLowerCase()];
    rest = m[2];
  }
  const want = squash(rest);
  if (!want) return null;
  const alias = ALIASES[rest.trim().toLowerCase().replace(/\.$/, '')] || ALIASES[want];
  const named = books.map((b) => [b, ...splitBook(b)]);
  const same = named.filter(([, n]) => n === num);
  if (alias) {
    const hit = same.find(([b, , s]) => b === alias || s === squash(alias));
    if (hit) return hit[0];
  }
  const hit = same.find(([, , s]) => s === want) || (!exact && same.find(([, , s]) => s.startsWith(want)));
  return hit ? hit[0] : null;
}

// "John 3:16", "1 cor 13", "ps 23:1-4", "jude 3" → {b, c, v, v2}; null if it
// doesn't look like a reference to a book this translation has.
export function parseRef(input, books, chaptersOf) {
  const m = /^\s*(.+?)\.?\s+(\d{1,3})(?:\s*[:.,]\s*(\d{1,3})(?:\s*[-–—]\s*(\d{1,3}))?)?\s*$/.exec(input)
    || /^\s*((?:[1-4]\s*)?[a-z][a-z .]*?)\.?\s*$/i.exec(input);
  if (!m) return null;
  // a bare word must name a book outright: "mark" yes, "jo" or "love" no
  const b = findBook(m[1], books, { exact: !m[2] });
  if (!b) return null;
  let c = m[2] ? Number(m[2]) : 1;
  let v = m[3] ? Number(m[3]) : null;
  let v2 = m[4] ? Number(m[4]) : null;
  const chapters = chaptersOf ? chaptersOf(b) : null;
  if (chapters && chapters.length === 1 && m[2] && !m[3] && c !== chapters[0]) {
    v = c; c = chapters[0]; // "Jude 3" is a verse: one-chapter books
  }
  if (chapters && !chapters.includes(c)) return null;
  return { b, c, v, v2 };
}

// ------------------------------------------------------------ folding

// Mirrors the server's search folding (gift_library.fold) closely enough
// to highlight what matched: no case, no accents or vowel points.
const KEEP = /[゙゚]/;
export function foldChar(ch) {
  return ch.normalize('NFD').replace(/\p{Mn}/gu, (m) => (KEEP.test(m) ? m : '')).normalize('NFC')
    .toLowerCase().replace(/ς/g, 'σ').replace(/ß/g, 'ss');
}

export function queryTerms(q) {
  q = q.trim();
  const quoted = /^["“”](.*)["“”]$/.exec(q);
  const terms = quoted ? [quoted[1].trim()] : q.split(/\s+/);
  return terms.map((t) => [...t].map(foldChar).join('')).filter(Boolean);
}

// As on the server: in scripts that space their words, a term must start a
// word ("love" marks loved, not beloved); elsewhere any substring counts.
const WORD_SCRIPT = /[\p{Script=Latin}\p{Script=Greek}\p{Script=Cyrillic}\p{Script=Armenian}\p{Script=Georgian}\p{Script=Coptic}\p{Script=Gothic}\p{Script=Cherokee}\p{Nd}]/u;
const ALNUM = /[\p{L}\p{N}]/u;

// Split text into [plain, match, plain, …] pieces for the folded terms.
export function markMatches(text, terms) {
  const chars = [...text];
  let folded = '';
  const at = []; // folded index → original char index
  chars.forEach((ch, i) => {
    const f = foldChar(ch);
    for (let k = 0; k < f.length; k++) at.push(i);
    folded += f;
  });
  const marks = new Array(chars.length).fill(false);
  for (const term of terms) {
    const word = WORD_SCRIPT.test(term[0] || '');
    let from = 0;
    while (term && (from = folded.indexOf(term, from)) !== -1) {
      if (!word || from === 0 || !ALNUM.test(folded[from - 1])) {
        for (let k = from; k < from + term.length; k++) marks[at[k]] = true;
        from += term.length;
      } else {
        from += 1;
      }
    }
  }
  const out = [];
  let buf = '', on = false;
  chars.forEach((ch, i) => {
    if (marks[i] !== on) { if (buf) out.push([buf, on]); buf = ''; on = marks[i]; }
    buf += ch;
  });
  if (buf) out.push([buf, on]);
  return out;
}

// ----------------------------------------------------------- languages

let names;
export function languageName(code) {
  if (!code) return 'Other';
  try {
    names = names || new Intl.DisplayNames(['en'], { type: 'language' });
    const n = names.of(code);
    if (n && n.toLowerCase() !== code.toLowerCase()) return n;
  } catch { /* unknown tag */ }
  return { bea: 'Beaver (Danezaa)', tlh: 'Klingon', sml: 'Central Sama', tsg: 'Tausug', pon: 'Pohnpeian',
    'cop-sa': 'Coptic (Sahidic)', enm: 'Middle English', hbo: 'Ancient Hebrew' }[code] || code;
}

export const LICENCE_CLASS = {
  'Public domain': 'pd', 'Open licence': 'open', 'Non-commercial': 'nc',
  'CrossWire-only permission': 'cw', Unknown: 'unk',
};

export function coverage(t) {
  const parts = [];
  if (t.ot && t.nt) parts.push(t.ot === 39 && t.nt === 27 ? 'Whole Bible' : 'OT + NT');
  else if (t.nt) parts.push(t.nt === 27 ? 'New Testament' : `${t.nt} NT book${t.nt > 1 ? 's' : ''}`);
  else if (t.ot) parts.push(t.ot === 39 ? 'Old Testament' : `${t.ot} OT book${t.ot > 1 ? 's' : ''}`);
  if (t.other) parts.push(`+${t.other} more`);
  return parts.join(' ');
}
