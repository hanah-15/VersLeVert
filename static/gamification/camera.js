(() => {
  const openButton = document.getElementById("camera-open");
  const fallbackInput = document.getElementById("camera-fallback");
  const panel = document.getElementById("camera-panel");
  const video = document.getElementById("camera-video");
  const canvas = document.getElementById("camera-canvas");
  const captureButton = document.getElementById("camera-capture");
  const switchButton = document.getElementById("camera-switch");
  const closeButton = document.getElementById("camera-close");
  const errorBox = document.getElementById("camera-error");
  if (!openButton || !fallbackInput || !panel) return;

  let stream = null;
  let devices = [];
  let deviceIndex = 0;
  let selectedDeviceId = "";

  const stopStream = () => {
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
    if (video) video.srcObject = null;
  };
  const showError = (message) => {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  };
  const closeCamera = () => {
    stopStream();
    panel.classList.add("hidden");
  };
  const getCameraError = (error) => {
    if (error.name === "NotAllowedError") return "L'accès à la caméra est refusé. Autorisez-le dans les paramètres du navigateur, ou choisissez un fichier.";
    if (error.name === "NotFoundError") return "Aucune caméra détectée.";
    if (error.name === "NotReadableError") return "La caméra est utilisée par une autre application.";
    return "Impossible d'ouvrir la caméra. Vous pouvez choisir un fichier à la place.";
  };

  const startCamera = async (deviceId = "") => {
    stopStream();
    errorBox.classList.add("hidden");
    panel.classList.remove("hidden");
    const videoConstraints = deviceId
      ? { deviceId: { exact: deviceId }, width: { ideal: 1920 }, height: { ideal: 1080 } }
      : { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } };
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: videoConstraints, audio: false });
    } catch (error) {
      if (error.name === "OverconstrainedError" && !deviceId) {
        try {
          stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        } catch (retryError) {
          closeCamera();
          showError(getCameraError(retryError));
          return;
        }
      } else {
        closeCamera();
        showError(getCameraError(error));
        return;
      }
    }
    video.srcObject = stream;
    try {
      devices = (await navigator.mediaDevices.enumerateDevices()).filter((item) => item.kind === "videoinput");
      const currentId = stream.getVideoTracks()[0]?.getSettings().deviceId;
      deviceIndex = Math.max(0, devices.findIndex((item) => item.deviceId === currentId));
      switchButton.classList.toggle("hidden", devices.length < 2);
    } catch (_error) {
      switchButton.classList.add("hidden");
    }
  };

  if (window.isSecureContext && navigator.mediaDevices?.getUserMedia) {
    openButton.classList.remove("hidden");
    document.getElementById("camera-fallback-open")?.classList.add("hidden");
    openButton.addEventListener("click", () => startCamera(selectedDeviceId));
    captureButton.addEventListener("click", () => {
      if (!video.videoWidth || !video.videoHeight) return;
      const scale = Math.min(1, 2000 / Math.max(video.videoWidth, video.videoHeight));
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => {
        if (!blob) {
          showError("La photo n'a pas pu être préparée. Réessayez ou choisissez un fichier.");
          return;
        }
        const file = new File([blob], `preuve-${Date.now()}.jpg`, { type: "image/jpeg" });
        closeCamera();
        document.dispatchEvent(new CustomEvent("proof:file-selected", { detail: { file, source: "CAMERA" } }));
      }, "image/jpeg", 0.85);
    });
    switchButton.addEventListener("click", async () => {
      if (devices.length < 2) return;
      deviceIndex = (deviceIndex + 1) % devices.length;
      selectedDeviceId = devices[deviceIndex].deviceId;
      await startCamera(selectedDeviceId);
    });
    closeButton.addEventListener("click", closeCamera);
  }

  document.addEventListener("proof:reset", closeCamera);

  fallbackInput.addEventListener("change", () => {
    const file = fallbackInput.files?.[0];
    if (file) document.dispatchEvent(new CustomEvent("proof:file-selected", { detail: { file, source: "CAMERA" } }));
  });
  window.addEventListener("pagehide", stopStream);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopStream();
  });
})();
