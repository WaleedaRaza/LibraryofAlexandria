(() => {
  const counter = document.querySelector('[data-count-to]');
  if (counter) {
    const target = Number(counter.dataset.countTo || counter.textContent || 0);
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const count = () => {
      if (reduced || !target) {
        counter.textContent = String(target);
        return;
      }
      const started = performance.now();
      const duration = 1100;
      const tick = (now) => {
        const progress = Math.min(1, (now - started) / duration);
        const eased = 1 - Math.pow(1 - progress, 4);
        counter.textContent = Math.round(target * eased).toLocaleString();
        if (progress < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    };
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        observer.disconnect();
        count();
      }, { threshold: 0.6 });
      counter.textContent = reduced ? String(target) : '0';
      observer.observe(counter);
    } else {
      count();
    }
  }

  const dataElement = document.getElementById('discovery-data');
  const hero = document.getElementById('random-book');
  if (!dataElement || !hero) return;

  const books = JSON.parse(dataElement.textContent || '[]');
  if (!books.length) return;
  const preview = new URLSearchParams(location.search).get('preview_links') === '1';
  const image = document.getElementById('random-book-image');
  const coverLink = document.getElementById('random-book-link');
  const openLink = document.getElementById('random-book-open');
  const title = document.getElementById('random-book-title');
  const author = document.getElementById('random-book-author');
  const format = document.getElementById('random-book-format');
  const next = document.getElementById('discovery-next');
  let current = Math.max(0, books.findIndex((book) => book.id === hero.dataset.bookId));
  let timer;

  const bookUrl = (book) => `/library/book/${encodeURIComponent(book.id)}${preview ? '?preview_links=1' : ''}`;
  const render = (book) => {
    hero.classList.add('is-changing');
    window.setTimeout(() => {
      const url = bookUrl(book);
      image.src = `/library/book/${encodeURIComponent(book.id)}/cover`;
      image.alt = `Cover of ${book.title}`;
      coverLink.href = url;
      openLink.href = url;
      title.textContent = book.title;
      author.textContent = book.author || 'Unknown author';
      format.textContent = `${book.availability === 'external_link' ? 'Web link' : 'PDF'} · ${book.domain || 'Book'}`;
      hero.style.removeProperty('--halo');
      hero.dataset.bookId = book.id;
      hero.classList.remove('is-changing');
    }, 160);
  };

  const chooseAnother = () => {
    if (books.length < 2) return;
    let nextIndex = current;
    while (nextIndex === current) nextIndex = Math.floor(Math.random() * books.length);
    current = nextIndex;
    render(books[current]);
  };

  const restartTimer = () => {
    window.clearInterval(timer);
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      timer = window.setInterval(chooseAnother, 12000);
    }
  };

  next.addEventListener('click', () => {
    chooseAnother();
    restartTimer();
  });
  restartTimer();
})();
