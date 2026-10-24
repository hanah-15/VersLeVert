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
if (guideForm && window.fetch) {
  guideForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = guideForm.querySelector("button");
    const status = guideForm.querySelector("[data-guide-status]");
    const results = document.querySelector("[data-guide-results]");
    button.disabled = true;
    guideForm.setAttribute("aria-busy", "true");
    status.textContent = "Le guide prépare vos suggestions…";
    results.hidden = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await fetch(guideForm.action || window.location.href, {
        method: "POST", body: new FormData(guideForm), credentials: "same-origin",
        headers: {"Accept": "application/json"}, signal: controller.signal,
      });
      if (response.redirected) {
        throw new Error("Votre session a expiré. Rechargez la page pour vous reconnecter.");
      }
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Le guide est momentanément indisponible.");
      results.replaceChildren();
      const heading = document.createElement("h2");
      heading.className = "font-heading text-2xl font-semibold text-forest";
      heading.textContent = "Vos pistes à explorer";
      const summary = document.createElement("p");
      summary.className = "break-words";
      summary.textContent = data.summary;
      results.append(heading, summary);
      for (const [key, label] of [["places", "Lieu"], ["products", "Produit recommandé"]]) {
        for (const item of data[key]) {
          const card = document.createElement("article");
          card.className = "rounded-lg-ui border border-olive bg-white p-6";
          const category = document.createElement("p");
          category.className = "text-xs font-bold uppercase text-forest";
          category.textContent = label;
          const title = document.createElement("h3");
          title.className = "mt-2 font-heading text-xl font-semibold text-forest";
          const link = document.createElement("a");
          link.className = "rounded underline focus:ring-4 focus:ring-sky";
          link.href = item.url;
          link.textContent = item.name;
          title.append(link);
          const reason = document.createElement("p");
          reason.className = "mt-2 break-words";
          reason.textContent = item.reason;
          card.append(category, title, reason);
          results.append(card);
        }
      }
      results.hidden = false;
      status.textContent = "Vos suggestions sont prêtes.";
    } catch (error) {
      status.textContent = error.name === "AbortError"
        ? "Le guide met trop de temps à répondre. Réessayez dans un instant."
        : error.message;
    } finally {
      clearTimeout(timeout);
      button.disabled = false;
      guideForm.removeAttribute("aria-busy");
    }
  });
}
