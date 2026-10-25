(() => {
  const form = document.getElementById("proof-upload-form");
  if (!form) return;
  const fileInput = document.getElementById("proof-file");
  const fallbackInput = document.getElementById("camera-fallback");
  const filePicker = document.getElementById("choose-proof-file");
  const fallbackPicker = document.getElementById("camera-fallback-open");
  const dropZone = document.getElementById("proof-drop-zone");
  const flowModal = document.getElementById("proof-flow-modal");
  const modalClose = document.getElementById("proof-modal-close");
  const progressClose = document.getElementById("proof-progress-close");
  const stepDocument = document.getElementById("proof-step-document");
  const previewPanel = document.getElementById("proof-preview-panel");
  const preview = document.getElementById("proof-preview");
  const fileName = document.getElementById("proof-file-name");
  const alertBox = document.getElementById("proof-alert");
  const sendButton = document.getElementById("proof-send");
  const progress = document.getElementById("proof-progress");
  const progressMessage = document.getElementById("proof-progress-message");
  const progressSteps = document.querySelectorAll("[data-proof-stage]");
  const aiResult = document.getElementById("proof-ai-result");
  const modalTitle = document.getElementById("proof-modal-title");
  const selectedPoints = document.getElementById("proof-selected-points");
  const changeType = document.getElementById("proof-change-type");
  const modalSteps = document.querySelectorAll("[data-modal-step]");
  const firstProofCard = document.querySelector("[data-proof-card] input[name=proof_type]");
  let selectedFile = null;
  let source = "UPLOAD";
  let objectUrl = "";
  let isSubmitting = false;

  const clearSelectedFile = () => {
    selectedFile = null;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = "";
    preview.removeAttribute("src");
    previewPanel.classList.add("hidden");
    dropZone.classList.remove("hidden");
    fileInput.value = "";
    fallbackInput.value = "";
  };

  const setModalStep = (current) => {
    modalSteps.forEach((step) => {
      const isCurrent = step.dataset.modalStep === current;
      const isDone = current === "analysis"
        ? step.dataset.modalStep === "type" || step.dataset.modalStep === "document"
        : step.dataset.modalStep === "type";
      step.classList.toggle("is-current", isCurrent);
      step.classList.toggle("is-done", isDone);
      if (isCurrent) step.setAttribute("aria-current", "step");
      else step.removeAttribute("aria-current");
    });
  };

  const resetProgressStages = () => {
    progressSteps.forEach((step) => {
      step.dataset.state = "pending";
    });
  };

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
      clearSelectedFile();
      document.getElementById("proof-selected-label").textContent = radio.dataset.proofLabel;
      document.getElementById("proof-selected-tip").textContent = radio.dataset.proofTips;
      selectedPoints.textContent = radio.dataset.proofPoints;
      progress.classList.add("hidden");
      document.getElementById("proof-progress-message").textContent =
        "Votre document est en cours de traitement.";
      document.getElementById("proof-progress-message").className = "mt-2 text-sm text-carbon";
      aiResult.classList.add("hidden");
      stepDocument.classList.remove("hidden");
      resetProgressStages();
      setModalStep("document");
      modalTitle.textContent = "Ajoutez votre justificatif";
      flowModal.showModal();
    });
  });
  modalClose.addEventListener("click", () => {
    if (!isSubmitting) flowModal.close();
  });
  progressClose.addEventListener("click", () => {
    if (!isSubmitting) flowModal.close();
  });
  changeType.addEventListener("click", () => {
    if (isSubmitting) return;
    flowModal.close();
    window.setTimeout(() => firstProofCard?.focus(), 0);
  });
  flowModal.addEventListener("cancel", (event) => {
    if (isSubmitting) event.preventDefault();
  });
  flowModal.addEventListener("close", () => {
    if (isSubmitting) return;
    clearSelectedFile();
    document.dispatchEvent(new CustomEvent("proof:reset"));
    form.querySelectorAll("input[name=proof_type]").forEach((radio) => {
      radio.checked = false;
      radio.closest("[data-proof-card]").classList.remove("ring-2", "ring-palm");
    });
    stepDocument.classList.remove("hidden");
    progress.classList.add("hidden");
    resetProgressStages();
    setModalStep("document");
    modalTitle.textContent = "Ajoutez votre justificatif";
    hideAlert();
  });
  document.getElementById("proof-type-search").addEventListener("input", (event) => {
    const term = event.target.value.trim().toLocaleLowerCase();
    document.querySelectorAll("[data-proof-card]").forEach((card) => {
      card.classList.toggle("hidden", !card.dataset.search.includes(term));
    });
    document.querySelectorAll("[data-proof-category]").forEach((category) => {
      const hasVisibleCards = Boolean(category.querySelector("[data-proof-card]:not(.hidden)"));
      category.classList.toggle("hidden", !hasVisibleCards);
      category.open = hasVisibleCards;
    });
  });
  filePicker.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => setFile(fileInput.files?.[0]));
  fallbackPicker.addEventListener("click", () => fallbackInput.click());
  dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragover");
  });
  dropZone.addEventListener("dragenter", (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragover");
  });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("is-dragover"));
  dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragover");
    setFile(event.dataTransfer.files?.[0]);
  });
  dropZone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      fileInput.click();
    }
  });
  document.addEventListener("proof:file-selected", (event) => setFile(event.detail.file, event.detail.source));
  document.getElementById("proof-retry-file").addEventListener("click", () => {
    clearSelectedFile();
  });

  const pollStatus = async (statusUrl) => {
    const deadline = Date.now() + 90000;
    while (Date.now() < deadline) {
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
      const response = await fetch(statusUrl, { headers: { Accept: "application/json" }, credentials: "same-origin" });
      if (!response.ok) throw new Error("Impossible de récupérer l'état de votre preuve.");
      const data = await response.json();
      const stage = data.status === "PENDING"
        ? "upload"
        : data.status === "PROCESSING"
          ? "ai"
          : "result";
      progressSteps.forEach((step) => {
        const stageOrder = ["upload", "ai", "result"];
        const currentIndex = stageOrder.indexOf(stage);
        const stepIndex = stageOrder.indexOf(step.dataset.proofStage);
        step.dataset.state = data.status === "REJECTED" && stage === "result"
          ? stepIndex === currentIndex ? "error" : stepIndex < currentIndex ? "done" : "pending"
          : stepIndex < currentIndex ? "done" : stepIndex === currentIndex ? "active" : "pending";
      });
      if (data.provider && data.status !== "PROCESSING" && data.status !== "PENDING") {
        aiResult.classList.remove("hidden");
        ["date", "amount", "merchant"].forEach((field) => {
          aiResult.querySelector(`[data-ai-field="${field}"]`).textContent = data.extracted[field] || "Non détecté";
        });
        aiResult.querySelector('[data-ai-field="transcript"]').textContent = data.transcript || "Aucun texte reconnu.";
      }
      if (data.status === "APPROVED") {
        progressSteps.forEach((step) => {
          step.dataset.state = "done";
        });
        progressMessage.textContent = `Preuve validée : +${data.points_awarded || 0} points ajoutés à votre solde.`;
        progressMessage.className = "ui-alert ui-alert-success";
        return;
      }
      if (data.status === "REJECTED") {
        progressSteps.forEach((step) => {
          step.dataset.state = step.dataset.proofStage === "result" ? "error" : "done";
        });
        progressMessage.textContent = data.reason || "Votre preuve n'a pas pu être validée.";
        progressMessage.className = "ui-alert ui-alert-error";
        return;
      }
    }
    progressMessage.textContent = "Le traitement prend plus de temps que prévu. Votre preuve est enregistrée ; une notification apparaîtra dès qu'un résultat ou une décision sera disponible.";
    progressSteps.forEach((step) => {
      if (step.dataset.proofStage === "result") step.dataset.state = "active";
    });
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideAlert();
    const type = form.querySelector("input[name=proof_type]:checked");
    if (!type) return showAlert("Choisissez d'abord un type de preuve.");
    if (!selectedFile) return showAlert("Ajoutez une photo ou un document avant l'envoi.");
    isSubmitting = true;
    modalClose.disabled = true;
    progressClose.disabled = true;
    sendButton.disabled = true;
    sendButton.textContent = "Envoi…";
    const body = new FormData();
    body.append("proof_type", type.value);
    body.append("file", selectedFile, selectedFile.name);
    body.append("source", source);
    const consent = document.getElementById("proof-ai-consent");
    if (consent?.checked) body.append("ai_consent", "on");
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
      setModalStep("analysis");
      modalTitle.textContent = "Analyse de votre preuve";
      await pollStatus(data.status_url);
    } catch (error) {
      showAlert(error.message);
    } finally {
      isSubmitting = false;
      modalClose.disabled = false;
      progressClose.disabled = false;
      sendButton.disabled = false;
      sendButton.textContent = "Envoyer pour analyse";
    }
  });
})();
