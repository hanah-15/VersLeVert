"use strict";

(() => {
  const form = document.querySelector("[data-offer-filter-form]");
  const results = document.querySelector("[data-offers-results]");
  const status = document.querySelector("[data-offer-status]");
  if (!form || !results || !status) return;

  const search = form.querySelector('input[name="q"]');
  let debounceTimer;
  let activeRequest;

  function showError(message) {
    status.textContent = message;
    status.className = "mt-2 text-sm font-semibold text-brick";
  }

  function updateDropdown(dropdown, value) {
    const input = form.querySelector(`[data-offer-filter-value="${dropdown.dataset.offerDropdown}"]`);
    const options = [...dropdown.querySelectorAll("[data-offer-option]")];
    const selected = options.find((option) => option.dataset.value === value);
    if (!input || !selected) return;

    input.value = value;
    dropdown.querySelector("[data-offer-dropdown-label]").textContent = selected.dataset.label;
    options.forEach((option) => {
      if (option === selected) option.setAttribute("aria-pressed", "true");
      else option.removeAttribute("aria-pressed");
    });
  }

  async function updateResults(updateAddress = true) {
    const url = new URL(form.action, window.location.origin);
    new FormData(form).forEach((value, key) => {
      if (value) url.searchParams.set(key, value);
    });

    if (activeRequest) activeRequest.abort();
    activeRequest = new AbortController();
    status.textContent = "Mise à jour des offres…";
    status.className = "mt-2 text-sm text-muted";

    try {
      const response = await fetch(url, {
        signal: activeRequest.signal,
        headers: { "X-Requested-With": "XMLHttpRequest" },
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`La recherche a échoué (${response.status}).`);

      const documentFragment = new DOMParser().parseFromString(await response.text(), "text/html");
      const updatedResults = documentFragment.querySelector("[data-offers-results]");
      if (!updatedResults) throw new Error("La réponse ne contient pas les résultats des offres.");

      results.innerHTML = updatedResults.innerHTML;
      if (updateAddress) window.history.replaceState(null, "", url);
      status.textContent = "Offres actualisées.";
      status.className = "sr-only";
    } catch (error) {
      if (error.name === "AbortError") return;
      console.error("Impossible d’actualiser les offres.", error);
      showError("Impossible d’actualiser les offres. Vérifiez votre connexion et réessayez.");
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    window.clearTimeout(debounceTimer);
    updateResults();
  });

  search.addEventListener("input", () => {
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => updateResults(), 250);
  });

  form.querySelectorAll("[data-offer-dropdown]").forEach((dropdown) => {
    dropdown.addEventListener("click", (event) => {
      const option = event.target.closest("[data-offer-option]");
      if (!option) return;
      updateDropdown(dropdown, option.dataset.value);
      dropdown.open = false;
      updateResults();
    });
  });

  form.querySelector("[data-offer-reset]").addEventListener("click", () => {
    search.value = "";
    form.querySelectorAll("[data-offer-dropdown]").forEach((dropdown) => {
      updateDropdown(dropdown, dropdown.dataset.offerDropdown === "sort" ? "points_asc" : "");
    });
    window.clearTimeout(debounceTimer);
    updateResults();
  });

  window.addEventListener("popstate", () => {
    const url = new URL(window.location.href);
    search.value = url.searchParams.get("q") || "";
    form.querySelectorAll("[data-offer-dropdown]").forEach((dropdown) => {
      const parameter = dropdown.dataset.offerDropdown;
      const value = url.searchParams.get(parameter) || (parameter === "sort" ? "points_asc" : "");
      updateDropdown(dropdown, value);
    });
    updateResults(false);
  });
})();
