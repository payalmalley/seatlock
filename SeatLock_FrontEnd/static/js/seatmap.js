// Selection counter + max 4 seats + hold countdown. The server re-checks everything.
const MAX_SEATS = 4;
const checks = document.querySelectorAll(".seat-check");
const holdBtn = document.getElementById("hold-btn");
const countEl = document.getElementById("selected-count");
const pickedEl = document.getElementById("picked-seats");

function updateSelection() {
  const picked = [...checks].filter((c) => c.checked);
  if (countEl) countEl.textContent = picked.length;
  if (holdBtn) holdBtn.disabled = picked.length === 0;
  if (pickedEl) {
    pickedEl.innerHTML = picked.length
      ? picked.map((c) => `<span class="sl-chip">${c.dataset.label}</span>`).join("")
      : "<em>No seats selected</em>";
  }
  checks.forEach((c) => {
    if (!c.checked) c.disabled = picked.length >= MAX_SEATS;
  });
}
checks.forEach((c) => c.addEventListener("change", updateSelection));

// Countdown for the student's own hold
const mine = document.querySelector("[data-expires]");
if (mine) {
  const expires = new Date(mine.dataset.expires).getTime();
  const text = document.getElementById("timer-text");

  const render = () => {
    const left = Math.max(0, Math.floor((expires - Date.now()) / 1000));
    if (text) {
      text.textContent =
        String(Math.floor(left / 60)).padStart(2, "0") + ":" + String(left % 60).padStart(2, "0");
    }
    return left;
  };
  render();
  const tick = setInterval(() => {
    if (render() === 0) {
      clearInterval(tick);
      location.reload(); // expired holds are released by the server
    }
  }, 1000);
}