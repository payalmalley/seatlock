// Selection counter + max 4 seats + hold countdown. The server re-checks everything.
const MAX_SEATS = 4;
const checks = document.querySelectorAll(".seat-check");
const holdBtn = document.getElementById("hold-btn");
const countEl = document.getElementById("selected-count");

function updateSelection() {
  const picked = [...checks].filter((c) => c.checked).length;
  if (countEl) countEl.textContent = picked;
  if (holdBtn) holdBtn.disabled = picked === 0;
  checks.forEach((c) => {
    if (!c.checked) c.disabled = picked >= MAX_SEATS;
  });
}
checks.forEach((c) => c.addEventListener("change", updateSelection));

// Countdown for the student's own hold
const mine = document.querySelector("[data-expires]");
if (mine) {
  const expires = new Date(mine.dataset.expires).getTime();
  const box = document.getElementById("hold-timer");
  const text = document.getElementById("timer-text");
  const confirmForm = document.getElementById("confirm-form");
  box.classList.remove("d-none");
  if (confirmForm) confirmForm.classList.remove("d-none");

  const tick = setInterval(() => {
    const left = Math.max(0, Math.floor((expires - Date.now()) / 1000));
    text.textContent = String(Math.floor(left / 60)).padStart(2, "0") + ":" + String(left % 60).padStart(2, "0");
    if (left === 0) {
      clearInterval(tick);
      location.reload(); // expired holds are released by the server
    }
  }, 1000);
}