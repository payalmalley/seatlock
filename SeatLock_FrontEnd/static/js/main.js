// Auto-hide alert messages after 6 seconds
document.querySelectorAll(".sl-alert").forEach((el) => {
  setTimeout(() => el.remove(), 6000);
});

// Client-side search on the events page
const search = document.getElementById("event-search");
if (search) {
  const cards = [...document.querySelectorAll("#event-grid .sl-card")];
  const none = document.getElementById("no-match");
  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    let shown = 0;
    cards.forEach((c) => {
      const hit = !q || c.dataset.search.includes(q);
      c.style.display = hit ? "" : "none";
      if (hit) shown++;
    });
    if (none) none.classList.toggle("d-none", shown > 0 || cards.length === 0);
  });
}