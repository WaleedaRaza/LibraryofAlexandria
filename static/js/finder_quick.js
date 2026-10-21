(() => {
  const form = document.getElementById('quick-finder');
  if (!form) return;
  const status = document.getElementById('quick-finder-status');
  const loading = document.getElementById('quick-finder-loading');
  const results = document.getElementById('quick-finder-results');
  const button = form.querySelector('button[type="submit"]');
  const contribute = document.getElementById('contribute-form');

  const glyph = (name) => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', `glyph glyph-${name}`);
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', `#g-${name}`);
    svg.append(use);
    return svg;
  };

  // A result with a book-like page count and a strong score gets the eye (looks real);
  // anything thinner gets the feather (worth a closer look).
  const isStrong = (item) => ((item.page_count || 0) >= 60 || (item.size_bytes || 0) >= 1048576) && (item.score || 0) >= 55;

  // "Send to Waleed" is the only way the contribute form appears: it opens prefilled with
  // the search and the chosen link, so contributing stays a deliberate second step.
  const sendToWaleed = (item) => {
    if (!contribute) return;
    const title = form.elements.title.value.trim();
    const author = form.elements.author.value.trim();
    if (title && !contribute.elements.title.value) contribute.elements.title.value = title;
    if (author && !contribute.elements.author.value) contribute.elements.author.value = author;
    const links = contribute.elements.links;
    const existing = links.value.split('\n').map((line) => line.trim()).filter(Boolean);
    if (!existing.includes(item.url)) links.value = [...existing, item.url].join('\n');
    contribute.hidden = false;
    contribute.scrollIntoView({ behavior: 'smooth', block: 'start' });
    contribute.elements.note.focus({ preventScroll: true });
  };
  contribute?.querySelector('[data-contribute-cancel]')?.addEventListener('click', () => {
    contribute.hidden = true;
    contribute.elements.links.value = '';
  });

  const resultRow = (item) => {
    const article = document.createElement('article');
    article.className = `quick-result${isStrong(item) ? ' is-strong' : ''}`;
    article.append(glyph(isStrong(item) ? 'eye' : 'feather'));
    const copy = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = item.title || 'PDF result';
    const facts = document.createElement('span');
    const pages = item.page_count ? `${item.page_count} pages` : item.size_bytes ? `${(item.size_bytes / 1048576).toFixed(1)} MB PDF` : 'page count unverified';
    const fit = item.edition_fit && item.edition_fit !== 'length unknown' ? ` · ${item.edition_fit}` : '';
    facts.textContent = `${item.domain || 'Public source'} · ${pages}${fit}`;
    const reasons = document.createElement('small');
    reasons.textContent = (item.reasons || []).slice(0, 3).join(' · ');
    copy.append(title, facts, reasons);
    const actions = document.createElement('div');
    actions.className = 'quick-result-actions';
    const open = document.createElement('a');
    open.className = 'btn';
    open.href = item.url;
    open.target = '_blank';
    open.rel = 'noopener noreferrer';
    open.textContent = 'Open PDF ↗';
    const send = document.createElement('button');
    send.className = 'btn btn-quiet';
    send.type = 'button';
    send.textContent = 'Send to Waleed';
    send.addEventListener('click', () => {
      sendToWaleed(item);
      send.textContent = 'Added below ✓';
    });
    actions.append(open, send);
    article.append(copy, actions);
    return article;
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    button.disabled = true;
    loading.hidden = false;
    status.textContent = '';
    results.replaceChildren();
    try {
      const response = await fetch('/library/find/quick', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: form.elements.title.value, author: form.elements.author.value }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Search failed. Try again in a moment.');
      if (!data.results.length) {
        status.textContent = 'No PDFs found. Try adding the author or the exact title.';
      } else {
        status.textContent = `${data.results.length} PDF${data.results.length === 1 ? '' : 's'} found.`;
        results.replaceChildren(...data.results.map(resultRow));
      }
    } catch (error) {
      status.textContent = error.message;
    } finally {
      loading.hidden = true;
      button.disabled = false;
    }
  });
})();
