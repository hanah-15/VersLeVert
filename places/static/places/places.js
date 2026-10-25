"use strict";

for (const form of document.querySelectorAll("[data-proximity-form]")) {
  const button = form.querySelector("[data-use-location]");
  const status = form.querySelector("[data-location-status]");
  const resetOrigin = () => {
    form.elements.latitude.value = "";
    form.elements.longitude.value = "";
  };
  form.elements.near_place.addEventListener("change", () => {
    resetOrigin();
    if (form.elements.near_place.value) {
      form.elements.city.value = "";
      status.textContent = "Autour de : " + form.elements.near_place.selectedOptions[0].textContent + ".";
    } else {
      form.elements.radius.value = "";
      status.textContent = "Choisissez un lieu ou utilisez votre position.";
    }
  });
  form.elements.city.addEventListener("input", () => {
    resetOrigin();
    form.elements.near_place.value = "";
    form.elements.radius.value = "";
    status.textContent = "Recherche dans la ville ou le quartier indiqué.";
  });
  button.addEventListener("click", () => {
    if (!navigator.geolocation) {
      status.textContent = "Position indisponible. Indiquez une ville ou choisissez un lieu.";
      return;
    }
    button.disabled = true;
    status.textContent = "Recherche de votre position…";
    navigator.geolocation.getCurrentPosition((position) => {
      form.elements.latitude.value = position.coords.latitude.toFixed(6);
      form.elements.longitude.value = position.coords.longitude.toFixed(6);
      form.elements.near_place.value = "";
      form.elements.city.value = "";
      if (!form.elements.radius.value) form.elements.radius.value = "10";
      status.textContent = "Autour de moi · à moins de " + form.elements.radius.value + " km.";
      button.disabled = false;
      form.querySelector(".location-options").open = true;
      if (form.hasAttribute("data-location-form")) form.requestSubmit();
    }, () => {
      button.disabled = false;
      status.textContent = "Position indisponible. Indiquez une ville ou choisissez un lieu ci-dessous.";
    }, {timeout: 10000, maximumAge: 60000});
  });
}

const guideForm = document.querySelector("[data-guide-form]");
if (guideForm && window.fetch) {
  guideForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!guideForm.reportValidity()) return;
    const button = guideForm.querySelector("[data-guide-submit]");
    const status = guideForm.querySelector("[data-guide-status]");
    const errors = guideForm.querySelector("[data-guide-errors]");
    const results = document.querySelector("[data-guide-results]");
    button.disabled = true;
    guideForm.setAttribute("aria-busy", "true");
    errors.hidden = true;
    status.textContent = "Recherche des suggestions…";
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 22000);
    try {
      const response = await fetch(guideForm.dataset.guideEndpoint, {
        method: "POST", body: new FormData(guideForm), credentials: "same-origin",
        headers: {"Accept": "application/json"}, signal: controller.signal,
      });
      if (response.redirected) throw new Error("Votre session a expiré. Rechargez la page pour vous reconnecter.");
      if (!(response.headers.get("Content-Type") || "").includes("application/json")) throw new Error("La recherche n'a pas abouti. Réessayez dans un instant.");
      const data = await response.json();
      if (!response.ok) throw new Error([data.error || "La recherche n'a pas abouti.", ...Object.values(data.fields || {}).flat()].join(" "));
      // Only a Django-autoescaped server fragment is inserted here.
      results.innerHTML = data.html;
      results.hidden = false;
      results.querySelector("[data-results-heading]")?.focus();
      status.textContent = "Vos suggestions sont prêtes.";
      results.scrollIntoView({behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start"});
    } catch (error) {
      status.textContent = "";
      errors.textContent = error.name === "AbortError" ? "La recherche prend trop de temps. Réessayez dans un instant." : error.message;
      errors.hidden = false;
    } finally {
      clearTimeout(timeout);
      button.disabled = false;
      guideForm.removeAttribute("aria-busy");
    }
  });
}

const recommendationForm = document.querySelector("[data-recommendation-form]");
if (recommendationForm && window.fetch) {
  const prepareButton = recommendationForm.querySelector("[data-prepare-recommendation]");
  const applyButton = recommendationForm.querySelector("[data-apply-preparation]");
  const restoreButton = recommendationForm.querySelector("[data-restore-preparation]");
  const dismissButton = recommendationForm.querySelector("[data-dismiss-preparation]");
  const status = recommendationForm.querySelector("[data-preparation-status]");
  const errors = recommendationForm.querySelector("[data-preparation-errors]");
  const result = recommendationForm.querySelector("[data-preparation-result]");
  const review = recommendationForm.elements.description;
  let prepared = null;
  let original = null;
  let applied = null;
  const values = () => ({name: recommendationForm.elements.product_name.value, description: review.value, category: recommendationForm.elements.category.value});
  const unchanged = (snapshot) => snapshot && values().name === snapshot.name && values().description === snapshot.description;
  prepareButton.addEventListener("click", async () => {
    const source = values();
    errors.hidden = true;
    result.hidden = true;
    restoreButton.hidden = true;
    if (source.description.trim().length < 20) {
      errors.textContent = "Écrivez d'abord quelques mots dans votre avis (20 caractères minimum).";
      errors.hidden = false;
      review.focus();
      return;
    }
    prepareButton.disabled = true;
    status.textContent = "Amélioration de votre texte…";
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 22000);
    try {
      const body = new FormData();
      body.set("csrfmiddlewaretoken", recommendationForm.elements.csrfmiddlewaretoken.value);
      body.set("product_name", source.name);
      body.set("description", source.description);
      const response = await fetch(recommendationForm.dataset.preparationEndpoint, {
        method: "POST", body, credentials: "same-origin",
        headers: {"Accept": "application/json"}, signal: controller.signal,
      });
      if (response.redirected) throw new Error("Votre session a expiré. Rechargez la page pour vous reconnecter.");
      if (!(response.headers.get("Content-Type") || "").includes("application/json")) throw new Error("L'aide à la rédaction est indisponible. Votre texte est conservé.");
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "L'aide à la rédaction est indisponible.");
      if (!unchanged(source)) {
        status.textContent = "Vous avez modifié votre avis. Cliquez à nouveau pour améliorer la nouvelle version.";
        return;
      }
      if (!data.description || data.description.trim() === source.description.trim()) {
        status.textContent = "Votre texte est conservé. Vous pouvez le modifier ou l'envoyer pour validation.";
        return;
      }
      prepared = data;
      original = source;
      recommendationForm.querySelector("[data-prepared-description]").textContent = data.description;
      recommendationForm.querySelector("[data-preparation-warnings]").hidden = !data.warnings.length;
      result.hidden = false;
      status.textContent = "Relisez la proposition ci-dessous.";
    } catch (error) {
      status.textContent = "";
      errors.textContent = error.name === "AbortError" ? "L'aide prend trop de temps. Votre avis est conservé ; vous pouvez l'envoyer." : error.message;
      errors.hidden = false;
    } finally {
      clearTimeout(timeout);
      prepareButton.disabled = false;
    }
  });
  applyButton.addEventListener("click", () => {
    if (!prepared || !unchanged(original)) {
      result.hidden = true;
      status.textContent = "Votre avis a changé. Cliquez à nouveau sur « Améliorer mon texte ».";
      return;
    }
    // Keep manual choices. Fill the name/category only when they are still empty.
    if (!recommendationForm.elements.product_name.value && prepared.product_name) recommendationForm.elements.product_name.value = prepared.product_name;
    if (!recommendationForm.elements.category.value) recommendationForm.elements.category.value = prepared.category;
    review.value = prepared.description;
    applied = values();
    errors.hidden = true;
    result.hidden = true;
    restoreButton.hidden = false;
    status.textContent = "Texte mis à jour. Vous pouvez encore le modifier.";
    review.focus();
  });
  dismissButton.addEventListener("click", () => {
    result.hidden = true;
    status.textContent = "Votre texte est conservé.";
    review.focus();
  });
  restoreButton.addEventListener("click", () => {
    if (!original || !unchanged(applied)) {
      restoreButton.hidden = true;
      status.textContent = "Vos dernières modifications sont conservées.";
      return;
    }
    recommendationForm.elements.product_name.value = original.name;
    review.value = original.description;
    // Avoid reverting a category the author changed after accepting the text.
    if (values().category === applied.category) recommendationForm.elements.category.value = original.category;
    status.textContent = "Votre texte initial est rétabli.";
    restoreButton.hidden = true;
    review.focus();
  });
}
