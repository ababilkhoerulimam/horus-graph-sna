    function updateTopicHudDisplay(emergent) {
      const scopeNameEl = document.getElementById("hud-scope-name");
      const scopeCountEl = document.getElementById("hud-scope-count");
      const driverBadgeEl = document.getElementById("hud-topic-driver-badge");
      const driverNameEl = document.getElementById("hud-topic-driver-name");


      if (scopeNameEl) {
        scopeNameEl.textContent = (currentTopic === "ALL") ? "Semua Wacana Jaringan" : currentTopic;
      }
      if (scopeCountEl) {
        if (currentTopic === "ALL") {
          const counts = (allData.metadata && allData.metadata.counts) || {};
          const entityCount = (allData.nodes || []).length || counts.entities;
          scopeCountEl.textContent = `${formatCount(entityCount)} ${labelOf("entities", "Entitas")} | ${formatCount(counts.articles)} ${labelOf("articles", "Berita")}`;
        } else {
          scopeCountEl.textContent = `${currentActiveNodeSet.size} Entitas | ${activeTopicEdges.length} Relasi`;
        }
      }
      if (driverBadgeEl && driverNameEl) {
        if (currentTopic !== "ALL" && emergent && emergent.driverId) {
          driverBadgeEl.style.display = "block";
          driverNameEl.textContent = `${emergent.driverId} (Skor: ${emergent.score.toFixed(1)})`;
        } else {
          driverBadgeEl.style.display = "none";
        }
      }
    }

    document.getElementById("btn-reset-view").addEventListener("click", () => {
      if (isTracingPath) resetTracePath();
      lockedNode = null;
      deactivateNodes();
      currentTopic = "ALL";
      const topicSelect = document.getElementById("select-topic-filter");
      if (topicSelect) topicSelect.value = "ALL";
      const topicLabelEl = document.getElementById("topic-label");
      if (topicLabelEl) topicLabelEl.textContent = "Topik: Semua Wacana (Makro)";
      document.querySelectorAll(".dropdown-item").forEach(i => i.classList.remove("active"));
      const allItem = document.querySelector('.dropdown-item[data-val="ALL"]');
      if (allItem) allItem.classList.add("active");
      applyCombinedFilters();
    });

    document.getElementById("pill-info").addEventListener("click", () => {
      const modal = document.getElementById("modal-network-overview");
      if (modal) {
        modal.classList.add("open");
        loadSensitivity();
        loadInference(0);
      }
    });

    // Search HUD
    document.getElementById("hud-search").addEventListener("keyup", (e) => {
      const q = e.target.value.trim().toLowerCase();
      if (!q) { lockedNode = null; deactivateNodes(); document.getElementById("node-drawer").style.display = "none"; return; }
      const match = allData.nodes.find(n => n.label.toLowerCase().includes(q) || (n.display_label && n.display_label.toLowerCase().includes(q)));
      if (match) {
        selectAndInspectNode(match);
      }
    });

