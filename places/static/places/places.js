"use strict";

const locationForm = document.querySelector("[data-location-form]");
if (locationForm) {
  const button = locationForm.querySelector("[data-use-location]");
  const status = locationForm.querySelector("[data-location-status]");
  button.addEventListener("click", () => {
    if (!navigator.geolocation) {
      status.textContent = "La géolocalisation n’est pas disponible. Saisissez vos coordonnées ci-dessous.";
      return;
    }
    button.disabled = true;
    status.textContent = "Recherche de votre position…";
    navigator.geolocation.getCurrentPosition((position) => {
      locationForm.elements.latitude.value = position.coords.latitude.toFixed(6);
      locationForm.elements.longitude.value = position.coords.longitude.toFixed(6);
      locationForm.requestSubmit();
    }, () => {
      button.disabled = false;
      status.textContent = "Position indisponible ou autorisation refusée. Vous pouvez saisir vos coordonnées manuellement.";
      locationForm.querySelector("details").open = true;
    }, {timeout: 10000, maximumAge: 60000});
  });
}

const guideForm = document.querySelector("[data-guide-form]");
if (guideForm) {
  for (const example of document.querySelectorAll("[data-guide-example]")) {
    example.addEventListener("click", () => {
      guideForm.elements.query.value = example.dataset.guideExample;
      guideForm.elements.query.focus();
    });
  }
  const locationButton = guideForm.querySelector("[data-guide-location]");
  locationButton.addEventListener("click", () => {
    const status = guideForm.querySelector("[data-guide-location-status]");
    if (!navigator.geolocation) {
      status.textContent = "Géolocalisation indisponible. Saisissez vos coordonnées dans les champs.";
      return;
    }
    locationButton.disabled = true;
    status.textContent = "Recherche de votre position…";
    navigator.geolocation.getCurrentPosition((position) => {
      guideForm.elements.latitude.value = position.coords.latitude.toFixed(6);
      guideForm.elements.longitude.value = position.coords.longitude.toFixed(6);
      if (!guideForm.elements.radius.value) guideForm.elements.radius.value = "10";
      status.textContent = "Position ajoutée. Elle sera utilisée uniquement pour filtrer les résultats locaux.";
      locationButton.disabled = false;
    }, () => {
      status.textContent = "Position indisponible ou autorisation refusée. Les coordonnées peuvent être saisies manuellement.";
      locationButton.disabled = false;
    }, {timeout: 10000, maximumAge: 60000});
  });
}
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
    status.textContent = "Compréhension de votre demande et recherche dans le catalogue…";
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(guideForm.dataset.guideEndpoint, {
        method: "POST", body: new FormData(guideForm), credentials: "same-origin",
        headers: {"Accept": "application/json"}, signal: controller.signal,
      });
      if (response.redirected) throw new Error("Votre session a expiré. Rechargez la page pour vous reconnecter.");
      if (!(response.headers.get("Content-Type") || "").includes("application/json")) {
        throw new Error("La demande n'a pas abouti. Rechargez la page et réessayez.");
      }
      const data = await response.json();
      if (!response.ok) {
        const details = Object.values(data.fields || {}).flat().join(" ");
        throw new Error([data.error || "La demande n'a pas abouti.", details].join(" "));
      }
      // This fragment is rendered by Django with autoescaping for every value.
      // Neither model output nor catalogue content is inserted as raw HTML.
      results.innerHTML = data.html;
      results.hidden = false;
      results.querySelector("[data-results-heading]")?.focus();
      status.textContent = data.source === "fallback"
        ? "Recherche locale terminée. La compréhension IA n'était pas disponible."
        : "Recherche terminée. Les sources sont disponibles sous chaque suggestion.";
    } catch (error) {
      status.textContent = "La recherche n'a pas abouti. Vos filtres et vos résultats précédents sont conservés.";
      errors.textContent = error.name === "AbortError"
        ? "Le délai de réponse est dépassé. Réessayez dans un instant."
        : error.message;
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
  const status = recommendationForm.querySelector("[data-preparation-status]");
  const errors = recommendationForm.querySelector("[data-preparation-errors]");
  const result = recommendationForm.querySelector("[data-preparation-result]");
  let prepared = null;
  let original = null;
  const values = () => ({name: recommendationForm.elements.product_name.value, description: recommendationForm.elements.description.value, category: recommendationForm.elements.category.value});
  prepareButton.addEventListener("click", async () => {
    const source = values();
    errors.hidden = true;
    if (source.description.trim().length < 20) {
      errors.textContent = "Décrivez d'abord votre expérience en au moins 20 caractères dans le champ ci-dessus.";
      errors.hidden = false;
      recommendationForm.elements.description.focus();
      return;
    }
    prepareButton.disabled = true;
    status.textContent = "L'assistant classe le produit et prépare votre brouillon…";
    result.setAttribute("aria-busy", "true");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 22000);
    try {
      const response = await fetch(recommendationForm.dataset.preparationEndpoint, {
        method: "POST", body: new FormData(recommendationForm), credentials: "same-origin",
        headers: {"Accept": "application/json"}, signal: controller.signal,
      });
      if (response.redirected) throw new Error("Votre session a expiré. Rechargez la page pour vous reconnecter.");
      if (!(response.headers.get("Content-Type") || "").includes("application/json")) throw new Error("La préparation n'a pas abouti. Votre texte est conservé.");
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "La préparation n'a pas abouti.");
      if (values().name !== source.name || values().description !== source.description) {
        status.textContent = "Votre texte a changé pendant la préparation. Relancez l'assistant pour utiliser la nouvelle version.";
        result.hidden = true;
        return;
      }
      prepared = data;
      original = source;
      recommendationForm.querySelector("[data-prepared-name]").textContent = data.product_name || "À compléter";
      recommendationForm.querySelector("[data-prepared-category]").textContent = data.category_label;
      recommendationForm.querySelector("[data-prepared-description]").textContent = data.description || "Aucun passage factuel utilisable n'a été repéré. Votre texte initial sera conservé.";
      const warnings = recommendationForm.querySelector("[data-preparation-warnings]");
      warnings.replaceChildren();
      for (const warning of data.warnings) {
        const paragraph = document.createElement("p");
        paragraph.className = "preparation-warning";
        paragraph.textContent = warning.message + " « " + warning.quote + " »";
        warnings.append(paragraph);
      }
      for (const missing of data.missing_information) {
        const paragraph = document.createElement("p");
        paragraph.className = "text-sm text-forest";
        paragraph.textContent = missing;
        warnings.append(paragraph);
      }
      result.hidden = false;
      applyButton.disabled = false;
      restoreButton.hidden = true;
      status.textContent = "Brouillon prêt en " + (data.elapsed_ms / 1000).toFixed(1) + " s. Relisez la proposition avant de l'appliquer.";
    } catch (error) {
      status.textContent = "Votre formulaire est conservé.";
      errors.textContent = error.name === "AbortError" ? "Le délai est dépassé. Vous pouvez compléter le formulaire vous-même." : error.message;
      errors.hidden = false;
    } finally {
      clearTimeout(timeout);
      prepareButton.disabled = false;
      result.removeAttribute("aria-busy");
    }
  });
  applyButton.addEventListener("click", () => {
    if (!prepared || !original) return;
    if (values().name !== original.name || values().description !== original.description) {
      errors.textContent = "Votre texte a changé depuis la préparation. Relancez l'assistant pour éviter d'écraser vos modifications.";
      errors.hidden = false;
      return;
    }
    if (prepared.product_name) recommendationForm.elements.product_name.value = prepared.product_name;
    errors.hidden = true;
    recommendationForm.elements.category.value = prepared.category;
    if (prepared.description) recommendationForm.elements.description.value = prepared.description;
    applyButton.disabled = true;
    restoreButton.hidden = false;
    status.textContent = "Proposition appliquée au formulaire. Vous pouvez la modifier puis l'envoyer pour validation.";
  });
  restoreButton.addEventListener("click", () => {
    if (!original) return;
    recommendationForm.elements.product_name.value = original.name;
    errors.hidden = true;
    recommendationForm.elements.description.value = original.description;
    recommendationForm.elements.category.value = original.category;
    status.textContent = "Votre texte initial a été rétabli.";
    restoreButton.hidden = true;
    applyButton.disabled = false;
  });
}
