"use strict";

/* ── Close dropdowns on outside click ─────────────────────────────────── */
document.addEventListener("click", (event) => {
  document.querySelectorAll("details[data-menu][open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });

  /* Password toggle */
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
  if (event.key === "Escape")
    document.querySelectorAll("details[data-menu][open]").forEach((menu) => {
      menu.open = false;
      menu.querySelector("summary").focus();
    });
});

/* ── Navbar scroll-blur ────────────────────────────────────────────────── */
(function () {
  const header = document.querySelector(".eco-header");
  if (!header) return;
  const onScroll = () => {
    const scrolled = window.scrollY > 16;
    header.classList.toggle("eco-header--scrolled", scrolled);
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll(); // run once on load
})();

/* ── Material Tabs — sliding indicator ────────────────────────────────── */
(function () {
  document.querySelectorAll(".mat-tabs").forEach((tabBar) => {
    const indicator = tabBar.querySelector(".mat-tab-indicator");
    if (!indicator) return;

    function positionIndicator(activeLink) {
      if (!activeLink) return;
      const barRect  = tabBar.getBoundingClientRect();
      const linkRect = activeLink.getBoundingClientRect();
      const left     = linkRect.left - barRect.left + tabBar.scrollLeft;
      indicator.style.width     = linkRect.width + "px";
      indicator.style.transform = `translateX(${left}px)`;
    }

    const activeLink = tabBar.querySelector("a[aria-current='page']");
    positionIndicator(activeLink);

    tabBar.querySelectorAll("a").forEach((link) => {
      link.addEventListener("mouseenter", () => positionIndicator(link));
    });
    tabBar.addEventListener("mouseleave", () => positionIndicator(activeLink));

    // Scroll active tab into view
    if (activeLink) {
      activeLink.scrollIntoView({ inline: "center", behavior: "instant", block: "nearest" });
    }
  });
})();
