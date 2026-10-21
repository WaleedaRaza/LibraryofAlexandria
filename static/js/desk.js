(() => {
  const form = document.querySelector('#desk-search');
  if (!form) return;

  const booksInput = document.querySelector('#books');
  const loadEssential = document.querySelector('#load-essential');
  const loadLaunch = document.querySelector('#load-launch');
  const loadLatestRun = document.querySelector('#load-latest-run');
  const pickFirstLooks = document.querySelector('#pick-first-looks');
  const launchBatch = document.querySelector('#launch-batch');
  const submit = document.querySelector('#desk-submit');
  const stop = document.querySelector('#desk-stop');
  const state = document.querySelector('#desk-state');
  const light = document.querySelector('#desk-light');
  const progress = document.querySelector('#desk-progress');
  const progressLabel = document.querySelector('#desk-progress-label');
  const current = document.querySelector('#desk-current');
  const counts = document.querySelector('#desk-counts');
  const results = document.querySelector('#desk-results');
  const selectionBar = document.querySelector('#selection-bar');
  const selectionCount = document.querySelector('#selection-count');
  const shortlist = document.querySelector('#shortlist');
  const reviewSelected = document.querySelector('#review-selected');
  const copySelected = document.querySelector('#copy-selected');
  const exportSelected = document.querySelector('#export-selected');
  const clearSelected = document.querySelector('#clear-selected');
  let jobId = null;
  let timer = null;
  let lastRendered = -1;
  let currentJob = null;
  const selectionKey = 'waleeds-pdf-desk-selection-v2';
  let selected = new Map();

  try {
    selected = new Map(JSON.parse(localStorage.getItem(selectionKey) || '[]'));
  } catch (_) {
    selected = new Map();
  }

  const escapeHtml = (value = '') => String(value).replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[char]);

  const formatBytes = bytes => {
    if (!bytes) return 'size unknown';
    return bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
  };

  function persistSelection() {
    localStorage.setItem(selectionKey, JSON.stringify([...selected]));
    selectionCount.textContent = selected.size;
    selectionBar.hidden = selected.size === 0;
    if (!selected.size) shortlist.hidden = true;
    if (!shortlist.hidden) renderShortlist();
  }

  function renderShortlist() {
    shortlist.innerHTML = `<div class="shortlist-head"><h2>Tabs worth opening</h2><p>Open these individually, inspect the book in your browser, then export your final bookmarks.</p></div><ol>${[...selected].map(([url, meta], index) => `
      <li><span>${String(index + 1).padStart(2, '0')}</span><div><strong>${escapeHtml(meta.title)}</strong><small>${escapeHtml(meta.source || new URL(url).hostname)} · ${meta.pages ? `${meta.pages} pages` : 'page count pending'}</small></div><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Open PDF ↗</a></li>
    `).join('')}</ol>`;
  }

  function candidateMarkup(item, book) {
    const className = item.viewable ? 'verified' : 'rejected';
    const pageCopy = item.page_count ? `${item.page_count} pages` : 'pages unverified';
    const reasons = (item.reasons || []).slice(0, 5).map(reason => `<li>${escapeHtml(reason)}</li>`).join('');
    const elite = item.viewable && item.page_count >= 40 && item.score >= 65 && item.rank <= 3 && !item.summary_warning && ['plausible length', 'length unknown'].includes(item.edition_fit);
    const action = item.viewable
      ? `<a class="candidate-view" href="${escapeHtml(item.final_url)}" target="_blank" rel="noopener noreferrer">View PDF ↗</a>`
      : `<span class="candidate-disabled">Not a direct PDF</span>`;
    const keep = item.viewable ? `
      <label class="candidate-keep">
        <input type="checkbox" data-keep-url="${escapeHtml(item.final_url)}" data-keep-title="${escapeHtml(book.title)}" data-keep-source="${escapeHtml(item.domain)}" data-keep-pages="${item.page_count || ''}" data-keep-original="${escapeHtml(item.url)}" ${selected.has(item.final_url) ? 'checked' : ''}>
        <span aria-hidden="true"></span>keep
      </label>` : '';
    return `
      <article class="candidate ${className}">
        <div class="candidate-rank">${String(item.rank).padStart(2, '0')}</div>
        <div class="candidate-main">
          <div class="candidate-line">
            <h3>${escapeHtml(item.title)}</h3>${elite ? '<span class="candidate-elite">FIRST LOOK</span>' : ''}
            <span class="candidate-score">${item.score}</span>
          </div>
          <p class="candidate-url">${escapeHtml(item.display_url)}</p>
          <p class="candidate-snippet">${escapeHtml(item.snippet || item.error || 'No search excerpt available.')}</p>
          <ul class="candidate-reasons">${reasons}</ul>
          <a class="candidate-original" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">Original search link ↗</a>
          ${item.source_page ? `<a class="candidate-original" href="${escapeHtml(item.source_page)}" target="_blank" rel="noopener noreferrer">Source page ↗</a>` : ''}
        </div>
        <div class="candidate-facts">
          ${keep}
          <span class="fact-state">${escapeHtml(item.state)}</span>
          <span>${escapeHtml(pageCopy)}</span>
          ${item.edition_fit && item.edition_fit !== 'length unknown' ? `<span>${escapeHtml(item.edition_fit)}</span>` : ''}
          <span>${escapeHtml(formatBytes(item.size_bytes))}</span>
          <span>${escapeHtml(item.rights)}</span>
          ${action}
        </div>
      </article>`;
  }

  function bookMarkup(book, index) {
    const verified = book.results.filter(item => item.viewable).length;
    const kept = book.results.filter(item => selected.has(item.final_url)).length;
    const visibleResults = book.results.slice(0, 12);
    return `
      <details class="desk-book" data-book-index="${index}" style="--book-index:${index}">
        <summary class="desk-book-head">
          <div><span>${String(index + 1).padStart(2, '0')}</span><h2>${escapeHtml(book.title)}</h2>${book.author ? `<p>${escapeHtml(book.author)}</p>` : ''}</div>
          <div><span class="book-result-count">${verified} direct PDFs${kept ? ` · ${kept} kept` : ''}${book.elapsed != null ? ` · ${book.elapsed}s` : ''}</span><i aria-hidden="true">⌄</i></div>
        </summary>
        ${book.error ? `<p class="desk-book-error">${escapeHtml(book.error)}</p>` : ''}
        <div class="candidate-list">
          ${visibleResults.length ? visibleResults.map(item => candidateMarkup(item, book)).join('') : '<p class="desk-no-match">No credible candidates survived this search.</p>'}
        </div>
      </details>`;
  }

  function render(job) {
    currentJob = job;
    const openBooks = new Set([...results.querySelectorAll('.desk-book[open]')].map(item => item.dataset.bookIndex));
    const all = job.books.flatMap(book => book.results || []);
    const verified = all.filter(item => item.viewable).length;
    const rejected = all.length - verified;
    const ratio = job.total ? job.completed / job.total : 0;
    progress.style.transform = `scaleX(${ratio})`;
    progressLabel.textContent = `${job.completed} / ${job.total} titles`;
    current.textContent = job.current ? `searching “${job.current.title}”` : '';
    counts.textContent = `${verified} direct PDFs · ${rejected} other links`;
    state.textContent = job.status.toUpperCase();
    light.className = job.status;
    results.innerHTML = job.books.length
      ? job.books.map(bookMarkup).join('')
      : '<div class="desk-empty searching"><div class="desk-empty-mark">···</div><p>Building the candidate set.</p><span>Search, probe, classify, rank.</span></div>';
    const newestIndex = String(job.books.length - 1);
    results.querySelectorAll('.desk-book').forEach(item => {
      if (openBooks.has(item.dataset.bookIndex) || (job.total <= 3 && item.dataset.bookIndex === newestIndex && job.completed > lastRendered)) {
        item.open = true;
      }
    });
    persistSelection();
  }

  async function poll() {
    if (!jobId) return;
    try {
      const response = await fetch(`/desk/jobs/${jobId}`);
      if (!response.ok) throw new Error('Could not read search status');
      const job = await response.json();
      if (job.completed !== lastRendered || ['complete', 'failed', 'cancelled'].includes(job.status)) {
        render(job);
        lastRendered = job.completed;
      } else {
        state.textContent = job.status.toUpperCase();
        current.textContent = job.current ? `searching “${job.current.title}”` : '';
      }
      if (['complete', 'failed', 'cancelled'].includes(job.status)) {
        clearInterval(timer);
        timer = null;
        submit.disabled = false;
        submit.querySelector('span').textContent = 'Run search';
        stop.hidden = true;
      }
    } catch (error) {
      clearInterval(timer);
      timer = null;
      state.textContent = 'CONNECTION LOST';
      light.className = 'failed';
      submit.disabled = false;
      stop.hidden = true;
    }
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!booksInput.value.trim()) return;
    submit.disabled = true;
    submit.querySelector('span').textContent = 'Searching';
    stop.hidden = false;
    state.textContent = 'QUEUED';
    light.className = 'queued';
    results.innerHTML = '<div class="desk-empty searching"><div class="desk-empty-mark">···</div><p>Building the candidate set.</p><span>Search, probe, classify, rank.</span></div>';
    const body = new FormData(form);
    const response = await fetch('/desk/search', { method: 'POST', body });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      state.textContent = payload.detail || 'SEARCH FAILED';
      light.className = 'failed';
      submit.disabled = false;
      stop.hidden = true;
      return;
    }
    const payload = await response.json();
    jobId = payload.job_id;
    lastRendered = -1;
    clearInterval(timer);
    timer = setInterval(poll, 1200);
    poll();
  });

  stop.addEventListener('click', async () => {
    if (!jobId) return;
    await fetch(`/desk/jobs/${jobId}/stop`, { method: 'POST' });
    poll();
  });

  loadEssential.addEventListener('click', async () => {
    loadEssential.disabled = true;
    loadEssential.textContent = 'Loading…';
    try {
      const response = await fetch('/desk/lists/essential-50');
      if (!response.ok) throw new Error('Reading list unavailable');
      const readingList = await response.json();
      const lines = [];
      let category = null;
      readingList.books.forEach(book => {
        if (category && category !== book.category) lines.push('');
        category = book.category;
        lines.push(`${book.title} — ${book.author}`);
      });
      booksInput.value = lines.join('\n');
      loadEssential.textContent = `${readingList.books.length} titles loaded`;
      booksInput.focus();
    } catch (_) {
      loadEssential.textContent = 'Could not load list';
    } finally {
      loadEssential.disabled = false;
    }
  });

  loadLaunch.addEventListener('click', async () => {
    loadLaunch.disabled = true;
    loadLaunch.textContent = 'Loading…';
    try {
      const response = await fetch('/desk/lists/launch-72');
      if (!response.ok) throw new Error('Launch list unavailable');
      const readingList = await response.json();
      const size = readingList.batch_size || 12;
      const batch = launchBatch.value;
      const books = batch === 'all' ? readingList.books : readingList.books.slice((Number(batch) - 1) * size, Number(batch) * size);
      booksInput.value = books.map(book => `${book.title} — ${book.author}`).join('\n');
      loadLaunch.textContent = `${books.length} titles loaded`;
      booksInput.focus();
    } catch (_) {
      loadLaunch.textContent = 'Could not load list';
    } finally {
      loadLaunch.disabled = false;
      setTimeout(() => { loadLaunch.textContent = 'Load batch'; }, 2000);
    }
  });

  loadLatestRun.addEventListener('click', async () => {
    loadLatestRun.disabled = true;
    try {
      const response = await fetch('/desk/lists/launch-72/results');
      if (!response.ok) throw new Error('No sourcing run yet');
      const run = await response.json();
      clearInterval(timer);
      timer = null;
      jobId = null;
      render(run);
      lastRendered = run.completed;
      results.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (_) {
      state.textContent = 'NO SAVED RUN YET';
    } finally {
      loadLatestRun.disabled = false;
    }
  });

  pickFirstLooks.addEventListener('click', () => {
    if (!currentJob) return;
    let added = 0;
    currentJob.books.forEach(book => {
      const pick = (book.results || []).find(item => item.viewable && item.page_count >= 40 && item.score >= 65 && !item.summary_warning && ['plausible length', 'length unknown'].includes(item.edition_fit));
      if (pick && !selected.has(pick.final_url)) {
        selected.set(pick.final_url, { title: book.title, source: pick.domain, pages: pick.page_count, original: pick.url });
        added += 1;
      }
    });
    render(currentJob);
    shortlist.hidden = false;
    renderShortlist();
    reviewSelected.textContent = 'Hide shortlist';
    pickFirstLooks.textContent = `${added} added`;
    setTimeout(() => { pickFirstLooks.textContent = 'Pick first looks'; }, 1800);
  });

  results.addEventListener('change', event => {
    const checkbox = event.target.closest('[data-keep-url]');
    if (!checkbox) return;
    const url = checkbox.dataset.keepUrl;
    if (checkbox.checked) {
      selected.set(url, { title: checkbox.dataset.keepTitle, source: checkbox.dataset.keepSource, pages: Number(checkbox.dataset.keepPages) || null, original: checkbox.dataset.keepOriginal });
    } else {
      selected.delete(url);
    }
    persistSelection();
  });

  reviewSelected.addEventListener('click', () => {
    shortlist.hidden = !shortlist.hidden;
    if (!shortlist.hidden) {
      renderShortlist();
      shortlist.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });

  copySelected.addEventListener('click', async () => {
    const links = [...selected.keys()].join('\n');
    await navigator.clipboard.writeText(links);
    copySelected.textContent = 'Copied';
    setTimeout(() => { copySelected.textContent = 'Copy links'; }, 1400);
  });

  exportSelected.addEventListener('click', () => {
    const entries = [...selected].map(([url, meta]) =>
      `<DT><A HREF="${escapeHtml(url)}">${escapeHtml(meta.title)} — ${escapeHtml(meta.source)}</A>`
    ).join('\n');
    const documentText = `<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n<TITLE>Waleed's PDF Finds</TITLE>\n<H1>Waleed's PDF Finds</H1>\n<DL><p>\n${entries}\n</DL><p>`;
    const href = URL.createObjectURL(new Blob([documentText], { type: 'text/html' }));
    const anchor = document.createElement('a');
    anchor.href = href;
    anchor.download = 'waleeds-pdf-finds-bookmarks.html';
    anchor.click();
    URL.revokeObjectURL(href);
  });

  clearSelected.addEventListener('click', () => {
    selected.clear();
    document.querySelectorAll('[data-keep-url]').forEach(input => { input.checked = false; });
    persistSelection();
  });

  booksInput.addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') form.requestSubmit();
  });

  persistSelection();
})();
