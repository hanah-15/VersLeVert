"use strict";
document.addEventListener("click", (event) => {
  document.querySelectorAll("details[data-menu][open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
  const toggle = event.target.closest("[data-password-toggle]");
  if (toggle) {
    const input = document.getElementById(toggle.dataset.passwordToggle);
    if (!input) return;
    const showing = input.type === "password";
    input.type = showing ? "text" : "password";
    toggle.setAttribute("aria-pressed", String(showing));
    toggle.setAttribute("aria-label", showing ? "Masquer le mot de passe" : "Afficher le mot de passe");
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") document.querySelectorAll("details[data-menu][open]").forEach((menu) => {
    menu.open = false;
    menu.querySelector("summary").focus();
  });
});
