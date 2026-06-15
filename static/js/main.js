// GED Veículos — main.js

// Auto-dismiss messages after 5s
document.querySelectorAll('.msg').forEach(el => {
  setTimeout(() => {
    el.style.transition = 'opacity .4s';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 400);
  }, 5000);
});
