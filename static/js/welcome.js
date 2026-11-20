// First run: doors → starter shelf → ask a book → the eye.
(() => {
  const root = document.querySelector('[data-welcome]');
  if (!root) return;
  const esc = (value) => (window.LibxndrAsk ? window.LibxndrAsk.escapeHtml(value) : String(value ?? ''));

  // ── 01 Doors and the starter shelf ─────────────────────────────────────
  const doors = [...root.querySelectorAll('[data-door]')];
  const cards = [...root.querySelectorAll('[data-door-book]')];
  const boxes = () => [...root.querySelectorAll('[data-starter-grid] input[type="checkbox"]')];
  const saveButton = root.querySelector('[data-save-shelf]');
  const countLabel = root.querySelector('[data-picked-count]');
  const shelfStatus = root.querySelector('[data-shelf-status]');

  const picked = () => {
    const seen = new Map();
    boxes().filter((box) => box.checked).forEach((box) => {
      if (!seen.has(box.value)) {
        seen.set(box.value, { id: box.value, title: box.dataset.title, author: box.dataset.author, questions: JSON.parse(box.dataset.questions || '[]') });
      }
    });
    return [...seen.values()];
  };

  const showDoors = () => {
    const open = new Set(doors.filter((d) => d.getAttribute('aria-pressed') === 'true').map((d) => d.dataset.door));
    const shown = new Set();
    cards.forEach((card) => {
      const value = card.querySelector('input').value;
      // A book in two open doors appears once.
      const visible = open.has(card.dataset.doorBook) && !shown.has(value);
      if (visible) shown.add(value);
      card.hidden = !visible;
    });
  };

  const refresh = () => {
    const chosen = picked();
    countLabel.textContent = String(chosen.length);
    saveButton.disabled = chosen.length === 0;
    renderPicker();
  };

  doors.forEach((door) => door.addEventListener('click', () => {
    const on = door.getAttribute('aria-pressed') !== 'true';
    door.setAttribute('aria-pressed', String(on));
    if (on && !picked().length) {
      // First door: preselect its first three so one click gets a real shelf.
      cards.filter((c) => c.dataset.doorBook === door.dataset.door).slice(0, 3).forEach((c) => { c.querySelector('input').checked = true; });
    }
    showDoors();
    refresh();
  }));

  root.querySelector('[data-starter-grid]').addEventListener('change', (event) => {
    const box = event.target.closest('input[type="checkbox"]');
    if (!box) return;
    boxes().filter((other) => other.value === box.value).forEach((other) => { other.checked = box.checked; });
    refresh();
  });

  saveButton.addEventListener('click', async () => {
    const chosen = picked();
    if (!chosen.length) return;
    saveButton.disabled = true;
    shelfStatus.textContent = 'Saving…';
    try {
      const response = await fetch('/welcome/shelf', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book_ids: chosen.map((b) => b.id) }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Could not save those.');
      shelfStatus.innerHTML = `✓ ${data.saved.length} ${data.saved.length === 1 ? 'book is' : 'books are'} on your <a href="/library/my">reading board</a>. Now ask one of them something ↓`;
      root.querySelector('#shelf').classList.add('is-done');
      root.querySelector('#ask').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      shelfStatus.textContent = error.message;
      saveButton.disabled = false;
    }
  });

  // ── 02 Ask a book ─────────────────────────────────────────────────────
  const picker = root.querySelector('[data-ask-picker]');
  const askForm = root.querySelector('[data-ask-welcome]');
  const suggestions = root.querySelector('[data-ask-suggestions]');
  const defaults = () => {
    // Before anything is picked, offer the first book of each door.
    const seen = new Set();
    return cards.map((card) => card.querySelector('input'))
      .filter((box) => { const first = !seen.has(box.closest('[data-door-book]').dataset.doorBook); seen.add(box.closest('[data-door-book]').dataset.doorBook); return first; })
      .map((box) => ({ id: box.value, title: box.dataset.title, author: box.dataset.author, questions: JSON.parse(box.dataset.questions || '[]') }));
  };

  const selectBook = (book) => {
    askForm.dataset.askBook = book.id;
    picker.querySelectorAll('[role="tab"]').forEach((tab) => tab.setAttribute('aria-selected', String(tab.dataset.book === book.id)));
    suggestions.innerHTML = book.questions.map((q) => `<button type="button" class="ask-chip" data-ask-question="${esc(q)}">${esc(q)}</button>`).join('');
    askForm.querySelector('input[name="question"]').placeholder = `Ask ${book.title} anything`;
    askForm.querySelector('[data-ask-result]').innerHTML = '';
  };

  let pickerBooks = [];
  function renderPicker() {
    const books = picked().length ? picked() : defaults();
    const current = askForm.dataset.askBook;
    pickerBooks = books;
    picker.innerHTML = books.map((b) => `<button type="button" role="tab" data-book="${esc(b.id)}" aria-selected="false"><img src="/library/book/${encodeURIComponent(b.id)}/cover" alt="" loading="lazy"><span>${esc(b.title)}</span></button>`).join('');
    const keep = books.find((b) => b.id === current) || books[0];
    if (keep) selectBook(keep);
  }
  picker.addEventListener('click', (event) => {
    const tab = event.target.closest('[role="tab"]');
    if (!tab) return;
    const book = pickerBooks.find((b) => b.id === tab.dataset.book);
    if (book) selectBook(book);
  });
  askForm.addEventListener('ask:answered', () => root.querySelector('#ask').classList.add('is-done'));

  // ── 03 The eye ────────────────────────────────────────────────────────
  const eyeForm = root.querySelector('[data-eye-try]');
  const eyeResult = root.querySelector('[data-eye-result]');
  const finderLink = (title, author) => `/library/find?title=${encodeURIComponent(title)}&author=${encodeURIComponent(author)}`;
  eyeForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const title = eyeForm.elements.title.value.trim();
    const author = eyeForm.elements.author.value.trim();
    if (title.length < 2) return;
    const button = eyeForm.querySelector('button');
    button.disabled = true;
    eyeResult.innerHTML = '<p class="ask-wait"><span class="ask-dots" aria-hidden="true"></span> Checking the shelves first…</p>';
    try {
      const lookup = await fetch(`/welcome/lookup?q=${encodeURIComponent(title)}`).then((r) => r.json()).catch(() => ({ matches: [] }));
      if (lookup.matches && lookup.matches.length) {
        eyeResult.innerHTML = `<p class="eye-found">It's already here: ${lookup.matches.map((m) => `<a href="${esc(m.href)}" data-preview>${esc(m.title)}${m.author ? ` · ${esc(m.author)}` : ''} ↗</a>`).join(' ')}</p>
          <p class="welcome-note">Wanted a different edition? <a href="${finderLink(title, author)}">Send the eye anyway ↗</a></p>`;
        return;
      }
      eyeResult.innerHTML = '<p class="ask-wait"><span class="ask-dots" aria-hidden="true"></span> Not on the shelves. The eye is searching the open web for a readable PDF (this can take half a minute)…</p>';
      const response = await fetch('/library/find/quick', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, author }),
      });
      const data = await response.json().catch(() => ({}));
      fetch('/welcome/eye-tried', { method: 'POST' }).catch(() => {});
      root.querySelector('#eye').classList.add('is-done');
      if (!response.ok) {
        eyeResult.innerHTML = `<p class="ask-error">${esc(data.detail || 'The eye could not search just now.')}</p>`;
        return;
      }
      const results = data.results || [];
      if (!results.length) {
        eyeResult.innerHTML = `<p>The eye found no readable copy on a quick look. <a href="${finderLink(title, author)}">Run a full search ↗</a>. A full search tries more sources and checks each edition.</p>`;
        return;
      }
      eyeResult.innerHTML = `<p class="eye-found">The eye found ${results.length} readable ${results.length === 1 ? 'copy' : 'copies'}:</p>
        <ul class="eye-list">${results.slice(0, 3).map((r) => `<li><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title || title)} ↗</a><span>${esc(r.domain || '')}${r.page_count ? ` · ${r.page_count} pages` : ''}${r.edition_fit && r.edition_fit !== 'length unknown' ? ` · ${esc(r.edition_fit)}` : ''}</span></li>`).join('')}</ul>
        <p class="welcome-note">Want it on the shelves for everyone? <a href="${finderLink(title, author)}">Open it in the eye and send it in ↗</a></p>`;
    } finally {
      button.disabled = false;
    }
  });

  // Start: first door open, its books preselected.
  if (doors[0]) {
    showDoors();
    cards.filter((c) => c.dataset.doorBook === doors[0].dataset.door).slice(0, 3).forEach((c) => { c.querySelector('input').checked = true; });
  }
  refresh();
})();
