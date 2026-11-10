/* Dashboard: charts (Chart.js) + GIS overview map (Leaflet). */
"use strict";

document.addEventListener("DOMContentLoaded", () => {
  /* ---- change trend line chart ---------------------------------------- */
  const trendCanvas = document.getElementById("trendChart");

  if (trendCanvas) {
    fetch("/api/dashboard/charts")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("chart data unavailable"))))
      .then((data) => {
        if (!data.trend.length) return;
        new Chart(trendCanvas, {
          type: "line",
          data: {
            labels: data.trend.map((t) => t.date),
            datasets: [{
              label: "Change %",
              data: data.trend.map((t) => t.change),
              borderColor: "#2ecc71",
              backgroundColor: "rgba(46,204,113,.15)",
              fill: true, tension: .3, pointRadius: 4,
              pointBackgroundColor: "#00d1c1",
            }],
          },
          options: {
            plugins: { legend: { labels: { color: "#8ba0b9" } } },
            scales: {
              x: { ticks: { color: "#8ba0b9", font: { size: 10 } }, grid: { color: "#1f3350" } },
              y: { ticks: { color: "#8ba0b9", callback: (v) => v + "%" }, grid: { color: "#1f3350" }, beginAtZero: true },
            },
          },
        });
      })
      .catch(() => {});
  }

  /* ---- priority doughnut ------------------------------------------------ */
  const priorityCanvas = document.getElementById("priorityChart");
  if (priorityCanvas) {
    fetch("/api/dashboard/charts")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("chart data unavailable"))))
      .then((data) => {
        if (!data.priorities.total) return;
        new Chart(priorityCanvas, {
          type: "doughnut",
          data: {
            labels: ["Low", "Medium", "High"],
            datasets: [{
              data: [data.priorities.low, data.priorities.medium, data.priorities.high],
              backgroundColor: ["#2ecc71", "#f1c40f", "#e74c3c"],
              borderColor: "#101d31", borderWidth: 3,
            }],
          },
          options: { plugins: { legend: { labels: { color: "#8ba0b9" } } }, cutout: "62%" },
        });
      })
      .catch(() => {});
  }

  /* ---- GIS overview map --------------------------------------------------- */
  const mapEl = document.getElementById("map-dashboard");
  if (mapEl && window.L) {
    const map = L.map(mapEl).setView([15.3, 75.1], 6);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);

    fetch("/api/map/parcels")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("map data unavailable"))))
      .then((data) => {
        const unlocated = document.getElementById("unlocated-list");
        unlocated.innerHTML = "";
        if (!data.features.length) {
          map.remove();
          mapEl.innerHTML =
            '<div class="empty-state" style="padding-top:170px;"><i class="bi bi-map"></i>' +
            "No georeferenced parcels to display yet.</div>";
        }
        data.features.forEach((f) => {
          const p = f.properties;
          const color = p.latest_priority === "high" ? "#e74c3c"
            : p.latest_priority === "medium" ? "#f1c40f" : "#2ecc71";
          L.circleMarker([f.geometry.coordinates[1], f.geometry.coordinates[0]], {
            radius: 9, color, fillColor: color, fillOpacity: .55, weight: 2,
          }).addTo(map).bindPopup(
            `<strong>${p.name}</strong><br>${p.location || "No location text"}<br>` +
            `Analyses: ${p.analysis_count}<br>` +
            (p.latest_change !== null ? `Latest change: ${p.latest_change}%` : "No analysis yet") +
            `<br><a href="/parcels/${p.id}">Open parcel →</a>`);
        });
        if (data.features.length) {
          map.fitBounds(L.latLngBounds(data.features.map(
            (f) => [f.geometry.coordinates[1], f.geometry.coordinates[0]])), { padding: [30, 30] });
        }
        if (!data.not_georeferenced.length) {
          unlocated.innerHTML = '<li class="text-muted">All parcels are georeferenced.</li>';
        } else {
          data.not_georeferenced.forEach((p) => {
            const li = document.createElement("li");
            li.className = "py-1";
            li.innerHTML = `<i class="bi bi-geo-slash text-muted me-1"></i>${p.name} — <em>not georeferenced</em>`;
            unlocated.appendChild(li);
          });
        }
      })
      .catch(() => {});
  }
});
