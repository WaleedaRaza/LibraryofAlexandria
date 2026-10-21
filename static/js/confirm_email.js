(() => {
  const params = new URLSearchParams(window.location.hash.substring(1));
  const accessToken = params.get('access_token');
  history.replaceState(null, '', window.location.pathname);
  const showError = (message) => {
    document.getElementById('status-title').textContent = 'Confirmation failed';
    document.getElementById('status-text').textContent = message;
    document.getElementById('sign-in-again').hidden = false;
  };
  if (!accessToken) {
    if (params.get('error_description') || params.get('error')) {
      showError('That confirmation link has expired or could not be verified. Please sign in again.');
    } else {
      window.location.replace('/auth/login');
    }
    return;
  }
  fetch('/auth/set-session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ access_token: accessToken, next: '/library/my' }),
  }).then(async (response) => {
    if (response.ok) {
      const result = await response.json();
      window.location.replace(result.redirect || '/library/my');
    } else showError('Session could not be created. Please try signing in.');
  }).catch(() => showError('Something went wrong. Please try signing in.'));
})();
