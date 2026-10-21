/* Shared shell behaviour: the opening splash, the book preview dialog,
   the sticky A–Z rail, and cover-colour halos. No frameworks, no build step. */
(() => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ── Splash: shown once per browser session, never blocks content for long. ── */
  const splash = document.querySelector('.splash');
  if (splash) {
    const total = Number(document.body.dataset.totalBooks || 0);
    const countNode = splash.querySelector('[data-splash-count]');
    const shownAt = Number(splash.dataset.shownAt || performance.now());
    if (total && countNode) {
      countNode.parentElement.hidden = false;
      const start = performance.now();
      const tick = (now) => {
        const progress = Math.min(1, (now - start) / 900);
        countNode.textContent = Math.round(total * (1 - Math.pow(1 - progress, 3))).toLocaleString();
        if (progress < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }
    const leave = () => {
      if (splash.classList.contains('is-leaving')) return;
      splash.classList.add('is-leaving');
      document.documentElement.classList.remove('is-splashing');
      try { sessionStorage.setItem('libxndr-opened', '1'); } catch (_) { /* fine */ }
      window.setTimeout(() => splash.remove(), 500);
    };
    // Full splash holds for two seconds on the first open; the brief one just covers the page change.
    const brief = splash.dataset.mode === 'brief';
    const hold = brief ? 0 : 1200;
    const minimum = Math.max(0, hold - (performance.now() - shownAt));
    const onLoad = () => window.setTimeout(leave, minimum);
    if (document.readyState === 'complete') onLoad(); else window.addEventListener('load', onLoad, { once: true });
    window.setTimeout(leave, brief ? 400 : 3000);
    if (!brief) splash.addEventListener('click', leave);
  }


  /* ── Cover halos: each cover lends its dominant colour to the glow around it. ── */
  const haloCache = new Map();
  const sampleHalo = (img) => {
    if (!img.complete || !img.naturalWidth) return;
    const host = img.closest('[data-halo-host]') || img.parentElement;
    if (!host) return;
    const cached = haloCache.get(img.currentSrc);
    if (cached) { host.style.setProperty('--halo', cached); return; }
    try {
      const canvas = document.createElement('canvas');
      canvas.width = 12; canvas.height = 18;
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(img, 0, 0, 12, 18);
      const data = ctx.getImageData(0, 0, 12, 18).data;
      let r = 0, g = 0, b = 0, n = 0;
      for (let i = 0; i < data.length; i += 4) {
        const max = Math.max(data[i], data[i + 1], data[i + 2]);
        const min = Math.min(data[i], data[i + 1], data[i + 2]);
        const weight = 1 + (max - min) / 64; // favour saturated pixels so covers glow in their own colour
        r += data[i] * weight; g += data[i + 1] * weight; b += data[i + 2] * weight; n += weight;
      }
      if (!n) return;
      r = Math.round(r / n); g = Math.round(g / n); b = Math.round(b / n);
      const lift = 1.25; // lift dark covers so the halo still reads on black
      const halo = `rgba(${Math.min(255, r * lift)}, ${Math.min(255, g * lift)}, ${Math.min(255, b * lift)}, .45)`;
      haloCache.set(img.currentSrc, halo);
      host.style.setProperty('--halo', halo);
    } catch (_) {
      /* cross-origin covers (signed storage URLs) taint the canvas; the default halo stays */
    }
  };
  const watchCovers = (root) => {
    root.querySelectorAll('img[data-halo]').forEach((img) => {
      if (img.complete) sampleHalo(img); else img.addEventListener('load', () => sampleHalo(img), { once: true });
    });
  };
  watchCovers(document);
  // Covers swapped in later (the hero's "another cover", dialog content) are sampled as they load.
  document.addEventListener('load', (event) => { if (event.target.matches && event.target.matches('img[data-halo]')) sampleHalo(event.target); }, true);

  /* ── Book preview dialog: a tile click opens the record over the shelf. ── */
  const dialog = document.getElementById('book-dialog');
  const supportsDialog = dialog && typeof dialog.showModal === 'function';
  let openedFrom = null;
  const closeDialog = () => {
    if (!dialog.open) return;
    dialog.close();
  };
  const restoreUrl = () => {
    if (history.state && history.state.libxndrPreview) history.back();
  };
  if (supportsDialog) {
    dialog.addEventListener('close', () => {
      document.body.classList.remove('has-dialog');
      if (openedFrom && document.contains(openedFrom)) openedFrom.focus({ preventScroll: true });
      openedFrom = null;
    });
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) { closeDialog(); restoreUrl(); }
      const closer = event.target.closest('[data-preview-close]');
      if (closer) { event.preventDefault(); closeDialog(); restoreUrl(); }
    });
    dialog.addEventListener('cancel', (event) => { event.preventDefault(); closeDialog(); restoreUrl(); });
    window.addEventListener('popstate', () => { if (dialog.open) closeDialog(); });

    const openPreview = async (href, trigger) => {
      openedFrom = trigger;
      dialog.innerHTML = '<div class="preview-loading"><div class="pyramid pyramid-inline" role="status" aria-label="Opening the book"><div class="pyramid-stage"><div class="pyramid-solid">' +
        ['lit', 'mid', 'shade', 'dark'].map((face) => `<div class="pyramid-face face-${face}"></div>`).join('') +
        '</div><div class="pyramid-ground"></div></div></div></div>';
      document.body.classList.add('has-dialog');
      dialog.showModal();
      try {
        const response = await fetch(href, { headers: { 'X-Partial': '1' } });
        if (!response.ok) throw new Error('unavailable');
        const html = await response.text();
        if (!dialog.open) return;
        dialog.innerHTML = html;
        watchCovers(dialog);
        const heading = dialog.querySelector('.preview-title');
        if (heading) { heading.setAttribute('tabindex', '-1'); heading.focus({ preventScroll: true }); }
      } catch (_) {
        window.location.href = href;
      }
    };

    document.addEventListener('click', (event) => {
      const link = event.target.closest('a[data-preview]');
      if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
      event.preventDefault();
      const href = link.getAttribute('href');
      history.pushState({ libxndrPreview: true }, '', href);
      openPreview(href, link);
    });
  }

  /* ── Topbar height: the sticky rail and anchor offsets follow the real header, which wraps on phones. ── */
  const topbar = document.querySelector('.topbar');
  if (topbar && 'ResizeObserver' in window) {
    const setHeight = () => document.documentElement.style.setProperty('--topbar-h', `${Math.round(topbar.getBoundingClientRect().height)}px`);
    new ResizeObserver(setHeight).observe(topbar);
    setHeight();
  }

  /* ── Sticky A–Z rail: light the letter you are reading. ── */
  const rail = document.querySelector('.alphabet-jump');
  if (rail && 'IntersectionObserver' in window) {
    const links = new Map([...rail.querySelectorAll('a')].map((a) => [a.getAttribute('href').slice(1), a]));
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        links.forEach((a) => a.classList.remove('is-current'));
        const current = links.get(entry.target.id);
        if (current) {
          current.classList.add('is-current');
          // Keep the lit letter visible in the rail by scrolling the rail itself, never the page.
          if (rail.scrollWidth > rail.clientWidth) {
            const target = current.offsetLeft - (rail.clientWidth - current.offsetWidth) / 2;
            rail.scrollTo({ left: Math.max(0, target), behavior: reduced ? 'auto' : 'smooth' });
          }
        }
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    document.querySelectorAll('.alphabet-shelf').forEach((shelf) => observer.observe(shelf));
  }
})();
