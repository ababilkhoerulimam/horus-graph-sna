    // Embedded Active Dataset
    let allData = { nodes: [], links: [], metadata: {} };  // diisi dari /api/bootstrap
    // Artefak pendamping: cakupan korpus dan indeks entitas. Tidak ada salinan
    // statis di HTML, jadi angka di UI tidak bisa menyimpang dari hasil build.
    let CORPUS_COVERAGE = null;
    let ENTITY_INDEX = [];
    let ENTITY_INDEX_META = null;
    // Metadata tampilan dari bundle. Nama domain, warna, dan narasi hanya
    // boleh datang dari sini.
    let PRESENTATION = {};
    let EGO_ID = null;
    let BOOTSTRAP = null;

    
    // -------------------------------------------------------------
    // Full 100% Artifact Datasets
    // -------------------------------------------------------------

    // State Variables
    let isTracingPath = false;
    let lockedNode = null;
    let currentTopic = "ALL";
    let alternativePaths = [];
    let activeTopicEdges = allData.links;
    let currentActiveNodeSet = new Set();
    const isDarkMode = true;

    // Helper functions for link endpoints
    const getSourceId = l => typeof l.source === "object" ? l.source.id : l.source;
    const getTargetId = l => typeof l.target === "object" ? l.target.id : l.target;

    // Cincin orbit berasal dari metadata (entities.ring_level) dan labelnya dari
    // presentation.orbit_tiers. Dataset tanpa pusat tidak memaksa cincin 0.
    const ORBIT_RADII = [0, 185, 360, 540];
    allData.nodes.forEach(n => {
      const raw = n.ring_level;
      const parsed = (raw === null || raw === undefined || raw === "") ? null : Number(raw);
      const tier = Number.isFinite(parsed) ? parsed : (EGO_ID && n.id === EGO_ID ? 0 : null);
      if (tier === null) {
        n.target_r = null;
        n.ring_tier = null;
        n.orbit_label = n.orbit_label || "";
        return;
      }
      n.target_r = ORBIT_RADII[tier] != null ? ORBIT_RADII[tier] : 185 + (tier - 1) * 180;
      n.ring_tier = tier;
      n.orbit_label = n.orbit_label
        || (PRESENTATION.orbit_tiers || [])[tier]
        || (tier === 0 ? "Pusat" : `Cincin ${tier}`);
    });

    // Semantic Entity Mappings for Sub-Topic Exploration
    // Keanggotaan topik dari artefak bipartite hasil hitung korpus (P5.4).
    let TOPIC_NODE_MAP = {};

    // Keanggotaan topik datang dari /api/bootstrap (bipartit topik-aktor).
    function buildTopicMap(topics) {
      const map = {};
      (topics || []).forEach(topic => { map[topic.id] = new Set(topic.members || []); });
      return map;
    }

    // Topic Networks: Generate Induced Subgraphs per Sub-Topic
    let topicNetworks = { "ALL": [] };
    function buildTopicNetworks() {
      const links = allData.links;
      const result = { "ALL": links };

      Object.keys(TOPIC_NODE_MAP).forEach(topic => {
        const allowedIds = new Set(TOPIC_NODE_MAP[topic]);
        if (EGO_ID) allowedIds.add(EGO_ID); // simpul pusat selalu ikut, bila ada

        result[topic] = links.filter(l => {
          const s = getSourceId(l), t = getTargetId(l);
          return allowedIds.has(s) && allowedIds.has(t);
        });
      });

      topicNetworks = result;
    }

    // Warna per tipe berasal dari presentation; kode tidak mengenal nama tipe.
    function colorForType(type) {
      const types = (PRESENTATION && PRESENTATION.entity_types) || [];
      const found = types.find(item => item.id === type);
      return (found && found.color) || "#8A99AE";
    }

    function typeLabel(type) {
      const types = (PRESENTATION && PRESENTATION.entity_types) || [];
      const found = types.find(item => item.id === type);
      return (found && found.label) || type || "";
    }

    // D3 Canvas
    const svg = d3.select("#network-svg");
    const container = svg.append("g").attr("class", "static-root");

        // -------------------------------------------------------------
    // RADAR VIEWPORT Minimap Live Tracking
    // -------------------------------------------------------------
    const minimapSvg = d3.select("#minimap-svg");
    const minimapNodesG = d3.select("#minimap-nodes");
    const minimapBox = d3.select("#minimap-viewport-box");

    // Add subtle background radar rings into minimap
    const mmRingsG = minimapSvg.insert("g", "#minimap-nodes").attr("class", "mm-rings");
    [220, 440, 660, 820].forEach(r => {
      mmRingsG.append("circle")
        .attr("cx", 0)
        .attr("cy", 0)
        .attr("r", r)
        .attr("fill", "none")
        .attr("stroke", "rgba(148, 163, 184, 0.25)")
        .attr("stroke-width", "2.5px")
        .attr("stroke-dasharray", "8, 8");
    });

    minimapSvg
      .style("cursor", "crosshair")
      .on("click", function(event) {
        const [targetX, targetY] = d3.pointer(event, this);
        const currentTransform = d3.zoomTransform(svg.node());
        const currentScale = currentTransform.k || 0.92;

        svg.transition()
          .duration(500)
          .ease(d3.easeCubicOut)
          .call(
            zoom.transform,
            d3.zoomIdentity
              .translate(-targetX * currentScale, -targetY * currentScale)
              .scale(currentScale)
          );
      });

    function renderMinimapNodes() {
      if (!minimapNodesG || !minimapNodesG.node()) return;
      minimapNodesG.selectAll("circle.mm-dot")
        .data(allData.nodes, d => d.id)
        .join("circle")
        .attr("class", "mm-dot")
        .attr("cx", d => d.x)
        .attr("cy", d => d.y)
        .attr("r", d => d.id === EGO_ID ? 22 : 11)
        .attr("fill", d => d.id === EGO_ID ? "#A855F7" : (d.color || "#8A99AE"))
        .attr("stroke", "#FFFFFF")
        .attr("stroke-width", d => d.id === EGO_ID ? 3.5 : 2.0)
        .attr("opacity", 0.95);
    }

    function updateMinimapDots(selectedYear) {
      if (!minimapNodesG || !minimapNodesG.node()) return;
      minimapNodesG.selectAll("circle.mm-dot")
        .attr("opacity", d => {
          if (selectedYear === null || selectedYear === undefined) return 0.95;
          const isActive = d.id === EGO_ID ||
            (d.active_years && d.active_years.includes(selectedYear)) ||
            (d.first_seen_year && d.first_seen_year <= selectedYear);
          return isActive ? 0.95 : 0.12;
        });
    }

    function updateMinimapBox(transform) {
      if (!minimapBox || !minimapBox.node()) return;
      const k = transform.k || 0.92;
      const tx = transform.x || 0;
      const ty = transform.y || 0;

      const svgNode = svg.node();
      const svgRect = svgNode ? svgNode.getBoundingClientRect() : { width: 1600, height: 1200 };
      const aspect = (svgRect.width && svgRect.height) ? (svgRect.width / svgRect.height) : (4600 / 3800);

      // Basis rentang viewBox kanvas utama (-2300 s/d 2300, -1900 s/d 1900)
      const baseSpanY = 3800;
      const baseSpanX = baseSpanY * aspect;

      const boxWidth = Math.max(120, baseSpanX / k);
      const boxHeight = Math.max(90, baseSpanY / k);

      // Pusat kamera (0,0) diubah oleh translate (-tx, -ty)
      const boxX = (-tx / k) - (boxWidth / 2);
      const boxY = (-ty / k) - (boxHeight / 2);

      minimapBox
        .attr("x", boxX)
        .attr("y", boxY)
        .attr("width", boxWidth)
        .attr("height", boxHeight);
    }

    // -------------------------------------------------------------
    // Dynamic Timeline Slider & Multi-Epoch Longitudinal SNA Filter
    // -------------------------------------------------------------
    // Daftar tahun dan narasi epos berasal dari bundle, bukan dari kode.
    function timelineYears() {
      const range = (BOOTSTRAP && BOOTSTRAP.dataset && BOOTSTRAP.dataset.date_range) || [];
      if (range.length !== 2) return [null];
      const start = parseInt(String(range[0]).slice(0, 4), 10);
      const end = parseInt(String(range[1]).slice(0, 4), 10);
      const years = [];
      for (let year = start; year <= end; year += 1) years.push(year);
      return years.concat([null]);
    }

    function milestoneFor(year) {
      const narratives = (PRESENTATION && PRESENTATION.epoch_narratives) || {};
      if (year === null || year === undefined) {
        return narratives.all || "";
      }
      return narratives[String(year)] || "";
    }

    // Tidak ada DEFAULT_TEMPORAL_EPOCHS: epos hanya dari data/temporal_slices.json (P5.2).

    let temporalEpochsData = null;
    function applyTemporalData(epochs) {
      temporalEpochsData = {};
      (epochs || []).forEach(ep => { temporalEpochsData[ep.id] = ep; });
      if (!epochs || !epochs.length) temporalEpochsData = null;
      renderEpochPills(epochs || []);
      renderEpochSelects(epochs || []);
    }

    // Dua pemilih epos di bilah komparasi ikut bundle. Sebelumnya keduanya
    // berisi tiga opsi tulisan tangan, sehingga bundle dengan jumlah epos lain
    // membandingkan irisan waktu yang tidak ada.
    // Dua epos nyata diperlukan sebelum bilah komparasi boleh tampil. Flag ini
    // dipakai juga oleh switchAppMode, yang dulu menampilkan bilah tanpa syarat.
    let COMPARE_AVAILABLE = false;

    function renderEpochSelects(epochs) {
      const baseSel = document.getElementById("sel-compare-baseline");
      const tgtSel = document.getElementById("sel-compare-target");
      if (!baseSel || !tgtSel) return;
      const usable = epochs.filter(ep => ep && ep.id);
      const optionFor = ep => {
        const start = ep.start_year == null ? "" : String(ep.start_year);
        const end = ep.end_year == null ? "" : String(ep.end_year);
        const label = ep.label || ep.id;
        // Sebagian label sudah memuat rentang tahunnya sendiri; menambahkannya
        // lagi menghasilkan "(2021-2022) (2021–2022)".
        const hasSpan = start && end && label.includes(start) && label.includes(end);
        const span = (start && end && !hasSpan) ? ` (${start}\u2013${end})` : "";
        return { value: ep.id, text: label + span };
      };
      [baseSel, tgtSel].forEach(sel => { sel.innerHTML = ""; });
      // Perbandingan butuh dua irisan waktu nyata. `all_time` adalah agregat,
      // bukan epos, jadi tidak dihitung: satu epos + all_time tetap berarti
      // membandingkan sesuatu dengan dirinya sendiri yang diperbesar.
      const realEpochs = usable.filter(ep => ep.id !== "all_time");
      COMPARE_AVAILABLE = realEpochs.length >= 2;
      if (!COMPARE_AVAILABLE) {
        document.getElementById("temporal-compare-bar").style.display = "none";
        return;
      }
      usable.forEach(ep => {
        const opt = optionFor(ep);
        [baseSel, tgtSel].forEach(sel => {
          const o = document.createElement("option");
          o.value = opt.value;
          o.textContent = opt.text;
          sel.appendChild(o);
        });
      });
      // Dasar = irisan paling awal, target = irisan paling akhir yang bukan
      // agregat all-time.
      baseSel.value = realEpochs[0].id;
      tgtSel.value = realEpochs[realEpochs.length - 1].id;
    }

    // Pil epos dibentuk dari data: jumlah, urutan, dan narasinya ikut bundle.
    function renderEpochPills(epochs) {
      const wrap = document.getElementById("epoch-pills-wrap");
      if (!wrap) return;
      const idleStyle = "background:transparent; border:1px solid rgba(255,255,255,0.15); color:#94A3B8; font-size:11px; font-weight:700; padding:2px 6px; border-radius:4px; cursor:pointer;";
      wrap.innerHTML = "";
      epochs.forEach(ep => {
        const btn = document.createElement("button");
        btn.className = "epoch-pill-btn";
        btn.dataset.epoch = ep.id;
        btn.style.cssText = idleStyle;
        const start = ep.start_year == null ? "" : String(ep.start_year).slice(-2);
        const end = ep.end_year == null ? "" : String(ep.end_year).slice(-2);
        const isAll = ep.id === "all_time";
        btn.textContent = isAll ? "Semua" : (start && end ? `${start}-${end}` : (ep.label || ep.id));
        btn.title = ep.label || ep.id;
        wrap.appendChild(btn);
      });
      const active = epochs.some(ep => ep.id === "all_time")
        ? "all_time"
        : (epochs[0] ? epochs[0].id : null);
      if (active) updatePillsState(active);
    }

    function applyCorpusCoverage(coverage) {
      CORPUS_COVERAGE = coverage || null;
    }

    function applyEntityIndex(entities) {
      ENTITY_INDEX = Array.isArray(entities) ? entities : [];
      const input = document.getElementById("hud-search");
      if (input) {
        input.placeholder = ENTITY_INDEX.length
          ? `Cari ${ENTITY_INDEX.length} entitas kanonik...`
          : "Indeks entitas belum tersedia";
      }
    }

    const timelineSlider = document.getElementById("timeline-slider");
    const timelineLabel = document.getElementById("timeline-label");
    const timelinePlayBtn = document.getElementById("btn-timeline-play");
    const timelineMilestoneBanner = document.getElementById("timeline-milestone-banner");
    let timelineInterval = null;

    function updatePillsState(epochKey) {
      document.querySelectorAll(".epoch-pill-btn").forEach(btn => {
        const isCurrent = btn.getAttribute("data-epoch") === epochKey;
        btn.classList.toggle("active", isCurrent);
        btn.style.background = isCurrent ? "rgba(56,189,248,0.2)" : "transparent";
        btn.style.borderColor = isCurrent ? "rgba(56,189,248,0.4)" : "rgba(255,255,255,0.15)";
        btn.style.color = isCurrent ? "#38BDF8" : "#94A3B8";
      });
    }

    function applyEpochFilter(epochKey) {
      stopTimelinePlayback();
      updatePillsState(epochKey);

      const epDef = temporalEpochsData ? temporalEpochsData[epochKey] : null;
      if (!epDef) {
        if (timelineMilestoneBanner) {
          timelineMilestoneBanner.innerHTML = "<span style=\"color:#F59E0B;\">Data epos <b>" + epochKey + "</b> belum tersedia. Jalankan <code>python -m src.build.build_temporal</code> lalu muat ulang.</span>";
        }
        return;
      }
      if (timelineSlider && epDef.slider_idx !== undefined) {
        timelineSlider.value = epDef.slider_idx;
      }
      if (timelineLabel) {
        timelineLabel.textContent = epDef.label || (epochKey === "all_time" ? "Semua Waktu" : `${epDef.start_year}-${epDef.end_year}`);
      }
      if (timelineMilestoneBanner) {
        const auton = epDef.top_autonomy || null;
        const topAuton = auton && auton.id
          ? `${auton.id} (C_i: ${auton.burt_constraint})`
          : "belum dihitung";
        timelineMilestoneBanner.innerHTML =
          `<span><b>${epDef.label || epDef.id}</b>: ` +
          `${formatCount(epDef.nodes)} ${labelOf("nodes", "Simpul")} | ` +
          `${formatCount(epDef.edges)} ${labelOf("edges", "Sisi")} | ` +
          `${labelOf("density", "Kerapatan")}: ${formatNumber(epDef.density, 4)} | ` +
          `Autonomi tertinggi: ${topAuton}</span>`;
      }

      const activeIds = epDef.node_ids ? new Set(epDef.node_ids) : null;
      if (epochKey === "all_time" || !activeIds) {
        activeTopicEdges = allData.links;
        nodeG.classed("dimmed", false)
          .transition()
          .duration(350)
          .style("opacity", 1.0);
      } else {
        nodeG.each(function(d) {
          const isActive = activeIds.has(d.id);
          d3.select(this)
            .classed("dimmed", !isActive)
            .transition()
            .duration(350)
            .style("opacity", isActive ? 1.0 : 0.15);
        });
        activeTopicEdges = allData.links.filter(l => activeIds.has(getSourceId(l)) && activeIds.has(getTargetId(l)));
      }

      renderActiveEdges(activeTopicEdges);
      updateEdgeCountBadge();
      if (timelineMilestoneBanner) {
        const canvasCount = document.getElementById("stat-active-edges");
        timelineMilestoneBanner.innerHTML += " <span style=\"color:#8A99AE;\">(kanvas: " + (canvasCount ? canvasCount.textContent : "-") + " relasi)</span>";
      }
      updateMinimapDots(epDef.end_year);
    }

    function updateTimelineMilestone(selectedYear) {
      if (!timelineMilestoneBanner) return;
      if (selectedYear === null) {
        const counts = (allData.metadata && allData.metadata.counts) || {};
        const summary = (allData.metadata && allData.metadata.summary) || {};
        timelineMilestoneBanner.innerHTML =
          "<span>Semua Waktu: Peta Jaringan Lengkap</span> " +
          '<span style="color:#8A99AE;">(' +
          formatCount(counts.articles) + " artikel, " +
          formatCount((allData.nodes || []).length) + " entitas, " +
          formatCount((allData.links || []).length) + " relasi, densitas " +
          formatNumber(summary.density, 4) + ")</span>";
        return;
      }
      const text = milestoneFor(selectedYear);
      // Angka tahunan dihitung dari artefak, bukan dari tabel statis.
      const telemetry = computeYearTelemetry(selectedYear);
      timelineMilestoneBanner.innerHTML =
        "<span>" + text + "</span> " +
        '<span style="color:#8A99AE;">(' +
        formatCount(telemetry.articles) + " artikel, " +
        formatCount(telemetry.nodes) + " entitas aktif, " +
        formatCount(telemetry.edges) + " relasi, densitas " +
        formatNumber(telemetry.density, 4) + ")</span>";
    }

    function updateTimelineView(year) {
      const years = timelineYears();
      let idx = years.indexOf(year);
      if (idx === -1) idx = years.length - 1;
      if (timelineSlider) timelineSlider.value = idx;
      applyTimelineFilter(idx);
    }

    function applyTimelineFilter(yearIndex) {
      const selectedYear = timelineYears()[yearIndex];
      updateTimelineMilestone(selectedYear);

      // Match epoch pill state
      if (yearIndex <= 1) updatePillsState("epoch_1");
      else if (yearIndex <= 3) updatePillsState("epoch_2");
      else if (yearIndex <= 5) updatePillsState("epoch_3");
      else updatePillsState("all_time");

      if (selectedYear === null) {
        if (timelineLabel) timelineLabel.textContent = "Semua Waktu";
        activeTopicEdges = allData.links;
        nodeG.classed("dimmed", false)
          .transition()
          .duration(350)
          .style("opacity", 1.0);
      } else {
        if (timelineLabel) timelineLabel.textContent = selectedYear.toString();
        activeTopicEdges = allData.links.filter(l =>
          (l.active_years && l.active_years.includes(selectedYear)) ||
          (l.first_seen_year && l.first_seen_year <= selectedYear)
        );

        nodeG.each(function(d) {
          const isActive = d.id === EGO_ID ||
            (d.active_years && d.active_years.includes(selectedYear)) ||
            (d.first_seen_year && d.first_seen_year <= selectedYear);
          d3.select(this)
            .classed("dimmed", !isActive)
            .transition()
            .duration(350)
            .style("opacity", isActive ? 1.0 : 0.20);
        });
      }

      updateMinimapDots(selectedYear);
    }

    // Delegasi klik: pil dibuat ulang setiap boot, jadi listener dipasang di wadah.
    const epochPillsWrapEl = document.getElementById("epoch-pills-wrap");
    if (epochPillsWrapEl) {
      epochPillsWrapEl.addEventListener("click", event => {
        const btn = event.target.closest(".epoch-pill-btn");
        if (!btn) return;
        applyEpochFilter(btn.getAttribute("data-epoch"));
      });
    }

    function stopTimelinePlayback() {
      if (timelineInterval) {
        clearInterval(timelineInterval);
        timelineInterval = null;
      }
      const iconPlay = document.getElementById("icon-play");
      const iconPause = document.getElementById("icon-pause");
      if (iconPlay) iconPlay.style.display = "block";
      if (iconPause) iconPause.style.display = "none";
      if (timelinePlayBtn) timelinePlayBtn.title = "Putar Riwayat Evolusi Klub";
    }

    function startTimelinePlayback() {
      const iconPlay = document.getElementById("icon-play");
      const iconPause = document.getElementById("icon-pause");
      if (iconPlay) iconPlay.style.display = "none";
      if (iconPause) iconPause.style.display = "block";
      if (timelinePlayBtn) timelinePlayBtn.title = "Jeda Pemutaran";

      let cur = timelineSlider ? parseInt(timelineSlider.value, 10) : 0;
      if (cur >= 6) {
        cur = 0;
        if (timelineSlider) timelineSlider.value = 0;
        applyTimelineFilter(0);
      }

      timelineInterval = setInterval(() => {
        cur++;
        if (cur >= 6) {
          if (timelineSlider) timelineSlider.value = 6;
          applyTimelineFilter(6);
          stopTimelinePlayback();
        } else {
          if (timelineSlider) timelineSlider.value = cur;
          applyTimelineFilter(cur);
        }
      }, 1800);
    }

    if (timelineSlider) {
      timelineSlider.addEventListener("input", (e) => {
        stopTimelinePlayback();
        applyTimelineFilter(parseInt(e.target.value, 10));
      });
    }

    if (timelinePlayBtn) {
      timelinePlayBtn.addEventListener("click", () => {
        if (timelineInterval) {
          stopTimelinePlayback();
        } else {
          startTimelinePlayback();
        }
      });
    }

    const zoom = d3.zoom()
      .scaleExtent([0.15, 8])
      .on("zoom", (e) => {
        container.attr("transform", e.transform);
        updateMinimapBox(e.transform);
      })
      // Setelah zoom berhenti, ruang antar label berubah: hitung ulang.
      .on("end", () => {
        scheduleLabelBudget();
        syncViewStateToHash();
      });
    svg.call(zoom);

    // Panel yang menutupi kanvas. Diukur, bukan ditebak: sidebar bisa
    // dilipat dan toolbar bisa bertambah tinggi.
    const CANVAS_OCCLUDERS = [
      { selector: "#sidebar-left", side: "left" },
      { selector: "#top-stats-bar", side: "top" },
      { selector: ".hud-timeline", side: "bottom" },
      { selector: ".hud-dock-left", side: "bottom" },
      { selector: ".hud-minimap", side: "bottom" },
    ];

    function canvasInsets(rect) {
      const insets = { left: 0, top: 0, right: 0, bottom: 0 };
      CANVAS_OCCLUDERS.forEach(({ selector, side }) => {
        const el = document.querySelector(selector);
        if (!el) return;
        const box = el.getBoundingClientRect();
        if (box.width < 2 || box.height < 2) return;  // tersembunyi
        if (side === "left") insets.left = Math.max(insets.left, box.right - rect.left);
        else if (side === "top") insets.top = Math.max(insets.top, box.bottom - rect.top);
        else if (side === "bottom") insets.bottom = Math.max(insets.bottom, rect.bottom - box.top);
        else if (side === "right") insets.right = Math.max(insets.right, rect.right - box.right);
      });
      return insets;
    }

    // Kamera dihitung dari kotak pembatas simpul, di dalam satuan viewBox.
    // Tiga kesalahan lama: transform-nya angka tetap yang menaruh pusat graf
    // di pojok kiri-atas; skalanya diukur dalam piksel
    // padahal SVG memakai viewBox 4600x3800, sehingga 2,2x di satuan pengguna
    // hanya tampil 0,4x di layar; dan area yang dipakai adalah seluruh SVG,
    // termasuk bagian yang tertutup sidebar.
    function getCloseFitTransform(paddingPx = 48, subset = null) {
      const node = svg.node();
      const box = node && node.viewBox && node.viewBox.baseVal;
      const width = node ? node.clientWidth : 0;
      const height = node ? node.clientHeight : 0;
      const points = (subset || allData.nodes || []).filter(
        n => Number.isFinite(n.x) && Number.isFinite(n.y)
      );
      if (!box || !box.width || !points.length || width < 2 || height < 2) {
        return d3.zoomIdentity;
      }

      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      points.forEach(n => {
        if (n.x < minX) minX = n.x;
        if (n.x > maxX) maxX = n.x;
        if (n.y < minY) minY = n.y;
        if (n.y > maxY) maxY = n.y;
      });

      // `meet` memakai skala seragam dan memusatkan sisa ruang.
      const scale = Math.min(width / box.width, height / box.height) || 1;
      const offsetX = (width - box.width * scale) / 2;
      const offsetY = (height - box.height * scale) / 2;
      const insets = canvasInsets(node.getBoundingClientRect());
      const toUnit = px => px / scale;

      const left = box.x + toUnit(insets.left + paddingPx - offsetX);
      const right = box.x + toUnit(width - insets.right - paddingPx - offsetX);
      const top = box.y + toUnit(insets.top + paddingPx - offsetY);
      const bottom = box.y + toUnit(height - insets.bottom - paddingPx - offsetY);
      const spanX = Math.max(maxX - minX, 1);
      const spanY = Math.max(maxY - minY, 1);
      const raw = Math.min((right - left) / spanX, (bottom - top) / spanY);
      const fit = Math.max(0.15, Math.min(8, raw));
      return d3.zoomIdentity
        .translate(
          (left + right) / 2 - (fit * (minX + maxX)) / 2,
          (top + bottom) / 2 - (fit * (minY + maxY)) / 2
        )
        .scale(fit);
    }
    // Titik (x, y) di tengah area yang tidak tertutup panel, pada skala `k`.
    // Versi lama memakai translate(-x*k, -y*k), yang menaruh titik itu di pojok
    // kiri-atas SVG — bukan di tengah layar.
    function cameraAt(x, y, k) {
      const node = svg.node();
      const box = node && node.viewBox && node.viewBox.baseVal;
      if (!box || !box.width) return d3.zoomIdentity.translate(-x * k, -y * k).scale(k);
      const width = node.clientWidth;
      const height = node.clientHeight;
      const pxPerUnit = Math.min(width / box.width, height / box.height) || 1;
      const offsetX = (width - box.width * pxPerUnit) / 2;
      const offsetY = (height - box.height * pxPerUnit) / 2;
      const insets = canvasInsets(node.getBoundingClientRect());
      const cx = box.x + ((insets.left + width - insets.right) / 2 - offsetX) / pxPerUnit;
      const cy = box.y + ((insets.top + height - insets.bottom) / 2 - offsetY) / pxPerUnit;
      return d3.zoomIdentity.translate(cx - x * k, cy - y * k).scale(k);
    }

    function resetGraphView(selection = svg) {
      return selection.call(zoom.transform, getCloseFitTransform());
    }
    requestAnimationFrame(() => resetGraphView());

    // Layers in order
    const orbitLayer = container.append("g").attr("class", "orbit-guide-layer");
    const activeLayer = container.append("g").attr("class", "active-edge-layer");
    const traceLayer = container.append("g").attr("class", "trace-layer");
    const nodeLayer = container.append("g").attr("class", "node-layer");
    const bipartiteLayer = container.append("g").attr("class", "bipartite-layer").style("display", "none");

                    // Radar range rings and sector watermarks eliminated: open 2D canvas for organic topological force network.

    // Concentric Radar Orbit Tiers Definition (Watermarks & Labels)
    // Label cincin diisi saat boot dari presentation.orbit_tiers.
    const ORBIT_TIERS = [220, 440, 660, 820].map(r => ({ r: r, label: "" }));

    // Inner concentric circle guides deleted: canvas opened for pure topological force layout.
    // Preserved only outermost macro boundary horizon ring at r=1800.
    ORBIT_TIERS.forEach(tier => {
      orbitLayer.append("text")
        .attr("class", "orbit-tier-watermark")
        .attr("x", 0)
        .attr("y", -tier.r + 14)
        .attr("fill", "rgba(148, 163, 184, 0.25)")
        .attr("font-size", "11px")
        .attr("font-weight", "800")
        .attr("letter-spacing", "2px")
        .attr("text-anchor", "middle")
        .attr("pointer-events", "none")
        .style("display", "none")
        .text(tier.label);
    });

    // Radius tidak lagi dihitung di sini: skala ukuran datang dari payload
    // (`size_rank`, `rank_*`, `radius_tier`) yang dihitung engine dari
    // peringkat. Satu fungsi radius untuk semua mode ada di computeNodeRadius.

    // Deskripsi entitas berasal dari bundle (entities.description).
    function entityDescription(d) {
      if (!d) return "";
      return d.description || typeLabel(d.entity_type);
    }

    const nodeMap = new Map();
    allData.nodes.forEach(n => nodeMap.set(n.id, n));

    // -------------------------------------------------------------
    // Continuous Radial Sonar & 4-Sector Coordinates (Anti-Carousel)
