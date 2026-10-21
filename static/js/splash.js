/* Opening splash. Runs synchronously while the page parses so the pyramid is the first thing seen.
   First open of a session: the full splash (pyramid, name, count) for at least two seconds.
   Every page after that: a brief pass of the pyramid while the next page arrives. */
(function () {
  var opened = false;
  try { opened = !!sessionStorage.getItem('libxndr-opened'); } catch (e) { /* storage unavailable: treat as first open */ }
  var template = document.getElementById('splash-template');
  if (!template || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (opened) return; // one quiet opening per session; page changes are instant after that
  var splash = template.content.firstElementChild.cloneNode(true);
  splash.dataset.shownAt = String(performance.now());
  splash.dataset.mode = opened ? 'brief' : 'full';
  if (opened) splash.classList.add('splash-brief');
  document.body.prepend(splash);
  document.documentElement.classList.add('is-splashing');
})();
