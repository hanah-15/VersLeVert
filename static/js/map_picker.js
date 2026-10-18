document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".map-picker").forEach(function (box) {
    var latInput = document.getElementById(box.dataset.latInput);
    var lonInput = document.getElementById(box.dataset.lonInput);
    var searchInput = box.querySelector(".map-search");
    var DEFAULT_CENTER = [36.8065, 10.1815]; // Tunis

    var hasPoint = latInput.value && lonInput.value;
    var start = hasPoint
      ? [parseFloat(latInput.value), parseFloat(lonInput.value)]
      : DEFAULT_CENTER;

    var map = L.map(box.querySelector(".map-canvas")).setView(start, hasPoint ? 14 : 8);
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
      {
      maxZoom: 19,
      attribution: "Tiles &copy; Esri"
      }
    ).addTo(map);

    var marker = null;
    function setPoint(lat, lon, zoom) {
      latInput.value = lat.toFixed(6);
      lonInput.value = lon.toFixed(6);
      if (marker) {
        marker.setLatLng([lat, lon]);
      } else {
        marker = L.marker([lat, lon], { draggable: true }).addTo(map);
        marker.on("dragend", function () {
          var p = marker.getLatLng();
          setPoint(p.lat, p.lng);
        });
      }
      if (zoom) map.setView([lat, lon], zoom);
    }

    if (hasPoint) setPoint(start[0], start[1]);
    map.on("click", function (e) { setPoint(e.latlng.lat, e.latlng.lng); });

    function search() {
      var q = searchInput.value.trim();
      if (!q) return;
      fetch("https://nominatim.openstreetmap.org/search?format=json&limit=1&q=" + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (!res.length) { alert("Adresse introuvable."); return; }
          setPoint(parseFloat(res[0].lat), parseFloat(res[0].lon), 15);
        })
        .catch(function () { alert("Recherche indisponible."); });
    }
    box.querySelector(".map-search-btn").addEventListener("click", search);
    searchInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); search(); }
    });

    box.querySelector(".map-locate-btn").addEventListener("click", function () {
      if (!navigator.geolocation) { alert("Géolocalisation non disponible."); return; }
      navigator.geolocation.getCurrentPosition(
        function (pos) { setPoint(pos.coords.latitude, pos.coords.longitude, 15); },
        function () { alert("Position refusée ou indisponible."); }
      );
    });
  });
});