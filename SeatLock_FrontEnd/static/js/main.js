// Auto-hide alert messages after 6 seconds
document.querySelectorAll(".alert").forEach((el) => {
  setTimeout(() => el.remove(), 6000);
});