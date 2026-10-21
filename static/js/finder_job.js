(() => {
  const shell = document.querySelector('[data-finder-job]');
  const live = document.getElementById('finder-live');
  if (!shell) return;

  shell.querySelectorAll('.finder-item form').forEach((form) => {
    const checkboxes = [...form.querySelectorAll('input[name="urls"]')];
    const note = form.querySelector('[data-selection-note]');
    const credit = form.querySelector('[data-credit-options]');
    const button = form.querySelector('button[type="submit"]');
    if (!checkboxes.length || !note || !credit || !button) return;
    const updateSelection = () => {
      const count = checkboxes.filter((input) => input.checked).length;
      note.classList.toggle('is-valid', count > 0);
      credit.classList.toggle('is-visible', count > 0);
      button.disabled = count === 0;
      note.replaceChildren();
      const mark = document.createElement('span');
      mark.setAttribute('aria-hidden', 'true');
      mark.textContent = count ? '✓' : '○';
      const copy = document.createElement('p');
      const strong = document.createElement('strong');
      strong.textContent = count ? 'Valid option.' : 'Select a result.';
      copy.append(strong, document.createTextNode(count
        ? ` ${count} source${count === 1 ? '' : 's'} selected. Consider contributing ${count === 1 ? 'it' : 'them'} to the library anonymously or with credit.`
        : ' Open it first and make sure it is the edition you want.'));
      note.append(mark, copy);
    };
    checkboxes.forEach((input) => input.addEventListener('change', updateSelection));
    updateSelection();
  });

  if (!['queued', 'running'].includes(shell.dataset.jobStatus)) return;
  const run = async () => {
    try {
      const response = await fetch(`/library/find/${shell.dataset.finderJob}/next`, { method: 'POST' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'The next title could not be checked.');
      live.textContent = `${result.completed} of ${result.total} checked. Saving progress…`;
      window.location.reload();
    } catch (error) {
      live.textContent = `${error.message} Reload to resume this run.`;
    }
  };
  run();
})();
