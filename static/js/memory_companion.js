(() => {
  const shell = document.querySelector("[data-memory-companion]");
  if (!shell) return;
  const form = shell.querySelector("[data-memory-form]");
  const input = form?.querySelector("textarea");
  const submit = form?.querySelector("button[type=submit]");
  const thread = shell.querySelector("#memory-companion-thread");
  const error = shell.querySelector("[data-memory-error]");

  function addMessage(message) {
    shell.querySelector("[data-memory-empty]")?.remove();
    const article = document.createElement("article");
    article.className = `memory-message memory-message-${message.role}`;
    const label = document.createElement("span");
    label.textContent = message.role === "user" ? "YOU" : "COMPANION";
    const body = document.createElement("p");
    body.textContent = message.content;
    article.append(label, body);
    if (message.sources?.length) {
      const sources = document.createElement("div");
      sources.className = "memory-message-sources";
      message.sources.forEach((source) => {
        const link = document.createElement("a");
        link.href = source.url;
        link.textContent = `${source.title} · p.${source.page_number}`;
        sources.append(link);
      });
      article.append(sources);
    }
    thread.append(article);
    thread.scrollTop = thread.scrollHeight;
  }

  shell.querySelectorAll("[data-memory-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      input.value = button.dataset.memoryPrompt;
      input.focus();
    });
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question || submit.disabled) return;
    error.textContent = "";
    addMessage({role: "user", content: question, sources: []});
    input.value = "";
    submit.disabled = true;
    submit.textContent = "Reading your memory…";
    try {
      const response = await fetch(shell.dataset.endpoint, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({question}),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "The companion could not answer.");
      addMessage(payload.message);
    } catch (requestError) {
      error.textContent = requestError.message || "The companion could not answer. Your memory is safe.";
    } finally {
      submit.disabled = false;
      submit.textContent = "Ask across memory ↗";
      input.focus();
    }
  });

  if (thread) thread.scrollTop = thread.scrollHeight;
})();
