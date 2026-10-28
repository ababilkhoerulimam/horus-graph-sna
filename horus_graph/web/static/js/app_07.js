    // -------------------------------------------------------------
    let currentColorMode = "type"; // "type" | "louvain" | "sentiment"
    let currentSizingMetric = "prominence"; // "prominence" | "volume" | "degree" | "betweenness" | "burt" | "uniform"

    // Palet komunitas berasal dari presentation.palette.
    function communityColors() {
      const palette = (PRESENTATION && PRESENTATION.palette) || {};
      return (palette.community && palette.community.length)
        ? palette.community
        : ["#38BDF8", "#10B981", "#F59E0B", "#EF4444", "#A855F7"];
    }
    // Palet komunitas baru tersedia setelah applyPresentation, jadi daftar ini
    // diisi di sana; versi const di posisi ini selalu memakai fallback 5 warna.
    let LOUVAIN_COLORS = communityColors();

    function getNodeColor(d) {
      if (d.is_ego) return ((PRESENTATION.palette || {}).ego) || "#F59E0B";
      if (currentColorMode === "type") {
        return colorForType(d.entity_type) || d.color || "#8A99AE";
      }
      if (currentColorMode === "louvain") {
        // Modulo mengikuti panjang palet, bukan angka 5: bundle dengan jumlah
        // komunitas lain tetap mendapat warna berbeda.
        const communityId = (d.louvain_community !== undefined && d.louvain_community !== null)
          ? d.louvain_community
          : d.cluster_id;
        // Tanpa id komunitas simpul diwarnai abu netral, bukan masuk komunitas 0.
        if (communityId === undefined || communityId === null) return "#475569";
        return LOUVAIN_COLORS[Math.abs(communityId) % LOUVAIN_COLORS.length];
      }
      if (currentColorMode === "sentiment") {
        // Tanpa lapisan sentimen semua simpul abu netral; tidak ada stance
        // yang bisa dipakai untuk mewarnai hijau atau merah.
        const sent = nodeSentiment(d);
        if (!sent) return "#475569";
        if (sent.stance > 0.15) return "#10B981";
        if (sent.stance < -0.15) return "#EF4444";
        return "#94A3B8";
      }
      return d.color || "#8A99AE";
    }

    // Satu skala ukuran untuk semua mode. Peringkatnya dihitung engine
    // (api/encoding.py) dari sebaran dataset itu sendiri, jadi tidak ada lagi
    // pembagi yang hanya benar untuk satu bundle. Yang dipilih di sini hanya
    // "peringkat yang mana", bukan "bagaimana menormalkan".
    const RADIUS_MIN = 6.0;
    const RADIUS_MAX = 26.0;
    // `prominence` adalah ringkasan komposit yang sudah dihitung engine
    // (degree + volume + betweenness berbobot); metrik lain adalah komponen
    // tunggal. Semuanya peringkat 0..1, jadi skalanya tetap satu.
    const SIZE_RANK_FIELDS = {
      prominence: "size_rank",
      degree: "rank_degree",
      betweenness: "rank_betweenness",
      burt: "rank_burt",
      volume: "rank_volume",
      uniform: null
    };

    // Peringkat yang benar-benar dikirim, atau null bila payload lama / metrik
    // uniform. Pemanggil yang butuh "tidak ada data" memakai ini; yang butuh
    // skala memakai sizeRank di bawah.
    function sizeRankOrNull(d) {
      const field = SIZE_RANK_FIELDS[currentSizingMetric];
      if (!field) return null;
      const value = d[field];
      if (typeof value !== "number" || !Number.isFinite(value)) return null;
      return Math.max(0.0, Math.min(1.0, value));
    }

    function sizeRank(d) {
      if (!SIZE_RANK_FIELDS[currentSizingMetric]) return null;
      // Peringkat yang tidak dikirim diperlakukan sebagai "paling kecil",
      // bukan rata-rata: mengarang posisi tengah menyembunyikan data hilang.
      const rank = sizeRankOrNull(d);
      if (rank === null) return 0.0;
      return rank;
    }

    // Tinggi kartu memakai peringkat yang sama dengan radius simpul, jadi
    // kartu besar benar-benar berarti simpul besar. Lebar tetap: lebar
    // menggeser jangkar ribbon, tinggi tidak.
    const CARD_MIN_H = 34.0;
    const CARD_MAX_H = 64.0;

    function cardHeight(d, fallback, minH = CARD_MIN_H, maxH = CARD_MAX_H) {
      const rank = sizeRankOrNull(d);
      // Tanpa peringkat (payload lama, metrik uniform) kartu tetap seperti
      // semula, bukan mengecil seragam karena field yang tidak ada.
      if (rank === null) return fallback;
      return minH + (maxH - minH) * rank;
    }

    function computeNodeRadius(d) {
      if (d.id === EGO_ID) return 28.0;
      const rank = sizeRank(d);
      if (rank === null) return 14.0;
      return RADIUS_MIN + (RADIUS_MAX - RADIUS_MIN) * rank;
    }

    function refreshNodeStyles() {
      nodeG.each(function(d) {
        const el = d3.select(this);
        const col = getNodeColor(d);
        const r = computeNodeRadius(d);
        d.node_radius = r;
        el.select("circle.main-circle")
          .attr("fill", col)
          .attr("r", r);
        el.select("circle.node-shield")
          .attr("r", r + 4);
        if (el.select("circle.subhub-accent-ring").node()) {
          el.select("circle.subhub-accent-ring")
            .attr("r", r + 4.5)
            .attr("stroke", col);
        }
      });
      // Radius baru hanya sampai ke layar kalau kanvas digambar ulang.
      graphView.refresh();
    }

    function applyEdgeFilters() {
      activeLayer.selectAll("g.edge-item")
        .style("display", d => shouldDisplayEdge(d) ? "block" : "none");
      updateEdgeCountBadge();
    }

    // Wiring Edge Category Dropdown
    const edgeCatBtn = document.getElementById("edge-cat-btn");
    const edgeCatMenu = document.getElementById("edge-cat-menu");
    if (edgeCatBtn && edgeCatMenu) {
      edgeCatBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = edgeCatMenu.classList.contains("show");
        document.querySelectorAll(".dropdown-menu").forEach(m => m.classList.remove("show", "open"));
        if (!isOpen) {
          edgeCatMenu.classList.add("show");
        }
      });
      edgeCatMenu.addEventListener("click", (e) => {
        e.stopPropagation(); // Keep menu open when toggling checkboxes
      });
    }

    // Kategori sisi dibangun dari data: label dari `category_label`, jumlah dari
    // hitungan nyata. Urutan tetap dari kategori yang dikenal engine.
    function populateEdgeCategoryMenu() {
      if (!edgeCatMenu) return;
      const counts = {};
      const labels = {};
      (allData.links || []).forEach(link => {
        const key = link.edge_category || "cooccurrence";
        counts[key] = (counts[key] || 0) + 1;
        if (!labels[key] && link.category_label && link.category_label !== key) {
          labels[key] = link.category_label;
        }
      });
      Object.keys(categoryFilters).forEach(key => {
        if (counts[key] === undefined) categoryFilters[key] = false;
      });

      edgeCatMenu.innerHTML = "";
      Object.keys(counts).forEach(key => {
        const checked = categoryFilters[key] !== false;
        categoryFilters[key] = checked;
        const label = document.createElement("label");
        const input = document.createElement("input");
        input.type = "checkbox";
        input.id = `chk-${key}`;
        input.checked = checked;
        input.addEventListener("change", event => {
          categoryFilters[key] = event.target.checked;
          applyEdgeFilters();
        });
        const text = document.createElement("span");
        text.textContent = ` ${labels[key] || key.replace(/_/g, " ")} (${counts[key]})`;
        label.appendChild(input);
        label.appendChild(text);
        edgeCatMenu.appendChild(label);
      });

      renderEdgeCategoryLegend(counts, labels);
    }

    // Legenda kategori sisi dibentuk dari kategori yang benar-benar ada di
    // bundle, dengan warna yang dipakai kanvas. Tidak ada valensi rekaan.
    function renderEdgeCategoryLegend(counts, labels) {
      const wrap = document.getElementById("canvas-legend-edge-categories");
      if (!wrap) return;
      wrap.innerHTML = "";
      Object.keys(counts).forEach(key => {
        const row = document.createElement("div");
        row.className = "canvas-legend-type";
        const dot = document.createElement("span");
        dot.className = "canvas-legend-type-dot";
        dot.style.background = getEdgeColor({ edge_category: key });
        const label = document.createElement("span");
        label.className = "canvas-legend-type-label";
        label.textContent = labels[key] || key.replace(/_/g, " ");
        const count = document.createElement("span");
        count.className = "canvas-legend-type-count";
        count.textContent = counts[key];
        row.append(dot, label, count);
        wrap.appendChild(row);
      });
    }

    // Wiring NPMI Slider
    const sliderNpmi = document.getElementById("slider-npmi");
    const valNpmi = document.getElementById("val-npmi");
    if (sliderNpmi) {
      sliderNpmi.addEventListener("input", (e) => {
        currentMinNpmi = parseFloat(e.target.value);
        if (valNpmi) valNpmi.textContent = currentMinNpmi.toFixed(2);
        applyEdgeFilters();
      });
    }

    // Wiring Media Lens Dropdown (Ontology Separation)
    function applyMediaLensFilter() {
      if (currentMode !== "actor_network" && currentMode !== "narrative_temporal") return;

      // Filter nodes visibility if hideMediaNodes is true
      nodeG.each(function(d) {
        const isMedia = isSourceNode(d);
        if (hideMediaNodes && isMedia) {
          d3.select(this).style("display", "none");
        } else {
          d3.select(this).style("display", "block");
        }
      });

      // If a specific source lens is selected
      if (currentMediaLens && currentMediaLens !== "ALL") {
        // Collect entities directly connected to this media node
        const coveredNodes = new Set();
        coveredNodes.add(currentMediaLens);

        activeLayer.selectAll("g.edge-item").each(function(d) {
          const s = getSourceId(d), t = getTargetId(d);
          if (s === currentMediaLens) coveredNodes.add(t);
          if (t === currentMediaLens) coveredNodes.add(s);
        });

        // Dim non-covered nodes and highlight covered ones
        nodeG.each(function(d) {
          const el = d3.select(this);
          if (hideMediaNodes && (isSourceNode(d))) {
            el.style("display", "none");
            return;
          }
          if (coveredNodes.has(d.id)) {
            el.attr("opacity", 1.0);
            el.select("circle.node-shield").attr("stroke", "#EA580C").attr("stroke-width", 2.5).attr("opacity", 0.9);
          } else {
            el.attr("opacity", 0.22);
            el.select("circle.node-shield").attr("stroke", "transparent").attr("opacity", 0);
          }
        });

        // Highlight edges connected to this media
        activeLayer.selectAll("g.edge-item").each(function(d) {
          const el = d3.select(this);
          const s = getSourceId(d), t = getTargetId(d);
          const isConnected = (s === currentMediaLens || t === currentMediaLens);
          if (isConnected) {
            el.style("display", "block");
            el.select(".edge-path").attr("stroke", "#EA580C").attr("stroke-width", 3.0).attr("opacity", 0.95);
          } else {
            el.style("display", shouldDisplayEdge(d) ? "block" : "none");
            el.select(".edge-path").attr("opacity", 0.08);
          }
        });
      } else {
        // Reset illumination
        nodeG.each(function(d) {
          const isMedia = isSourceNode(d);
          const el = d3.select(this);
          if (hideMediaNodes && isMedia) {
            el.style("display", "none");
          } else {
            el.style("display", "block").attr("opacity", 1.0);
            el.select("circle.node-shield").attr("stroke", "transparent").attr("opacity", 0);
          }
        });
        applyEdgeFilters();
      }
    }

    const mediaLensBtn = document.getElementById("media-lens-btn");
    const mediaLensMenu = document.getElementById("media-lens-menu");
    const mediaLensLabel = document.getElementById("media-lens-label");
    const chkHideMedia = document.getElementById("chk-hide-media-nodes");

    if (mediaLensBtn && mediaLensMenu) {
      mediaLensBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = mediaLensMenu.classList.contains("show");
        document.querySelectorAll(".dropdown-menu").forEach(m => m.classList.remove("show", "open"));
        if (!isOpen) {
          mediaLensMenu.classList.add("show");
        }
      });

      // Delegasi: butir outlet dibuat ulang setelah data dimuat.
      mediaLensMenu.addEventListener("click", (e) => {
        const item = e.target.closest(".dropdown-item");
        if (!item) return;
        e.stopPropagation();
        mediaLensMenu.querySelectorAll(".dropdown-item").forEach(i => i.classList.remove("active"));
        item.classList.add("active");
        currentMediaLens = item.dataset.mediaLens;
        const outletName = item.dataset.mediaLabel || currentMediaLens;
        if (mediaLensLabel) {
          mediaLensLabel.textContent = currentMediaLens === "ALL"
            ? "Lensa: Semua"
            : `Lensa: ${outletName}`;
        }
        mediaLensMenu.classList.remove("show", "open");
        applyMediaLensFilter();
      });
    }

    // Daftar outlet = simpul bertipe sumber, diurutkan menurut jumlah artikel.
    function populateMediaLensMenu() {
      if (!mediaLensMenu) return;
      const typeIds = sourceTypeIds();
      const wrap = document.getElementById("dropdown-media-lens-wrap");
      const sources = (allData.nodes || [])
        .filter(node => typeIds.includes(node.entity_type))
        .sort((a, b) => (b.articles || 0) - (a.articles || 0))
        .slice(0, 8);
      if (!sources.length) {
        if (wrap) wrap.style.display = "none";
        return;
      }
      if (wrap) wrap.style.display = "";
      mediaLensMenu.querySelectorAll(".dropdown-item:not([data-media-lens='ALL'])").forEach(el => el.remove());
      const divider = mediaLensMenu.querySelector(".dropdown-divider");
      sources.forEach(node => {
        const item = document.createElement("div");
        item.className = "dropdown-item";
        item.dataset.mediaLens = node.id;
        item.dataset.mediaLabel = node.label || node.id;
        item.textContent = node.label || node.id;
        mediaLensMenu.insertBefore(item, divider || null);
      });
    }

    if (chkHideMedia) {
      chkHideMedia.addEventListener("change", (e) => {
        hideMediaNodes = e.target.checked;
        applyMediaLensFilter();
      });
    }

    // Wiring Color Mode Dropdown
    const colorBtn = document.getElementById("color-mode-btn");
    const colorMenu = document.getElementById("color-mode-menu");
    const colorLabel = document.getElementById("color-mode-label");
    if (colorBtn && colorMenu) {
      colorBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = colorMenu.classList.contains("show");
        document.querySelectorAll(".dropdown-menu").forEach(m => m.classList.remove("show", "open"));
        if (!isOpen) {
          colorMenu.classList.add("show");
        }
      });
      colorMenu.querySelectorAll(".dropdown-item").forEach(item => {
        item.addEventListener("click", (e) => {
          e.stopPropagation();
          colorMenu.querySelectorAll(".dropdown-item").forEach(i => i.classList.remove("active"));
          item.classList.add("active");
          currentColorMode = item.dataset.colorMode;
          if (colorLabel) colorLabel.textContent = `Warna: ${currentColorMode === 'type' ? 'Tipe' : (currentColorMode === 'louvain' ? 'Louvain' : 'Sentimen')}`;
          colorMenu.classList.remove("show", "open");
          refreshNodeStyles();
        });
      });
    }

    // Wiring Sizing Mode Dropdown
    const sizeBtn = document.getElementById("node-sizing-btn");
    const sizeMenu = document.getElementById("node-sizing-menu");
    const sizeLabel = document.getElementById("node-sizing-label");
    if (sizeBtn && sizeMenu) {
      sizeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = sizeMenu.classList.contains("show");
        document.querySelectorAll(".dropdown-menu").forEach(m => m.classList.remove("show", "open"));
        if (!isOpen) {
          sizeMenu.classList.add("show");
        }
      });
      sizeMenu.querySelectorAll(".dropdown-item").forEach(item => {
        item.addEventListener("click", (e) => {
          e.stopPropagation();
          sizeMenu.querySelectorAll(".dropdown-item").forEach(i => i.classList.remove("active"));
          item.classList.add("active");
          currentSizingMetric = item.dataset.sizingMetric;
          const labelMap = { prominence: "Prominence", volume: "Volume", degree: "Degree", betweenness: "Betweenness", burt: "Burt ES", uniform: "Uniform" };
          if (sizeLabel) sizeLabel.textContent = `Ukuran: ${labelMap[currentSizingMetric] || 'Prominence'}`;
          sizeMenu.classList.remove("show", "open");
          refreshNodeStyles();
        });
      });
    }

    document.addEventListener("click", () => {
      document.querySelectorAll(".dropdown-menu").forEach(m => {
        m.classList.remove("show", "open");
      });
    });

    // -------------------------------------------------------------
    // Mode Switcher (Mode 01 / Mode 02 / Mode 03)
    // -------------------------------------------------------------
    const modeBtns = document.querySelectorAll(".mode-pill-btn");
    modeBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        const targetMode = btn.dataset.mode;
        switchAppMode(targetMode);
      });
    });

    function switchAppMode(mode) {
      // Mode tidak bisa dipakai sebelum data pertama selesai dimuat.
      if (!allData.nodes || !allData.nodes.length) return;
      currentMode = mode;
      modeBtns.forEach(b => b.classList.toggle("active", b.dataset.mode === mode));

      const tempCompareBar = document.getElementById("temporal-compare-bar");
      const npmiSliderGroup = document.getElementById("npmi-slider-group");
      const edgeCatDropdown = document.getElementById("dropdown-edge-categories-wrap") || document.getElementById("dropdown-edge-cat-wrap");

      if (mode === "actor_network") {
        if (tempCompareBar) tempCompareBar.style.display = "none";
        if (npmiSliderGroup) npmiSliderGroup.style.display = "flex";
        if (edgeCatDropdown) edgeCatDropdown.style.display = "block";
        bipartiteLayer.style("display", "none");
        nodeLayer.style("display", "block");
        activeLayer.style("display", "block");
        orbitLayer.style("display", "block");
        resetNodeTemporalDiff();
        applyEdgeFilters();
      } else if (mode === "topic_actor") {
        if (tempCompareBar) tempCompareBar.style.display = "none";
        if (npmiSliderGroup) npmiSliderGroup.style.display = "none";
        if (edgeCatDropdown) edgeCatDropdown.style.display = "none";
        nodeLayer.style("display", "none");
        activeLayer.style("display", "none");
        orbitLayer.style("display", "none");
        bipartiteLayer.style("display", "block");
        renderBipartiteTopicActor();
      } else if (mode === "narrative_temporal") {
        if (tempCompareBar) tempCompareBar.style.display = COMPARE_AVAILABLE ? "flex" : "none";
        if (npmiSliderGroup) npmiSliderGroup.style.display = "flex";
        if (edgeCatDropdown) edgeCatDropdown.style.display = "block";
        bipartiteLayer.style("display", "none");
        nodeLayer.style("display", "block");
        activeLayer.style("display", "block");
        orbitLayer.style("display", "block");
        if (COMPARE_AVAILABLE) runTemporalComparison();
      }
    }

    // -------------------------------------------------------------
    // Mode 02: D3 Bipartite Topic-Actor Renderer
