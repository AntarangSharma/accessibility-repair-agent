const form = document.querySelector("#run-form");
const message = document.querySelector("#form-message");
const button = document.querySelector("#run-button");
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  button.disabled = true;
  message.textContent =
    "Starting inspection. The original will remain available.";
  try {
    const response = await fetch("/api/runs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')
          .content,
      },
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    const result = await response.json();
    if (!response.ok)
      throw new Error(
        typeof result.detail === "string"
          ? result.detail
          : "The run could not start.",
      );
    window.location.assign(result.url);
  } catch (error) {
    message.textContent = error.message;
    button.disabled = false;
  }
});
if (document.body.dataset.poll) {
  button.disabled = true;
  const poll = async () => {
    try {
      const response = await fetch("/api/runs/" + document.body.dataset.poll);
      if (!response.ok) throw new Error("Status unavailable");
      const run = await response.json();
      if (run.terminal) {
        window.location.reload();
        return;
      }
      document.querySelector("#run-status").textContent = run.status;
      message.textContent = `Run in progress: ${run.attempts} candidate(s), ${run.calls} model call(s).`;
    } catch {
      message.textContent =
        "Connection interrupted. Reload to inspect the persisted run.";
    }
    setTimeout(poll, 1200);
  };
  setTimeout(poll, 1000);
}
