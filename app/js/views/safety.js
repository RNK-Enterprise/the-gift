// Report and block: required for anything people post (chat, profiles,
// songs). Reports go to the site admins with a copy of what was reported.

import * as api from '../api.js';
import { h, sheet, toast } from '../ui.js';

const REASONS = [
  ['spam', 'Spam or scams'], ['harassment', 'Harassment or bullying'], ['hate', 'Hate or discrimination'],
  ['sexual', 'Sexual content'], ['violence', 'Violence or threats'], ['self-harm', 'Self-harm or suicide'],
  ['misinformation', 'False or misleading'], ['copyright', 'Copyright (not theirs to share)'], ['other', 'Something else'],
];

// kind: 'message' | 'user' | 'song' | 'artist'; userId lets you also block
export function reportSheet({ kind, id, name, userId }) {
  const sh = sheet(kind === 'user' ? `Report ${name}` : 'Report');
  const choices = h('div', { class: 'stack' }, REASONS.map(([value, label], i) =>
    h('label', { class: 'check-row' }, h('input', { type: 'radio', name: 'reason', value, checked: i === 0 }), h('span', { text: label }))));
  const detail = h('textarea', { class: 'textarea', rows: 3, maxlength: 1000, placeholder: 'Anything that helps us understand (optional)' });
  const blockId = kind === 'user' ? id : userId;
  const alsoBlock = blockId ? h('input', { type: 'checkbox', checked: kind === 'user' }) : null;
  const err = h('p', { class: 'form-error', role: 'alert' });
  sh.body.append(
    h('p', { class: 'muted small', text: 'Reports go to the site admins, never to the person you report. If someone is in danger, contact local emergency services.' }),
    h('form', { class: 'form', on: { submit: async (e) => {
      e.preventDefault();
      const reason = choices.querySelector('input:checked').value;
      try {
        await api.post('report', { kind, id, reason, detail: detail.value });
        if (alsoBlock && alsoBlock.checked) await api.post('block', { user_id: blockId });
        sh.close();
        toast(alsoBlock && alsoBlock.checked ? 'Reported and blocked. Thank you.' : 'Reported. Thank you.');
      } catch (ex) { err.textContent = ex.message; }
    } } },
    choices, detail,
    alsoBlock ? h('label', { class: 'check-row' }, alsoBlock, h('span', { text: 'Also block them: you won’t see their messages and they can’t add you as a friend.' })) : null,
    err, h('button', { class: 'btn primary', type: 'submit' }, 'Send report')));
}
