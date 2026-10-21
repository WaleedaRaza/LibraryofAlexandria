(() => {
  const card = document.getElementById('reset-card');
  const form = document.getElementById('reset-form');
  const loading = document.getElementById('reset-loading');
  const error = document.getElementById('reset-error');
  if (!card || !form || !loading || !error) return;

  const params = new URLSearchParams(window.location.hash.substring(1));
  const accessToken = params.get('access_token');
  history.replaceState(null, '', window.location.pathname + window.location.search);

  const showError = (message) => {
    loading.hidden = true;
    form.hidden = true;
    error.textContent = message;
    error.hidden = false;
  };
  const showForm = () => {
    loading.hidden = true;
    error.hidden = true;
    form.hidden = false;
  };

  if (card.dataset.ready === 'true') {
    showForm();
    return;
  }
  if (!accessToken) {
    showError('That password-reset link is invalid or has expired. Request a new one below.');
    return;
  }
  fetch('/auth/recovery-session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ access_token: accessToken }),
  }).then(async (response) => {
    if (response.ok) showForm();
    else {
      const result = await response.json().catch(() => ({}));
      showError(result.error || 'That password-reset link could not be verified.');
    }
  }).catch(() => showError('The reset link could not be checked. Please try again.'));
})();
