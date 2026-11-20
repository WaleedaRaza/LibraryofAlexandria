// "Ask this book": a question in, a passage and its page out.
// Works on any <form data-ask-book="<book id>"> with a [data-ask-result] inside, including
// forms that arrive later inside the book preview dialog (the listener is delegated).
(() => {
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const render = (target, data) => {
    const answer = data.answer ? `<p class="ask-answer">${escapeHtml(data.answer)}</p>` : '';
    const open = data.signed_in ? `Open at page ${data.page} ↗` : `Join free to open page ${data.page} ↗`;
    const alternates = (data.alternates || []).length
      ? `<details class="ask-more"><summary>Also in this book</summary><ul>${data.alternates.map((alt) => `<li><a href="${escapeHtml(alt.open_url)}">p. ${alt.page}</a> <span>${escapeHtml(alt.quote)}</span></li>`).join('')}</ul></details>`
      : '';
    target.innerHTML = `
      <figure class="ask-passage">
        <blockquote>${escapeHtml(data.quote)}</blockquote>
        <figcaption>${escapeHtml(data.book.title)}${data.book.author ? ` · ${escapeHtml(data.book.author)}` : ''} · page ${data.page}</figcaption>
      </figure>
      ${answer}
      <div class="ask-open"><a class="btn btn-primary" href="${escapeHtml(data.open_url)}">${open}</a></div>
      ${alternates}`;
  };

  const ask = async (form, question) => {
    const bookId = form.dataset.askBook;
    const target = form.querySelector('[data-ask-result]');
    if (!bookId || !target) return;
    target.innerHTML = '<p class="ask-wait"><span class="ask-dots" aria-hidden="true"></span> Reading the book for that… the first question about a book takes a few seconds.</p>';
    form.classList.add('is-asking');
    try {
      const response = await fetch(`/library/book/${encodeURIComponent(bookId)}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        target.innerHTML = `<p class="ask-error">${escapeHtml(data.detail || 'That did not work. Try again.')}</p>`;
        return;
      }
      render(target, data);
      form.dispatchEvent(new CustomEvent('ask:answered', { bubbles: true, detail: data }));
    } catch (_) {
      target.innerHTML = '<p class="ask-error">The connection dropped. Try again.</p>';
    } finally {
      form.classList.remove('is-asking');
    }
  };

  document.addEventListener('submit', (event) => {
    const form = event.target.closest('form[data-ask-book]');
    if (!form) return;
    event.preventDefault();
    const input = form.querySelector('input[name="question"]');
    const question = (input?.value || '').trim();
    if (question.length < 4 || form.classList.contains('is-asking')) return;
    ask(form, question);
  });

  document.addEventListener('click', (event) => {
    const chip = event.target.closest('[data-ask-question]');
    if (!chip) return;
    const form = chip.closest('form[data-ask-book]');
    if (!form || form.classList.contains('is-asking')) return;
    const input = form.querySelector('input[name="question"]');
    if (input) input.value = chip.dataset.askQuestion;
    ask(form, chip.dataset.askQuestion);
  });

  window.LibxndrAsk = { escapeHtml };
})();
