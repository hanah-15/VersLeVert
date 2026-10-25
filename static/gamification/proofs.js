(() => {
  const form = document.getElementById("proof-upload-form");
  if (!form) return;
  const fileInput = document.getElementById("proof-file");
  const fallbackInput = document.getElementById("camera-fallback");
  const filePicker = document.getElementById("choose-proof-file");
  const fallbackPicker = document.getElementById("camera-fallback-open");
  const dropZone = document.getElementById("proof-drop-zone");
  const stepDocument = document.getElementById("proof-step-document");
  const previewPanel = document.getElementById("proof-preview-panel");
  const preview = document.getElementById("proof-preview");
  const fileName = document.getElementById("proof-file-name");
  const alertBox = document.getElementById("proof-alert");
  const sendButton = document.getElementById("proof-send");
  const progress = document.getElementById("proof-progress");
  const progressMessage = document.getElementById("proof-progress-message");
  let selectedFile = null;
  let source = "UPLOAD";
  let objectUrl = "";

  const showAlert = (message, variant = "error") => {
    alertBox.textContent = message;
    alertBox.className = `ui-alert ui-alert-${variant}`;
    alertBox.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  const hideAlert = () => {
    alertBox.textContent = "";
    alertBox.classList.add("hidden");
  };
  const csrfToken = () => form.querySelector("[name=csrfmiddlewaretoken]")?.value || "";

  const prepareFile = async (file) => {
    if (file.type === "application/pdf" || !file.type.startsWith("image/")) return file;
    try {
      const bitmap = await createImageBitmap(file);
      const scale = Math.min(1, 2000 / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(bitmap.width * scale);
      canvas.height = Math.round(bitmap.height * scale);
      canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      bitmap.close();
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
      if (!blob) return file;
      return new File([blob], file.name.replace(/\.[^.]+$/, ".jpg"), { type: "image/jpeg" });
    } catch (_error) {
      return file;
    }
  };

  const setFile = async (file, fileSource = "UPLOAD") => {
    if (!file) return;
    hideAlert();
    selectedFile = await prepareFile(file);
    source = fileSource;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(selectedFile);
    preview.src = objectUrl;
    preview.classList.toggle("hidden", selectedFile.type === "application/pdf");
    fileName.textContent = selectedFile.name;
    dropZone.classList.add("hidden");
    previewPanel.classList.remove("hidden");
  };

  document.querySelectorAll("[data-proof-card] input[name=proof_type]").forEach((radio) => {
    radio.addEventListener("change", () => {
      document.querySelectorAll("[data-proof-card]").forEach((card) => card.classList.remove("ring-2", "ring-palm"));
      radio.closest("[data-proof-card]").classList.add("ring-2", "ring-palm");
      stepDocument.classList.remove("hidden");
      stepDocument.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
  document.getElementById("proof-type-search").addEventListener("input", (event) => {
    const term = event.target.value.trim().toLocaleLowerCase();
    document.querySelectorAll("[data-proof-card]").forEach((card) => {
      card.classList.toggle("hidden", !card.dataset.search.includes(term));
    });
    document.querySelectorAll("[data-proof-category]").forEach((category) => {
      category.classList.toggle("hidden", !category.querySelector("[data-proof-card]:not(.hidden)"));
    });
  });
  filePicker.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => setFile(fileInput.files?.[0]));
  fallbackPicker.addEventListener("click", () => fallbackInput.click());
  dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropZone.classList.add("border-palm", "bg-palm/10");
  });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("border-palm", "bg-palm/10"));
  dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropZone.classList.remove("border-palm", "bg-palm/10");
    setFile(event.dataTransfer.files?.[0]);
  });
  document.addEventListener("proof:file-selected", (event) => setFile(event.detail.file, event.detail.source));
  document.getElementById("proof-retry-file").addEventListener("click", () => {
    selectedFile = null;
    previewPanel.classList.add("hidden");
    dropZone.classList.remove("hidden");
    fileInput.value = "";
    fallbackInput.value = "";
  });

  const pollStatus = async (statusUrl) => {
    const deadline = Date.now() + 60000;
    while (Date.now() < deadline) {
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
      const response = await fetch(statusUrl, { headers: { Accept: "application/json" }, credentials: "same-origin" });
      if (!response.ok) throw new Error("Impossible de récupérer l'état de votre preuve.");
      const data = await response.json();
      if (data.status === "APPROVED") {
        progressMessage.textContent = `Preuve validée : +${data.points_awarded || 0} points ajoutés à votre solde.`;
        progressMessage.className = "ui-alert ui-alert-success";
        return;
      }
      if (data.status === "NEEDS_REVIEW") {
        progressMessage.textContent = "Votre preuve est en cours de vérification par notre équipe.";
        progressMessage.className = "ui-alert ui-alert-info";
        return;
      }
      if (data.status === "REJECTED") {
        progressMessage.textContent = data.reason || "Votre preuve n'a pas pu être validée.";
        progressMessage.className = "ui-alert ui-alert-error";
        return;
      }
    }
    progressMessage.textContent = "L'analyse continue. Nous vous notifierons dès que le résultat sera prêt.";
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideAlert();
    const type = form.querySelector("input[name=proof_type]:checked");
    if (!type) return showAlert("Choisissez d'abord un type de preuve.");
    if (!selectedFile) return showAlert("Ajoutez une photo ou un document avant l'envoi.");
    sendButton.disabled = true;
    sendButton.textContent = "Envoi…";
    const body = new FormData();
    body.append("proof_type", type.value);
    body.append("file", selectedFile, selectedFile.name);
    body.append("source", source);
    try {
      const response = await fetch(form.dataset.uploadUrl, {
        method: "POST",
        body,
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrfToken(), Accept: "application/json" },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "L'envoi a échoué.");
      previewPanel.classList.add("hidden");
      stepDocument.classList.add("hidden");
      progress.classList.remove("hidden");
      await pollStatus(data.status_url);
    } catch (error) {
      showAlert(error.message);
    } finally {
      sendButton.disabled = false;
      sendButton.textContent = "Envoyer pour vérification";
    }
  });
})();
