"use strict";

for (const form of document.querySelectorAll("[data-proximity-form]")) {
  const controls = form.querySelector("[data-area-controls]");
  const button = form.querySelector("[data-use-location]");
  const status = form.querySelector("[data-location-status]");
  const selection = form.querySelector("[data-location-selection]");
  const name = form.querySelector("[data-location-name]");
  const accuracy = form.querySelector("[data-location-accuracy]");
  let lookupVersion = 0;
  const clearOrigin = () => {
    lookupVersion += 1;
    form.elements.latitude.value = "";
    form.elements.longitude.value = "";
    form.elements.location_token.value = "";
    selection.hidden = true;
    accuracy.hidden = true;
    button.disabled = false;
  };
  form.querySelector("[data-clear-location]").addEventListener("click", () => {
    clearOrigin();
    form.elements.near_place.value = "";
    form.elements.radius.value = "";
    status.textContent = "Indiquez une ville ou utilisez votre position.";
  });
  form.elements.near_place.addEventListener("change", () => {
    clearOrigin();
    if (form.elements.near_place.value) {
      form.elements.city.value = "";
      name.textContent = form.elements.near_place.selectedOptions[0].textContent;
      selection.hidden = false;
      if (!form.elements.radius.value) form.elements.radius.value = "10";
      status.textContent = "Choisissez une distance, puis lancez la recherche.";
    } else {
      form.elements.radius.value = "";
      status.textContent = "Choisissez un lieu ou utilisez votre position.";
    }
  });
  form.elements.city.addEventListener("input", () => {
    clearOrigin();
    form.elements.near_place.value = "";
    form.elements.radius.value = "";
    status.textContent = "Recherche dans la ville ou le quartier indiqué.";
  });
  button.addEventListener("click", () => {
    if (!navigator.geolocation) {
      status.textContent = "Position indisponible. Indiquez une ville ou choisissez un lieu.";
      return;
    }
    const previousRadius = form.elements.radius.value;
    clearOrigin();
    form.elements.near_place.value = "";
    form.elements.radius.value = "";
    const version = ++lookupVersion;
    button.disabled = true;
    status.textContent = "Recherche de votre position…";
    navigator.geolocation.getCurrentPosition(async (position) => {
      if (version !== lookupVersion) return;
      form.elements.latitude.value = position.coords.latitude.toFixed(6);
      form.elements.longitude.value = position.coords.longitude.toFixed(6);
      form.elements.location_token.value = "";
      form.elements.near_place.value = "";
      form.elements.city.value = "";
      if (!form.elements.radius.value) form.elements.radius.value = previousRadius || "10";
      name.textContent = "Ma position";
      selection.hidden = false;
      accuracy.hidden = !(position.coords.accuracy > 200);
      if (!accuracy.hidden) accuracy.textContent = "Position approximative : précision d'environ " + (position.coords.accuracy / 1000).toFixed(1) + " km.";
      status.textContent = "Position repérée. Recherche du nom du quartier…";
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 7000);
      try {
        const body = new FormData();
        body.set("latitude", form.elements.latitude.value);
        body.set("longitude", form.elements.longitude.value);
        const response = await fetch(controls.dataset.locationEndpoint, {
          method: "POST", body, credentials: "same-origin",
          headers: {"Accept": "application/json", "X-CSRFToken": controls.dataset.csrfToken},
          signal: controller.signal,
        });
        if (!response.ok || response.redirected) throw new Error("No area label");
        const data = await response.json();
        if (version !== lookupVersion) return;
        name.textContent = data.label;
        form.elements.location_token.value = data.location_token;
        status.textContent = "Quartier repéré : " + data.label + ". Choisissez une distance, puis lancez la recherche.";
      } catch {
        if (version === lookupVersion) status.textContent = "Votre position est repérée. Le nom du quartier est indisponible ; vous pouvez choisir une distance et rechercher.";
      } finally {
        clearTimeout(timeout);
        if (version === lookupVersion) button.disabled = false;
      }
      // Let the user choose the radius before submitting; never auto-search.
    }, () => {
      if (version !== lookupVersion) return;
      button.disabled = false;
      status.textContent = "Position indisponible. Autorisez la localisation dans votre navigateur ou indiquez une ville.";
    }, {enableHighAccuracy: true, timeout: 15000, maximumAge: 60000});
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
  const location = recommendationForm.elements.purchase_location;
  let prepared = null;
  let original = null;
  let undoFields = {};
  const values = () => ({name: recommendationForm.elements.product_name.value, description: review.value});
  const unchanged = (snapshot) => snapshot && values().name === snapshot.name && values().description === snapshot.description;
  location.addEventListener("input", () => { recommendationForm.elements.place.value = ""; });
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
    status.textContent = "Reformulation de votre avis et recherche du lieu mentionné…";
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
      const suggestedLocation = data.purchase_location || "";
      if ((!data.description || data.description.trim() === source.description.trim()) && !suggestedLocation) {
        status.textContent = "Votre texte est conservé. Vous pouvez le modifier ou l'envoyer pour validation.";
        return;
      }
      prepared = data;
      original = source;
      recommendationForm.querySelector("[data-prepared-description]").textContent = data.description || source.description;
      const notes = {
        health_claim: "Les bénéfices pour la santé restent à préciser.",
        certification: "Les labels et certifications restent à vérifier.",
        quantified_impact: "Les chiffres d'impact nécessitent une source.",
        absolute_eco_claim: "Les impressions sur l'environnement sont formulées avec prudence.",
      };
      const warnings = recommendationForm.querySelector("[data-preparation-warnings]");
      warnings.textContent = [...new Set(data.warnings.map(w => notes[w.issue]).filter(Boolean))].join(" ");
      warnings.hidden = !warnings.textContent;
      const locationSection = recommendationForm.querySelector("[data-prepared-location-section]");
      locationSection.hidden = !suggestedLocation;
      recommendationForm.querySelector("[data-prepared-location]").textContent = suggestedLocation;
      recommendationForm.querySelector("[data-prepared-location-note]").textContent = location.value.trim()
        ? "Le lieu que vous avez déjà saisi sera conservé."
        : "Ce lieu sera ajouté au champ « Où le trouver ? » en utilisant la suggestion.";
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
    undoFields = {};
    const setField = (key, next) => {
      const field = recommendationForm.elements[key];
      if (field.value === next) return;
      undoFields[key] = {before: field.value, after: next};
      field.value = next;
    };
    if (!recommendationForm.elements.product_name.value && prepared.product_name) setField("product_name", prepared.product_name);
    if (!recommendationForm.elements.category.value) setField("category", prepared.category);
    if (!location.value.trim() && prepared.purchase_location) {
      setField("purchase_location", prepared.purchase_location);
      setField("place", "");
    }
    if (prepared.description) setField("description", prepared.description);
    errors.hidden = true;
    result.hidden = true;
    restoreButton.hidden = Object.keys(undoFields).length === 0;
    status.textContent = "Suggestion appliquée. Vous pouvez encore modifier votre avis et le lieu.";
    review.focus();
  });
  dismissButton.addEventListener("click", () => {
    result.hidden = true;
    status.textContent = "Votre texte est conservé.";
    review.focus();
  });
  restoreButton.addEventListener("click", () => {
    for (const [key, previous] of Object.entries(undoFields)) {
      const field = recommendationForm.elements[key];
      if (field.value === previous.after) field.value = previous.before;
    }
    undoFields = {};
    status.textContent = "Les changements de l'assistant sont annulés ; vos dernières saisies sont conservées.";
    restoreButton.hidden = true;
    review.focus();
  });
}
