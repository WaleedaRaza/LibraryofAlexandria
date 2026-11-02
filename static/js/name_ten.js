// Name Ten: ten slots with book search, then submit, ponder and show the score.
(() => {
  const root = document.getElementById('ten');
  if (!root) return;

  const form = document.getElementById('ten-form');
  const submitButton = document.getElementById('ten-submit');
  const countLine = document.getElementById('ten-count');
  const errorLine = document.getElementById('ten-error');
  const pondering = document.getElementById('ten-pondering');
  const ponderingLine = document.getElementById('ten-pondering-line');
  const result = document.getElementById('ten-result');
  const signedIn = root.dataset.signedIn === 'true';
  let gameId = Number(root.dataset.dailyGame || root.dataset.freeGame || 0);

  // --- the player's anonymous id (only a session cookie survives our hosting) ---
  const ANON_KEY = 'libxndr.ten.anon';
  const storage = (() => { try { return window.localStorage; } catch (_) { return null; } })();
  const newId = () => (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
    : 'xxxxxxxx-xxxx-4xxx-8xxx-xxxxxxxxxxxx'.replace(/x/g, () => Math.floor(Math.random() * 16).toString(16));
  let anonId = storage && storage.getItem(ANON_KEY);
  if (!anonId && !signedIn) {
    anonId = newId();
    try { storage && storage.setItem(ANON_KEY, anonId); } catch (_) { /* private mode: one-page id */ }
  }
  if (signedIn && anonId) {
    fetch('/ten/claim', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ anon_id: anonId }) })
      .then((response) => { if (response.ok) { try { storage.removeItem(ANON_KEY); } catch (_) { /* fine */ } } })
      .catch(() => {});
  }

  // --- game tabs ---
  root.querySelectorAll('.ten-game').forEach((tab) => {
    tab.addEventListener('click', () => {
      root.querySelectorAll('.ten-game').forEach((other) => other.setAttribute('aria-selected', String(other === tab)));
      gameId = Number(tab.dataset.game);
    });
  });

  // --- slots ---
  const normal = (text) => (text || '').toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, ' ').trim();
  const splitTyped = (text) => {
    const match = text.match(/^(.*?)\s+(?:—|–|-|by)\s+(.+)$/i);
    return match ? { title: match[1].trim(), author: match[2].trim() } : { title: text.trim(), author: '' };
  };
  const slots = Array.from(root.querySelectorAll('.ten-slot')).map((element) => ({
    element,
    input: element.querySelector('input'),
    author: element.querySelector('.ten-slot-author'),
    options: element.querySelector('.ten-options'),
    clear: element.querySelector('.ten-clear'),
    picked: null,        // {title, author, source} once chosen from the list
    results: [],
    active: -1,
    timer: null,
    request: null,
  }));

  const value = (slot) => slot.picked || (slot.input.value.trim() ? splitTyped(slot.input.value) : null);

  function refresh() {
    const seen = new Set();
    let filled = 0;
    let duplicate = false;
    slots.forEach((slot) => {
      const book = value(slot);
      slot.element.classList.toggle('is-filled', Boolean(book));
      slot.clear.hidden = !book;
      if (!book) return;
      const key = `${normal(book.title)}|${normal(book.author)}`;
      duplicate = duplicate || seen.has(key);
      slot.element.classList.toggle('is-duplicate', seen.has(key));
      seen.add(key);
      filled += 1;
    });
    countLine.textContent = duplicate ? 'The same book is in two slots' : `${filled} of 10`;
    submitButton.disabled = filled !== 10 || duplicate;
  }

  function closeOptions(slot) {
    slot.options.hidden = true;
    slot.options.replaceChildren();
    slot.input.setAttribute('aria-expanded', 'false');
    slot.input.removeAttribute('aria-activedescendant');
    slot.active = -1;
  }

  function pick(slot, book) {
    slot.picked = { title: book.title, author: book.author || '', source: book.source };
    slot.input.value = book.title;
    slot.author.textContent = book.author || '';
    slot.element.dataset.source = book.source;
    closeOptions(slot);
    refresh();
    const next = slots.find((other) => !value(other));
    if (next) next.input.focus();
  }

  function highlight(slot, index) {
    const rows = Array.from(slot.options.children);
    slot.active = Math.max(-1, Math.min(rows.length - 1, index));
    rows.forEach((row, i) => row.setAttribute('aria-selected', String(i === slot.active)));
    if (slot.active >= 0) slot.input.setAttribute('aria-activedescendant', rows[slot.active].id);
  }

  function showOptions(slot, results) {
    slot.results = results;
    slot.options.replaceChildren();
    if (!results.length) { closeOptions(slot); return; }
    results.forEach((book, index) => {
      const row = document.createElement('li');
      row.id = `${slot.options.id}-${index}`;
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', 'false');
      const title = document.createElement('strong');
      title.textContent = book.title;
      const meta = document.createElement('span');
      meta.textContent = [book.author, book.source === 'library' ? 'in the library' : ''].filter(Boolean).join(' · ');
      row.append(title, meta);
      row.addEventListener('mousedown', (event) => { event.preventDefault(); pick(slot, book); });
      slot.options.append(row);
    });
    slot.options.hidden = false;
    slot.input.setAttribute('aria-expanded', 'true');
    slot.active = -1;
  }

  async function search(slot) {
    const query = slot.input.value.trim();
    if (query.length < 2) { closeOptions(slot); return; }
    if (slot.request) slot.request.abort();
    slot.request = new AbortController();
    try {
      const response = await fetch(`/ten/search?q=${encodeURIComponent(query)}`, { signal: slot.request.signal });
      if (!response.ok) return;
      const data = await response.json();
      if (document.activeElement === slot.input && slot.input.value.trim() === query) showOptions(slot, data.results || []);
    } catch (_) { /* aborted or offline: typing still works */ }
  }

  slots.forEach((slot) => {
    slot.input.addEventListener('input', () => {
      slot.picked = null;
      slot.author.textContent = '';
      delete slot.element.dataset.source;
      refresh();
      clearTimeout(slot.timer);
      slot.timer = setTimeout(() => search(slot), 220);
    });
    slot.input.addEventListener('keydown', (event) => {
      const open = !slot.options.hidden;
      if (event.key === 'ArrowDown' && open) { event.preventDefault(); highlight(slot, slot.active + 1); }
      else if (event.key === 'ArrowUp' && open) { event.preventDefault(); highlight(slot, slot.active - 1); }
      else if (event.key === 'Enter') {
        event.preventDefault();
        if (open && slot.active >= 0) pick(slot, slot.results[slot.active]);
        else if (open && slot.results.length) pick(slot, slot.results[0]);
        else { closeOptions(slot); const next = slots[slots.indexOf(slot) + 1]; if (next) next.input.focus(); }
      } else if (event.key === 'Escape') closeOptions(slot);
    });
    slot.input.addEventListener('blur', () => setTimeout(() => closeOptions(slot), 120));
    slot.clear.addEventListener('click', () => {
      slot.picked = null;
      slot.input.value = '';
      slot.author.textContent = '';
      delete slot.element.dataset.source;
      refresh();
      slot.input.focus();
    });
  });

  // --- submit, ponder, show ---
  const LINES = [
    'Reading your ten…',
    'Counting who else named each of these…',
    'Checking all forty-five pairs…',
    'Looking for the list closest to yours…',
    'Deciding what to say about you…',
  ];
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function ponder() {
    let line = 0;
    ponderingLine.textContent = LINES[0];
    const timer = setInterval(() => { line = (line + 1) % LINES.length; ponderingLine.textContent = LINES[line]; }, 900);
    return () => clearInterval(timer);
  }

  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const link = (href, text) => { const a = el('a', text); a.href = href; return a; };
  const findHref = (item) => `/library/find?title=${encodeURIComponent(item.title)}&author=${encodeURIComponent(item.author || '')}`;

  function render(data) {
    document.getElementById('ten-score').textContent = data.score;
    document.getElementById('ten-score-line').textContent = data.early
      ? `One of the first ${data.lists_before + 1} lists named here. Scores settle once a couple hundred people have played; yours is frozen now.`
      : `Rarer together than ${data.score} in 100 of the ${data.ranked_against} lists named before yours.`;

    const findings = document.getElementById('ten-findings');
    findings.replaceChildren();
    const pair = data.rarest_pair;
    if (pair) {
      findings.append(el('li', pair.never_seen
        ? `Nobody else has put ${pair.titles[0]} and ${pair.titles[1]} on the same list.`
        : `${pair.titles[0]} and ${pair.titles[1]} have shared a list only ${pair.together} time${pair.together === 1 ? '' : 's'}.`));
    }
    if (data.most_common && data.lists_before >= 20) {
      findings.append(el('li', `${data.most_common.title} is your most expected pick: it is on 1 in ${data.most_common.one_in} lists.`));
    }
    if (data.lists_before > 0) {
      findings.append(el('li', data.closest_shared >= 10
        ? 'Someone has named exactly these ten before.'
        : `The closest earlier list shares ${data.closest_shared} of your ten.`));
    }
    const eleventh = data.missing_eleventh;
    if (eleventh) {
      const row = el('li', `The book people most often name next to yours: ${eleventh.title}${eleventh.author ? ` by ${eleventh.author}` : ''}. `);
      row.append(link(`/library/book/${encodeURIComponent(eleventh.book_id)}`, 'It is in the library'));
      findings.append(row);
    }

    const list = document.getElementById('ten-result-list');
    list.replaceChildren();
    data.items.forEach((item) => {
      const row = el('li', null, `ten-item is-${item.status}`);
      const text = el('div');
      text.append(el('strong', item.title), el('span', item.author || ''));
      row.append(text);
      if (item.status === 'library') row.append(link(`/library/book/${encodeURIComponent(item.book_id)}`, 'Read it here'));
      else if (item.status === 'finder') row.append(link(findHref(item), 'Find a copy'));
      else row.append(link(findHref(item), 'Not found yet · search'));
      list.append(row);
    });
    result.hidden = false;
    result.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (submitButton.disabled) return;
    errorLine.hidden = true;
    const items = slots.map((slot) => { const book = value(slot); return { title: book.title, author: book.author }; });
    form.hidden = true;
    root.querySelector('.ten-games').hidden = true;
    pondering.hidden = false;
    const stop = ponder();
    try {
      const [response] = await Promise.all([
        fetch('/ten/play', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ game_id: gameId, anon_id: signedIn ? null : anonId, items }),
        }),
        wait(2600),   // let it ponder: the pause is part of the game
      ]);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Something went wrong. Try again.');
      render(data);
    } catch (error) {
      form.hidden = false;
      root.querySelector('.ten-games').hidden = false;
      errorLine.textContent = error.message;
      errorLine.hidden = false;
    } finally {
      stop();
      pondering.hidden = true;
    }
  });

  document.getElementById('ten-again').addEventListener('click', () => {
    result.hidden = true;
    const free = root.querySelector(`.ten-game[data-game="${root.dataset.freeGame}"]`);
    if (free) free.click();
    root.querySelectorAll('.ten-game').forEach((tab) => { if (tab !== free) tab.remove(); });
    root.querySelector('.ten-games').hidden = false;
    form.hidden = false;
    slots.forEach((slot) => { slot.picked = null; slot.input.value = ''; slot.author.textContent = ''; delete slot.element.dataset.source; });
    refresh();
    slots[0].input.focus();
  });

  refresh();
})();
