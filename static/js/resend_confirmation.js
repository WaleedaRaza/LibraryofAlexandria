(() => {
  let seconds = 20;
  const countdown = document.getElementById('countdown');
  const countdownText = document.getElementById('countdown-text');
  const form = document.getElementById('resend-form');
  const button = document.getElementById('resend-btn');
  const status = document.getElementById('resend-status');
  const timer = setInterval(() => {
    seconds -= 1;
    countdown.textContent = seconds;
    if (seconds <= 0) {
      clearInterval(timer);
      countdownText.hidden = true;
      form.hidden = false;
    }
  }, 1000);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    button.disabled = true;
    button.textContent = 'Sending…';
    try {
      const response = await fetch('/auth/resend', { method: 'POST', body: new FormData(form) });
      const result = await response.json();
      status.hidden = false;
      status.textContent = result.success ? '✓ Email sent. Check your inbox.' : (result.error || 'Could not send. Try again.');
      if (result.success) form.hidden = true;
      else button.disabled = false;
    } catch (_) {
      status.hidden = false;
      status.textContent = 'Network error. Try again.';
      button.disabled = false;
    }
    button.textContent = 'Resend confirmation email';
  });
})();
