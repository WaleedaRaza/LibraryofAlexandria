/* Flow mode: any page of any PDF, one word (or a few) at a time, optionally read aloud.

   Text comes from the PDF's own text layer through PDF.js, page by page, ahead of the
   reader. Words are shown RSVP style with the recognition point fixed under the reticle,
   so the eyes stay still and the text moves. In Listen mode a narrator speaks each
   sentence and the display follows the voice word by word.

   Narrators are pluggable (see NARRATORS below). Today only the browser's own speech
   engine is wired in; a server voice that returns audio plus word timings can register
   itself without touching the rest of this file. */
(() => {
  const shell = document.querySelector('.flow-shell');
  if (!shell) return;
  const $ = (id) => document.getElementById(id);
  const bookId = shell.dataset.bookId;
  const pdfUrl = shell.dataset.pdfUrl || `/read/${encodeURIComponent(bookId)}/pdf`;
  const statusEl = $('flow-status');
  const wordEl = $('flow-word');
  const [leftEl, pivotEl, rightEl] = wordEl.children;
  const contextEl = $('flow-context');
  const playBtn = $('flow-play');
  const wpmInput = $('flow-wpm');
  const pageInput = $('flow-page-input');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const setStatus = (text) => { statusEl.textContent = text || ''; };
  if (!window.pdfjsLib) { setStatus('The text engine did not load on this device.'); return; }
  pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

  /* ---------- settings ---------- */
  const STORE = 'libxndr-flow';
  const store = {
    read() { try { return JSON.parse(localStorage.getItem(STORE) || '{}'); } catch (_) { return {}; } },
    write(value) { try { localStorage.setItem(STORE, JSON.stringify(value)); } catch (_) {} },
  };
  const settings = Object.assign(
    { wpm: 350, mode: 'flash', bg: reducedMotion ? 'none' : 'runner', chunk: 1, voice: '', context: true },
    store.read(),
  );
  const saveSettings = () => store.write(settings);

  /* ---------- text: PDF page -> words ---------- */
  const state = {
    pdf: null,
    words: [],        // { t, page, s }   s = sentence index
    sentences: [],    // { start, end, page }
    firstPage: 1,
    nextPage: 1,      // next page to extract
    loading: null,
    idx: 0,
    playing: false,
    timer: null,
    generation: 0,    // bumps on every stop so stale callbacks are ignored
    shownPage: 0,
    sessionWords: 0,
    playStarted: 0,
    playedMs: 0,
    lastCounted: -1,
  };

  const ABBREV = /^(mr|mrs|ms|dr|st|vs|etc|e\.g|i\.e|cf|viz|vol|ch|no|pp|p|fig|ed|trans|ibid|op|cit|jr|sr|prof|gen|col|capt|lt|rev|hon|mt|ft)\.$/i;
  const endsSentence = (token) => {
    const bare = token.replace(/["'”’)\]]+$/, '');
    if (!/[.!?…]$/.test(bare)) return false;
    if (ABBREV.test(bare)) return false;
    if (/^[A-Z]\.$/.test(bare)) return false; // initials
    return true;
  };

  async function extractPage(number) {
    const page = await state.pdf.getPage(number);
    const height = page.getViewport({ scale: 1 }).height;
    const content = await page.getTextContent();
    const lines = [];
    let line = { text: '', y: null };
    for (const item of content.items) {
      if (typeof item.str !== 'string') continue;
      if (line.y === null && item.str.trim()) line.y = item.transform[5];
      line.text += item.str;
      if (item.hasEOL) { lines.push(line); line = { text: '', y: null }; }
    }
    if (line.text.trim()) lines.push(line);
    const kept = lines.filter((l, i) => {
      const text = l.text.trim();
      if (!text) return false;
      if (/^[\divxlcIVXLC.\-–— ]+$/.test(text) && text.length < 12) return false; // page numbers
      const inMargin = l.y !== null && (l.y > height * 0.93 || l.y < height * 0.06);
      const edge = i < 2 || i >= lines.length - 2;
      return !(inMargin && edge && text.length < 90); // running heads and feet
    });
    let text = '';
    for (const l of kept) {
      const piece = l.text.replace(/\s+/g, ' ').trim();
      if (/[A-Za-z]-$/.test(text) && /^[a-z]/.test(piece)) text = text.slice(0, -1) + piece; // de-hyphenate
      else text += (text ? ' ' : '') + piece;
    }
    return text.split(/\s+/).filter(Boolean);
  }

  function appendWords(tokens, page) {
    let current = state.sentences[state.sentences.length - 1];
    if (!current || current.closed) {
      current = { start: state.words.length, end: state.words.length, page };
      state.sentences.push(current);
    }
    for (const t of tokens) {
      if (current.closed) {
        current = { start: state.words.length, end: state.words.length, page };
        state.sentences.push(current);
      }
      state.words.push({ t, page, s: state.sentences.length - 1 });
      current.end = state.words.length;
      if (endsSentence(t) || current.end - current.start >= 60) current.closed = true;
    }
  }

  // Pull pages until there are `want` words ahead of the reader (or the book ends).
  function ensureAhead(want = 400) {
    if (state.loading) return state.loading;
    if (state.words.length - state.idx >= want || state.nextPage > state.pdf.numPages) return Promise.resolve();
    state.loading = (async () => {
      let tries = 0;
      while (state.words.length - state.idx < want && state.nextPage <= state.pdf.numPages && tries < 12) {
        const n = state.nextPage++;
        tries += 1;
        try { appendWords(await extractPage(n), n); } catch (_) { /* skip an unreadable page */ }
      }
    })().finally(() => { state.loading = null; });
    return state.loading;
  }

  async function openAt(page) {
    stop();
    const target = Math.max(1, Math.min(state.pdf.numPages, Number(page) || 1));
    Object.assign(state, { words: [], sentences: [], idx: 0, firstPage: target, nextPage: target, shownPage: 0, lastCounted: -1 });
    setStatus(`Reading page ${target}…`);
    await ensureAhead(250);
    if (!state.words.length) {
      setStatus('No text found from here. This edition may be a scan without a text layer.');
      show(-1);
      return;
    }
    setStatus('');
    show(0);
  }

  /* ---------- display ---------- */
  const pivotIndex = (word) => {
    const lead = (word.match(/^[^\p{L}\p{N}]*/u) || [''])[0].length;
    const core = word.slice(lead).replace(/[^\p{L}\p{N}]+$/u, '').length;
    const orp = core <= 1 ? 0 : core <= 5 ? 1 : core <= 9 ? 2 : core <= 13 ? 3 : 4;
    return Math.min(word.length - 1, lead + orp);
  };

  function render(text, single) {
    wordEl.classList.toggle('is-chunk', !single);
    shell.classList.toggle('chunked', !single);
    if (!single) { leftEl.textContent = ''; pivotEl.textContent = text; rightEl.textContent = ''; return; }
    const p = pivotIndex(text);
    leftEl.textContent = text.slice(0, p);
    pivotEl.textContent = text.charAt(p);
    rightEl.textContent = text.slice(p + 1);
  }

  function renderContext(i, count) {
    const word = state.words[i];
    if (!word || !settings.context) { contextEl.textContent = ''; return; }
    const sentence = state.sentences[word.s];
    contextEl.replaceChildren();
    for (let k = sentence.start; k < sentence.end; k += 1) {
      const text = state.words[k].t + ' ';
      if (k >= i && k < i + count) {
        const mark = document.createElement('mark');
        mark.textContent = state.words[k].t;
        contextEl.append(mark, ' ');
      } else contextEl.append(text);
    }
  }

  function show(i, count = 1) {
    if (i < 0 || !state.words[i]) { render('', true); contextEl.textContent = ''; return; }
    state.idx = i;
    const run = state.words.slice(i, i + count).map((w) => w.t).join(' ');
    render(run, count === 1);
    renderContext(i, count);
    for (let k = Math.max(state.lastCounted + 1, i); k < i + count; k += 1) state.sessionWords += 1;
    state.lastCounted = Math.max(state.lastCounted, i + count - 1);
    const page = state.words[i].page;
    if (page !== state.shownPage) onPage(page);
    const span = Math.max(1, state.pdf.numPages);
    $('flow-progress-bar').style.width = `${Math.min(100, (page / span) * 100)}%`;
    if (state.words.length - i < 200) ensureAhead();
  }

  /* ---------- progress + page ---------- */
  let progressTimer;
  function onPage(page) {
    state.shownPage = page;
    pageInput.value = page;
    $('flow-back').href = `/read/${encodeURIComponent(bookId)}?page=${page}`;
    clearTimeout(progressTimer);
    progressTimer = setTimeout(() => {
      fetch(`/read/${encodeURIComponent(bookId)}/progress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page_number: page, page_count: state.pdf.numPages }),
      }).catch(() => {});
    }, 800);
  }

  /* ---------- flash playback ---------- */
  function delayFor(i, count) {
    const base = 60000 / settings.wpm;
    let ms = 0;
    for (let k = i; k < i + count && k < state.words.length; k += 1) {
      const t = state.words[k].t;
      let w = 1;
      const core = t.replace(/[^\p{L}\p{N}]/gu, '').length;
      if (core > 7) w *= Math.min(1.6, 1 + (core - 7) * 0.06);
      if (endsSentence(t)) w *= 2.1;
      else if (/[,;:—–)]["'”’]?$/.test(t)) w *= 1.45;
      ms += base * w;
    }
    return ms;
  }

  function chunkAt(i) {
    const size = Number(settings.chunk) || 1;
    const sentence = state.sentences[state.words[i].s];
    let n = 1;
    while (n < size && i + n < sentence.end && !endsSentence(state.words[i + n - 1].t)) n += 1;
    return n;
  }

  function flashStep(gen) {
    if (gen !== state.generation || !state.playing) return;
    if (state.idx >= state.words.length) {
      if (state.loading) { state.timer = setTimeout(() => flashStep(gen), 120); return; }
      finish();
      return;
    }
    const count = chunkAt(state.idx);
    show(state.idx, count);
    const wait = delayFor(state.idx, count);
    state.timer = setTimeout(() => { state.idx += count; flashStep(gen); }, wait);
  }

  /* ---------- narrators ---------- */
  // A narrator speaks a run of words and reports progress:
  //   speak(words: string[], { rate, voice }, onWord(index), onDone()) -> stop()
  // Register more with window.LibxndrFlow.registerNarrator(name, narrator).
  const BrowserNarrator = {
    available: () => 'speechSynthesis' in window,
    voices: () => (window.speechSynthesis ? speechSynthesis.getVoices() : []),
    speak(words, { rate, voice }, onWord, onDone) {
      const text = words.join(' ');
      const offsets = [];
      let pos = 0;
      for (const w of words) { offsets.push(pos); pos += w.length + 1; }
      const utter = new SpeechSynthesisUtterance(text);
      utter.rate = rate;
      const chosen = this.voices().find((v) => v.voiceURI === voice);
      if (chosen) { utter.voice = chosen; utter.lang = chosen.lang; }
      let done = false;
      let started = false;
      let sawBoundary = false;
      let fallback = null;
      const finishOnce = (ok = true) => { if (done) return; done = true; clearInterval(fallback); clearTimeout(watchdog); onDone(ok); };
      // No voice installed, or the engine is stuck: report failure instead of racing ahead.
      const watchdog = setTimeout(() => { if (!started) { speechSynthesis.cancel(); finishOnce(false); } }, 4000);
      utter.onboundary = (event) => {
        if (event.name && event.name !== 'word') return;
        sawBoundary = true;
        clearInterval(fallback);
        let lo = 0; let hi = offsets.length - 1;
        while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (offsets[mid] <= event.charIndex) lo = mid; else hi = mid - 1; }
        onWord(lo);
      };
      utter.onstart = () => {
        started = true;
        onWord(0);
        // Some voices (many network voices) never send word boundaries: estimate instead.
        const perWord = 60000 / (175 * rate);
        let k = 0;
        setTimeout(() => {
          if (sawBoundary || done) return;
          fallback = setInterval(() => { k += 1; if (k < words.length) onWord(k); else clearInterval(fallback); }, perWord);
        }, Math.min(700, perWord * 1.5));
      };
      utter.onend = () => finishOnce(true);
      utter.onerror = (event) => finishOnce(started && ['interrupted', 'canceled'].includes(event.error));
      speechSynthesis.speak(utter);
      return () => { done = true; clearInterval(fallback); clearTimeout(watchdog); speechSynthesis.cancel(); };
    },
  };
  const NARRATORS = { browser: BrowserNarrator };
  let narrator = BrowserNarrator;
  let stopSpeech = null;

  function listenStep(gen) {
    if (gen !== state.generation || !state.playing) return;
    if (state.idx >= state.words.length) {
      if (state.loading) { state.timer = setTimeout(() => listenStep(gen), 150); return; }
      finish();
      return;
    }
    const start = state.idx;
    const sentence = state.sentences[state.words[start].s];
    const end = Math.min(sentence.end, start + 40); // short utterances: Chrome drops long ones
    const run = state.words.slice(start, end).map((w) => w.t);
    const rate = Math.max(0.5, Math.min(3, settings.wpm / 175));
    stopSpeech = narrator.speak(run, { rate, voice: settings.voice }, (k) => {
      if (gen === state.generation) show(start + k);
    }, (ok) => {
      if (gen !== state.generation) return;
      if (!ok) {
        toast('Read-aloud is not available on this device. Switched to Flash.');
        setMode('flash');
        play();
        return;
      }
      state.idx = end;
      listenStep(gen);
    });
  }

  /* ---------- transport ---------- */
  function play() {
    if (!state.words.length || state.playing) return;
    if (state.idx >= state.words.length) state.idx = 0;
    if (settings.mode === 'listen' && !narrator.available()) {
      toast('This browser cannot read aloud. Switched to Flash.');
      setMode('flash');
    }
    state.playing = true;
    state.playStarted = performance.now();
    state.generation += 1;
    playBtn.textContent = '❚❚';
    playBtn.setAttribute('aria-label', 'Pause');
    setStatus('');
    if (settings.mode === 'listen') listenStep(state.generation); else flashStep(state.generation);
  }

  function stop() {
    if (state.playing) state.playedMs += performance.now() - state.playStarted;
    state.playing = false;
    state.generation += 1;
    clearTimeout(state.timer);
    if (stopSpeech) { stopSpeech(); stopSpeech = null; }
    playBtn.textContent = '▶';
    playBtn.setAttribute('aria-label', 'Play');
    updateStats();
  }

  function finish() {
    stop();
    setStatus('End of the book.');
  }

  const toggle = () => (state.playing ? stop() : play());

  function jumpSentence(direction) {
    if (!state.words.length) return;
    const wasPlaying = state.playing;
    stop();
    const word = state.words[Math.min(state.idx, state.words.length - 1)];
    const sentence = state.sentences[word.s];
    let target;
    if (direction < 0) {
      // Back to the start of this sentence, or the previous one if already there.
      target = state.idx - sentence.start > 1 ? sentence.start : (state.sentences[word.s - 1] || sentence).start;
    } else {
      target = sentence.end;
    }
    if (target >= state.words.length) target = state.words.length - 1;
    show(target);
    if (wasPlaying) play();
  }

  /* ---------- keep a sentence ---------- */
  async function keepSentence() {
    const word = state.words[state.idx];
    if (!word) return;
    const sentence = state.sentences[word.s];
    const text = state.words.slice(sentence.start, sentence.end).map((w) => w.t).join(' ');
    try {
      const response = await fetch(`/read/${encodeURIComponent(bookId)}/highlights`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page_number: sentence.page, selected_text: text }),
      });
      if (!response.ok) throw new Error();
      toast('Kept in your notebook.');
    } catch (_) {
      toast('Could not keep that sentence just now.');
    }
  }

  /* ---------- stats ---------- */
  function updateStats() {
    const ms = state.playedMs + (state.playing ? performance.now() - state.playStarted : 0);
    const minutes = Math.floor(ms / 60000);
    const seconds = Math.floor((ms % 60000) / 1000);
    const day = new Date().toISOString().slice(0, 10);
    let today = 0;
    try {
      const raw = JSON.parse(localStorage.getItem('libxndr-flow-days') || '{}');
      raw[day] = (raw[day] || 0) + (state.sessionWords - (state.countedToday || 0));
      state.countedToday = state.sessionWords;
      localStorage.setItem('libxndr-flow-days', JSON.stringify(raw));
      today = raw[day];
    } catch (_) { today = state.sessionWords; }
    if (!state.sessionWords) { $('flow-stats').textContent = ''; return; }
    $('flow-stats').textContent = `${state.sessionWords.toLocaleString()} words this sitting · ${minutes}m ${String(seconds).padStart(2, '0')}s · ${today.toLocaleString()} today`;
  }
  setInterval(() => { if (state.playing) updateStats(); }, 5000);

  /* ---------- toast ---------- */
  let toastTimer;
  function toast(text) {
    const el = $('flow-toast');
    el.textContent = text;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 2200);
  }

  /* ---------- background ---------- */
  const canvas = $('flow-bg');
  const ctx = canvas.getContext('2d');
  let bgW = 0; let bgH = 0;
  function resize() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    bgW = canvas.clientWidth; bgH = canvas.clientHeight;
    canvas.width = Math.round(bgW * ratio); canvas.height = Math.round(bgH * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  }
  window.addEventListener('resize', resize);
  resize();

  const hash = (n) => { const x = Math.sin(n * 127.1) * 43758.5453; return x - Math.floor(x); };

  // Simple hieroglyph strokes, drawn at (x, y) with height h. Our own shapes, not traced from any source.
  const GLYPHS = [
    (x, y, h) => { // ankh
      ctx.beginPath(); ctx.ellipse(x, y - h * 0.72, h * 0.16, h * 0.22, 0, 0, Math.PI * 2);
      ctx.moveTo(x - h * 0.3, y - h * 0.48); ctx.lineTo(x + h * 0.3, y - h * 0.48);
      ctx.moveTo(x, y - h * 0.5); ctx.lineTo(x, y); ctx.stroke();
    },
    (x, y, h) => { // eye
      ctx.beginPath(); ctx.moveTo(x - h * 0.45, y - h * 0.55);
      ctx.quadraticCurveTo(x, y - h * 0.9, x + h * 0.45, y - h * 0.55);
      ctx.quadraticCurveTo(x, y - h * 0.3, x - h * 0.45, y - h * 0.55);
      ctx.moveTo(x + h * 0.06, y - h * 0.58); ctx.arc(x, y - h * 0.58, h * 0.07, 0, Math.PI * 2);
      ctx.moveTo(x - h * 0.05, y - h * 0.42); ctx.lineTo(x - h * 0.12, y - h * 0.08);
      ctx.moveTo(x + h * 0.12, y - h * 0.42); ctx.quadraticCurveTo(x + h * 0.3, y - h * 0.1, x + h * 0.14, y - h * 0.05);
      ctx.stroke();
    },
    (x, y, h) => { // water
      ctx.beginPath(); ctx.moveTo(x - h * 0.45, y - h * 0.3);
      for (let i = 1; i <= 6; i += 1) ctx.lineTo(x - h * 0.45 + i * h * 0.15, y - h * (i % 2 ? 0.42 : 0.3));
      ctx.stroke();
    },
    (x, y, h) => { // reed
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y - h * 0.8);
      ctx.quadraticCurveTo(x + h * 0.28, y - h * 0.7, x + h * 0.06, y - h * 0.45); ctx.stroke();
    },
    (x, y, h) => { // sun disk
      ctx.beginPath(); ctx.arc(x, y - h * 0.5, h * 0.22, 0, Math.PI * 2);
      ctx.moveTo(x + h * 0.04, y - h * 0.5); ctx.arc(x, y - h * 0.5, h * 0.04, 0, Math.PI * 2); ctx.stroke();
    },
    (x, y, h) => { // djed pillar
      ctx.beginPath(); ctx.moveTo(x - h * 0.08, y); ctx.lineTo(x - h * 0.08, y - h * 0.9);
      ctx.moveTo(x + h * 0.08, y); ctx.lineTo(x + h * 0.08, y - h * 0.9);
      for (let i = 0; i < 4; i += 1) { ctx.moveTo(x - h * 0.2, y - h * (0.62 + i * 0.08)); ctx.lineTo(x + h * 0.2, y - h * (0.62 + i * 0.08)); }
      ctx.stroke();
    },
    (x, y, h) => { // bird
      ctx.beginPath(); ctx.moveTo(x - h * 0.3, y - h * 0.1);
      ctx.quadraticCurveTo(x - h * 0.1, y - h * 0.55, x + h * 0.18, y - h * 0.6);
      ctx.lineTo(x + h * 0.32, y - h * 0.55);
      ctx.moveTo(x + h * 0.02, y - h * 0.35); ctx.lineTo(x - h * 0.02, y);
      ctx.moveTo(x + h * 0.1, y - h * 0.35); ctx.lineTo(x + h * 0.14, y); ctx.stroke();
    },
  ];
  const glyph = (n, x, y, h) => GLYPHS[Math.floor(hash(n) * GLYPHS.length)](x, y, h);

  function pyramid(cx, base, half, tall, lit, shade) {
    ctx.fillStyle = shade;
    ctx.beginPath(); ctx.moveTo(cx - half, base); ctx.lineTo(cx, base - tall); ctx.lineTo(cx + half, base); ctx.fill();
    ctx.fillStyle = lit;
    ctx.beginPath(); ctx.moveTo(cx - half, base); ctx.lineTo(cx, base - tall); ctx.lineTo(cx - half * 0.12, base); ctx.fill();
  }

  const BACKGROUNDS = {
    none: { draw() { ctx.fillStyle = '#000'; ctx.fillRect(0, 0, bgW, bgH); } },

    // A small runner crossing an endless night city, vaulting whatever is in the way.
    runner: {
      x: 0,
      draw(dt, speed) {
        this.x += dt * 0.32 * speed;
        const g = bgH * 0.84;
        const sky = ctx.createLinearGradient(0, 0, 0, g);
        sky.addColorStop(0, '#07061a'); sky.addColorStop(1, '#1d1036');
        ctx.fillStyle = sky; ctx.fillRect(0, 0, bgW, bgH);
        const layers = [[0.15, 0.42, '#130c26'], [0.4, 0.3, '#1b1233'], [0.75, 0.2, '#251842']];
        layers.forEach(([depth, tall, color], li) => {
          ctx.fillStyle = color;
          const off = this.x * depth;
          const width = 46 + li * 18;
          const first = Math.floor(off / width);
          for (let b = first; b < first + bgW / width + 2; b += 1) {
            const h = bgH * tall * (0.35 + hash(b + li * 1000) * 0.65);
            const bx = b * width - off;
            ctx.fillRect(bx, g - h, width - 3, h);
            if (li === 2) {
              ctx.fillStyle = 'rgba(227,179,65,.18)';
              for (let wy = g - h + 10; wy < g - 8; wy += 14) if (hash(b * 31 + wy) > 0.55) ctx.fillRect(bx + 8, wy, 5, 6);
              ctx.fillStyle = color;
            }
          }
        });
        ctx.fillStyle = '#0b0718'; ctx.fillRect(0, g, bgW, bgH - g);
        ctx.strokeStyle = 'rgba(43,179,163,.5)'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(0, g); ctx.lineTo(bgW, g); ctx.stroke();
        const spacing = 360;
        const runnerX = bgW * 0.22;
        const firstOb = Math.floor((this.x - runnerX) / spacing);
        let jump = 0;
        ctx.fillStyle = 'rgba(214,90,43,.75)';
        for (let o = firstOb; o < firstOb + bgW / spacing + 2; o += 1) {
          if (hash(o * 7.3) < 0.25) continue;
          const ox = o * spacing + 200 - this.x + runnerX;
          const oh = 18 + hash(o) * 26;
          ctx.fillRect(ox, g - oh, 22, oh);
          const d = ox + 11 - runnerX;
          if (Math.abs(d) < 90) jump = Math.max(jump, Math.cos((d / 90) * (Math.PI / 2)) * (oh + 30));
        }
        const phase = this.x / 18;
        const by = g - 34 - jump;
        ctx.strokeStyle = '#e3b341'; ctx.lineWidth = 4; ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.arc(runnerX + 4, by - 14, 7, 0, Math.PI * 2);
        ctx.moveTo(runnerX, by - 6); ctx.lineTo(runnerX - 3, by + 14);
        const legA = jump > 4 ? 0.9 : Math.sin(phase); const legB = jump > 4 ? -0.4 : -Math.sin(phase);
        ctx.moveTo(runnerX - 3, by + 14); ctx.lineTo(runnerX - 3 + legA * 12, by + 34);
        ctx.moveTo(runnerX - 3, by + 14); ctx.lineTo(runnerX - 3 + legB * 12, by + 34);
        ctx.moveTo(runnerX, by); ctx.lineTo(runnerX + legB * 11, by + 12);
        ctx.moveTo(runnerX, by); ctx.lineTo(runnerX + legA * 11, by + 12);
        ctx.stroke();
      },
    },

    // Neon grid rushing toward a low sun.
    tunnel: {
      z: 0,
      draw(dt, speed) {
        this.z = (this.z + dt * 0.0012 * speed) % 1;
        const hz = bgH * 0.48;
        const sky = ctx.createLinearGradient(0, 0, 0, hz);
        sky.addColorStop(0, '#05020f'); sky.addColorStop(1, '#2a0b33');
        ctx.fillStyle = sky; ctx.fillRect(0, 0, bgW, hz);
        ctx.fillStyle = '#05020c'; ctx.fillRect(0, hz, bgW, bgH - hz);
        const sun = ctx.createLinearGradient(0, hz - bgH * 0.22, 0, hz);
        sun.addColorStop(0, 'rgba(242,207,109,.55)'); sun.addColorStop(1, 'rgba(214,90,43,.45)');
        ctx.fillStyle = sun;
        ctx.beginPath(); ctx.arc(bgW / 2, hz, bgH * 0.2, Math.PI, 0); ctx.fill();
        ctx.strokeStyle = 'rgba(43,179,163,.45)'; ctx.lineWidth = 1.5;
        for (let i = -14; i <= 14; i += 1) {
          ctx.beginPath(); ctx.moveTo(bgW / 2 + i * 8, hz); ctx.lineTo(bgW / 2 + i * bgW * 0.18, bgH); ctx.stroke();
        }
        for (let i = 0; i < 14; i += 1) {
          const p = (i + this.z) / 14;
          const y = hz + (bgH - hz) * p * p;
          ctx.globalAlpha = 0.2 + p * 0.6;
          ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(bgW, y); ctx.stroke();
        }
        ctx.globalAlpha = 1;
      },
    },

    // The Nile at night: pyramids drifting past, a felucca on moonlit water, a frieze of glyphs underfoot.
    nile: {
      x: 0,
      draw(dt, speed) {
        this.x += dt * 0.12 * speed;
        const t = performance.now() / 1000;
        const bank = bgH * 0.7; const river = bgH * 0.84;
        const sky = ctx.createLinearGradient(0, 0, 0, bank);
        sky.addColorStop(0, '#05060f'); sky.addColorStop(0.65, '#16122a'); sky.addColorStop(1, '#3a2418');
        ctx.fillStyle = sky; ctx.fillRect(0, 0, bgW, bank);
        for (let i = 0; i < 90; i += 1) {
          const sx = (hash(i) * bgW * 1.5 - this.x * 0.02) % bgW; const sy = hash(i + 50) * bank * 0.7;
          ctx.fillStyle = `rgba(243,239,228,${0.25 + 0.5 * Math.abs(Math.sin(t * (0.5 + hash(i + 9)) + i))})`;
          ctx.fillRect(sx < 0 ? sx + bgW : sx, sy, 1.6, 1.6);
        }
        const mx = bgW * 0.78; const my = bank * 0.26; const mr = Math.min(bgW, bgH) * 0.06;
        const halo = ctx.createRadialGradient(mx, my, mr, mx, my, mr * 5);
        halo.addColorStop(0, 'rgba(242,207,109,.22)'); halo.addColorStop(1, 'rgba(242,207,109,0)');
        ctx.fillStyle = halo; ctx.fillRect(0, 0, bgW, bank);
        ctx.fillStyle = '#f2e3b0'; ctx.beginPath(); ctx.arc(mx, my, mr, 0, Math.PI * 2); ctx.fill();
        [[0.06, 0.2, '#4a3220', '#22160f', 520], [0.16, 0.32, '#7a5328', '#2b1b10', 700]].forEach(([depth, tall, lit, shade, gap], li) => {
          gap *= Math.min(1, bgW / 900) * 0.6 + 0.4; const off = this.x * depth; const first = Math.floor(off / gap);
          for (let p = first - 1; p < first + bgW / gap + 2; p += 1) {
            if (hash(p * 3 + li) < 0.3) continue;
            const h = Math.min(bgH, bgW * 1.1) * tall * (0.6 + hash(p + li * 77) * 0.4);
            const cx = p * gap - off + hash(p * 5) * gap * 0.4;
            pyramid(cx, bank, h * 0.95, h, lit, shade);
            if (li === 1 && hash(p * 11) > 0.5) pyramid(cx + h * 1.1, bank, h * 0.6, h * 0.62, lit, shade);
          }
        });
        ctx.fillStyle = '#120c08';
        ctx.beginPath(); ctx.moveTo(0, bank);
        for (let px = 0; px <= bgW; px += 20) ctx.lineTo(px, bank - 6 - 6 * Math.sin((px + this.x * 0.4) / 90));
        ctx.lineTo(bgW, bank + 4); ctx.lineTo(0, bank + 4); ctx.fill();
        const palms = this.x * 0.45; const pg = 260; const pf = Math.floor(palms / pg);
        ctx.strokeStyle = '#0b0805'; ctx.fillStyle = '#0b0805'; ctx.lineWidth = 4;
        for (let p = pf - 1; p < pf + bgW / pg + 2; p += 1) {
          if (hash(p * 13) < 0.45) continue;
          const px = p * pg - palms; const ph = 70 + hash(p) * 60; const sway = Math.sin(t * 0.8 + p) * 4;
          ctx.beginPath(); ctx.moveTo(px, bank); ctx.quadraticCurveTo(px + 10, bank - ph / 2, px + sway, bank - ph); ctx.stroke();
          for (let f = 0; f < 6; f += 1) {
            const a = -Math.PI / 2 + (f - 2.5) * 0.55;
            ctx.beginPath(); ctx.moveTo(px + sway, bank - ph);
            ctx.quadraticCurveTo(px + sway + Math.cos(a) * 30, bank - ph + Math.sin(a) * 30 - 6, px + sway + Math.cos(a) * 46, bank - ph + Math.sin(a) * 30 + 14);
            ctx.stroke();
          }
        }
        const water = ctx.createLinearGradient(0, bank, 0, river);
        water.addColorStop(0, '#0c1a22'); water.addColorStop(1, '#06100f');
        ctx.fillStyle = water; ctx.fillRect(0, bank + 4, bgW, river - bank - 4);
        for (let i = 0; i < 14; i += 1) {
          const ry = bank + 10 + i * ((river - bank - 14) / 14);
          const w = mr * (2.2 - i * 0.08) * (0.7 + 0.3 * Math.sin(t * 2 + i));
          ctx.fillStyle = `rgba(242,207,109,${0.28 - i * 0.015})`;
          ctx.fillRect(mx - w / 2 + Math.sin(t * 1.5 + i * 1.7) * 6, ry, w, 2);
        }
        const bx = bgW * 0.38 + Math.sin(t * 0.2) * 20; const by = bank + (river - bank) * 0.45 + Math.sin(t * 1.3) * 2;
        ctx.fillStyle = '#0b0805';
        ctx.beginPath(); ctx.moveTo(bx - 48, by); ctx.quadraticCurveTo(bx, by + 14, bx + 52, by - 2); ctx.lineTo(bx + 40, by - 4); ctx.lineTo(bx - 40, by - 4); ctx.fill();
        ctx.strokeStyle = '#0b0805'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(bx - 4, by - 4); ctx.lineTo(bx - 4, by - 70); ctx.stroke();
        ctx.fillStyle = 'rgba(243,232,200,.85)';
        ctx.beginPath(); ctx.moveTo(bx - 2, by - 72); ctx.lineTo(bx + 44, by - 10); ctx.lineTo(bx - 2, by - 12); ctx.fill();
        ctx.fillStyle = '#0d0a07'; ctx.fillRect(0, river, bgW, bgH - river);
        ctx.strokeStyle = 'rgba(168,121,27,.8)'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(0, river + 3); ctx.lineTo(bgW, river + 3); ctx.moveTo(0, bgH - 4); ctx.lineTo(bgW, bgH - 4); ctx.stroke();
        const fh = Math.min(40, (bgH - river) * 0.6); const fx = this.x * 1.0; const cell = fh * 1.3;
        const ff = Math.floor(fx / cell);
        ctx.strokeStyle = '#e3b341'; ctx.lineWidth = Math.max(1.5, fh / 16); ctx.lineCap = 'round';
        for (let g = ff; g < ff + bgW / cell + 2; g += 1) glyph(g, g * cell - fx + cell / 2, river + (bgH - river + fh) / 2, fh);
      },
    },

    // Walking a temple hall: carved columns come toward you out of torchlight.
    temple: {
      z: 0,
      draw(dt, speed) {
        this.z += dt * 0.00035 * speed;
        if (this.z >= 1) { this.z -= 1; this.k = (this.k || 0) + 1; }
        const t = performance.now() / 1000;
        const cx = bgW / 2; const hz = bgH * 0.46;
        ctx.fillStyle = '#060403'; ctx.fillRect(0, 0, bgW, bgH);
        const floor = ctx.createLinearGradient(0, hz, 0, bgH);
        floor.addColorStop(0, '#1a1209'); floor.addColorStop(1, '#4a3418');
        ctx.fillStyle = floor; ctx.fillRect(0, hz, bgW, bgH - hz);
        const glow = ctx.createRadialGradient(cx, hz, 4, cx, hz, bgH * (0.5 + 0.03 * Math.sin(t * 9) + 0.02 * Math.sin(t * 23)));
        glow.addColorStop(0, 'rgba(242,170,70,.55)'); glow.addColorStop(1, 'rgba(242,170,70,0)');
        ctx.fillStyle = glow; ctx.fillRect(0, 0, bgW, bgH);
        ctx.strokeStyle = 'rgba(227,179,65,.12)'; ctx.lineWidth = 1;
        for (let i = 0; i < 12; i += 1) {
          const p = (i + this.z) / 12; const y = hz + (bgH - hz) * p * p;
          ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(bgW, y); ctx.stroke();
        }
        const N = 9;
        for (let i = 0; i < N; i += 1) {
          const p = (i + this.z) / N; const s = p * p;
          if (s < 0.01) continue;
          const spread = bgW * 0.06 + bgW * 0.75 * s;
          const w = 6 + bgW * 0.16 * s; const top = hz - bgH * 1.1 * s; const bottom = hz + (bgH - hz) * s;
          const id = i - (this.k || 0); // the same column keeps the same carvings as it walks toward you
          [-1, 1].forEach((side) => {
            const x = cx + side * spread - w / 2;
            const shade = Math.round(22 + 78 * s);
            ctx.fillStyle = `rgb(${shade + 30},${shade + 8},${Math.round(shade * 0.55)})`;
            ctx.fillRect(x, top, w, bottom - top);
            ctx.fillStyle = 'rgba(0,0,0,.35)'; ctx.fillRect(side < 0 ? x : x + w * 0.7, top, w * 0.3, bottom - top);
            ctx.fillStyle = `rgb(${shade + 50},${shade + 25},${Math.round(shade * 0.6)})`;
            ctx.fillRect(x - w * 0.12, top + (bottom - top) * 0.04, w * 1.24, (bottom - top) * 0.04);
            if (w > 24) {
              ctx.strokeStyle = `rgba(227,179,65,${Math.min(0.55, s * 1.2)})`; ctx.lineWidth = Math.max(1, w / 28); ctx.lineCap = 'round';
              const gh = w * 0.45; const rows = Math.floor((bottom - top) * 0.8 / (gh * 1.3));
              for (let r = 0; r < rows; r += 1) glyph(id * 31 + r * 7 + side + 5, x + w / 2, top + (bottom - top) * 0.12 + (r + 1) * gh * 1.3, gh);
            }
          });
        }
      },
    },

    // The book's own letters falling in columns.
    rain: {
      drops: [],
      draw(dt, speed) {
        ctx.fillStyle = 'rgba(0,0,0,.18)'; ctx.fillRect(0, 0, bgW, bgH);
        const size = 18;
        const cols = Math.ceil(bgW / size);
        if (this.drops.length !== cols) this.drops = Array.from({ length: cols }, (_, i) => hash(i) * bgH);
        ctx.font = `${size}px 'IBM Plex Mono', monospace`;
        const source = state.words.length ? state.words[(state.idx + 40) % state.words.length].t : 'LIBXNDR';
        for (let c = 0; c < cols; c += 1) {
          this.drops[c] += dt * 0.05 * speed * (0.6 + hash(c * 3) * 0.8);
          if (this.drops[c] > bgH + size) this.drops[c] = -hash(c + this.drops[c]) * 200;
          const ch = source.charAt(Math.floor(hash(c + Math.floor(this.drops[c] / size)) * source.length)) || '·';
          ctx.fillStyle = c % 7 === 0 ? 'rgba(227,179,65,.55)' : 'rgba(43,179,163,.4)';
          ctx.fillText(ch, c * size, this.drops[c]);
        }
      },
    },
  };

  let last = performance.now();
  function frame(now) {
    const dt = Math.min(64, now - last);
    last = now;
    const bg = BACKGROUNDS[settings.bg] || BACKGROUNDS.none;
    const speed = state.playing ? settings.wpm / 350 : 0.15;
    bg.draw(dt, speed);
    if (settings.bg !== 'none' && !document.hidden) requestAnimationFrame(frame);
    else bgLoop = false;
  }
  let bgLoop = false;
  function startBackground() {
    if (settings.bg === 'none') { BACKGROUNDS.none.draw(); return; }
    if (bgLoop) return;
    bgLoop = true; last = performance.now();
    requestAnimationFrame(frame);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) startBackground(); });

  /* ---------- controls ---------- */
  function setMode(mode) {
    const wasPlaying = state.playing;
    stop();
    settings.mode = mode;
    saveSettings();
    document.querySelectorAll('.flow-seg button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === mode)));
    if (wasPlaying) play();
  }
  function setWpm(value) {
    settings.wpm = Math.max(120, Math.min(1000, Math.round(value / 10) * 10));
    wpmInput.value = settings.wpm;
    $('flow-wpm-value').textContent = settings.wpm;
    saveSettings();
    if (state.playing && settings.mode === 'listen') { stop(); play(); } // new speech rate takes effect on restart
  }

  function fillVoices() {
    const select = $('flow-voice');
    const voices = BrowserNarrator.voices();
    select.replaceChildren();
    const auto = document.createElement('option');
    auto.value = ''; auto.textContent = 'Default';
    select.append(auto);
    voices
      .slice()
      .sort((a, b) => (b.lang.startsWith('en') - a.lang.startsWith('en')) || a.name.localeCompare(b.name))
      .forEach((v) => {
        const option = document.createElement('option');
        option.value = v.voiceURI; option.textContent = `${v.name} (${v.lang})`;
        select.append(option);
      });
    select.value = settings.voice;
    if (select.value !== settings.voice) select.value = '';
  }
  if (window.speechSynthesis) {
    fillVoices();
    speechSynthesis.addEventListener?.('voiceschanged', fillVoices);
  }

  playBtn.addEventListener('click', toggle);
  $('flow-tap').addEventListener('click', toggle);
  $('flow-back-sentence').addEventListener('click', () => jumpSentence(-1));
  $('flow-skip-sentence').addEventListener('click', () => jumpSentence(1));
  $('flow-keep').addEventListener('click', keepSentence);
  wpmInput.addEventListener('input', () => setWpm(Number(wpmInput.value)));
  document.querySelectorAll('.flow-seg button').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.mode)));
  $('flow-more').addEventListener('click', () => {
    const panel = $('flow-settings');
    panel.hidden = !panel.hidden;
    $('flow-more').setAttribute('aria-expanded', String(!panel.hidden));
  });
  $('flow-bg-select').addEventListener('change', (e) => { settings.bg = e.target.value; saveSettings(); startBackground(); });
  $('flow-chunk').addEventListener('change', (e) => { settings.chunk = Number(e.target.value); saveSettings(); });
  $('flow-voice').addEventListener('change', (e) => { settings.voice = e.target.value; saveSettings(); if (state.playing && settings.mode === 'listen') { stop(); play(); } });
  $('flow-show-context').addEventListener('change', (e) => {
    settings.context = e.target.checked; saveSettings();
    shell.classList.toggle('hide-context', !settings.context);
    renderContext(state.idx, 1);
  });
  pageInput.addEventListener('change', () => { if (state.pdf) openAt(pageInput.value); });

  document.addEventListener('keydown', (e) => {
    // Typing fields keep their keys; on buttons, sliders and checkboxes the shortcuts still work.
    const field = e.target.closest('select, textarea, input:not([type=range]):not([type=checkbox])');
    if (field || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target.type === 'range' && e.key.startsWith('Arrow')) return; // the slider moves itself
    if (e.key === ' ') { e.preventDefault(); toggle(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); jumpSentence(-1); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); jumpSentence(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setWpm(settings.wpm + 25); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); setWpm(settings.wpm - 25); }
    else if (e.key === 'l' || e.key === 'L') setMode(settings.mode === 'listen' ? 'flash' : 'listen');
    else if (e.key === 'k' || e.key === 'K') keepSentence();
  });
  window.addEventListener('pagehide', () => { if (window.speechSynthesis) speechSynthesis.cancel(); });

  // Reflect saved settings in the controls.
  setWpm(settings.wpm);
  document.querySelectorAll('.flow-seg button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === settings.mode)));
  $('flow-bg-select').value = settings.bg;
  $('flow-chunk').value = String(settings.chunk);
  $('flow-show-context').checked = settings.context;
  shell.classList.toggle('hide-context', !settings.context);
  startBackground();

  window.LibxndrFlow = {
    registerNarrator(name, impl) { NARRATORS[name] = impl; },
    useNarrator(name) { if (NARRATORS[name]) { stop(); narrator = NARRATORS[name]; } },
    state,
  };

  /* ---------- open ---------- */
  pdfjsLib.getDocument({ url: pdfUrl, withCredentials: pdfUrl.startsWith('/') }).promise
    .then((pdf) => {
      state.pdf = pdf;
      $('flow-page-count').textContent = pdf.numPages;
      pageInput.max = pdf.numPages;
      return openAt(Number(shell.dataset.startPage) || 1);
    })
    .then(() => { if (state.words.length) setStatus('Tap, or press space, to start.'); })
    .catch(() => setStatus('This PDF could not be opened just now.'));
})();
