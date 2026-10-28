    // -------------------------------------------------------------
    // 1. Legend Toggle Collapse
    const legendCard = document.getElementById("hud-legend-card");
    const legendToggleBtn = document.getElementById("legend-header-toggle");
    const legendToggleIcon = document.getElementById("legend-toggle-icon");
    if (legendToggleBtn && legendCard) {
      legendToggleBtn.addEventListener("click", () => {
        legendCard.classList.toggle("collapsed");
        legendToggleIcon.textContent = legendCard.classList.contains("collapsed") ? "+" : "−";
      });
    }

    // 2. Analytics Modals
    const modalNetwork = document.getElementById("modal-network-overview");

    // Modal Close Buttons
    document.querySelectorAll(".modal-close-btn").forEach(btn => {
      btn.addEventListener("click", function() {
        const targetId = this.getAttribute("data-close");
        const m = document.getElementById(targetId);
        if (m) m.classList.remove("open");
        // Panel tertutup berarti tidak ada yang membaca; hentikan pemantauan
        // supaya tab yang ditinggal tidak terus menanyakan status uji.
        if (targetId === "modal-network-overview" && typeof stopInferencePoll === "function") {
          stopInferencePoll();
        }
      });
    });

    document.querySelectorAll(".analytics-modal").forEach(m => {
      m.addEventListener("click", function(e) {
        if (e.target === this) {
          this.classList.remove("open");
          if (this.id === "modal-network-overview" && typeof stopInferencePoll === "function") {
            stopInferencePoll();
          }
        }
      });
    });

    // 3. Edge Strength Filter Pills Logic
    document.querySelectorAll(".edge-filter-pill[data-w]").forEach(btn => {
      btn.addEventListener("click", function() {
        document.querySelectorAll(".edge-filter-pill[data-w]").forEach(b => b.classList.remove("active"));
        this.classList.add("active");
        currentMinWeight = parseInt(this.getAttribute("data-w"), 10);
        resetNodeHighlight();
      });
    });

    // -------------------------------------------------------------
    // SNA Left Sidebar: Controller & Entity Breakdown Accordion
    // -------------------------------------------------------------
    const sidebarEl = document.getElementById("sidebar-left");
    const sidebarTabBtn = document.getElementById("sidebar-tab-btn");
    const railSidebarBtn = document.getElementById("btn-toggle-sidebar");
    const sbChevron = document.getElementById("sb-chevron");

    function toggleSidebar(forceState) {
      if (!sidebarEl) return;
      const willCollapse = forceState !== undefined ? !forceState : !sidebarEl.classList.contains("collapsed");
      sidebarEl.classList.toggle("collapsed", willCollapse);
      document.body.classList.toggle("sidebar-open", !willCollapse);
      if (railSidebarBtn) railSidebarBtn.classList.toggle("active", !willCollapse);
      if (sbChevron) {
        sbChevron.innerHTML = willCollapse 
          ? '<polyline points="9 18 15 12 9 6"></polyline>' 
          : '<polyline points="15 18 9 12 15 6"></polyline>';
      }
    }

    if (sidebarTabBtn) sidebarTabBtn.addEventListener("click", () => toggleSidebar());
    if (railSidebarBtn) railSidebarBtn.addEventListener("click", () => toggleSidebar());
    const canvasLegend = document.getElementById("canvas-legend");
    const canvasLegendToggle = document.getElementById("canvas-legend-toggle");
    if (canvasLegendToggle && canvasLegend) canvasLegendToggle.addEventListener("click", () => {
      const expanded = canvasLegend.classList.toggle("expanded");
      canvasLegendToggle.setAttribute("aria-expanded", String(expanded));
    });

    // Render Entity Accordions — tipe entitas mengikuti presentation bundle.
    const sidebarAccordionState = new Map();
    let temporalNodeIds = null;
    let entityDisplayLimit = 5; // Default: Top 5 view
    let currentStartYear = null;
    let currentEndYear = null;
    currentActiveNodeSet = new Set();

    function yearBounds() {
      const range = (BOOTSTRAP && BOOTSTRAP.dataset && BOOTSTRAP.dataset.date_range) || [];
      const years = timelineYears().filter(y => y !== null);
      if (currentStartYear === null) {
        currentStartYear = range.length === 2
          ? parseInt(String(range[0]).slice(0, 4), 10)
          : (years.length ? years[0] : 0);
      }
      if (currentEndYear === null) {
        currentEndYear = range.length === 2
          ? parseInt(String(range[1]).slice(0, 4), 10)
          : (years.length ? years[years.length - 1] : currentStartYear);
      }
      return { start: currentStartYear, end: currentEndYear };
    }


    function radialDistance(node) {
      return Math.hypot(Number(node.x) || 0, Number(node.y) || 0);
    }

    function getOrbitSummary(nodes) {
      const egoMeta = (PRESENTATION && PRESENTATION.ego) || null;
      const summary = [
        {
          key: "core",
          label: ((PRESENTATION && PRESENTATION.wording) || {}).orbit_core || "Pusat inti",
          detail: egoMeta ? (egoMeta.label || egoMeta.id) : "",
          count: 0
        },
        { key: "inner", label: "Inner Zone", detail: "0 sampai 700px", count: 0 },
        { key: "tactical", label: "Tactical Arena", detail: "701 sampai 1250px", count: 0 },
        { key: "outer", label: "Outer Horizon", detail: "di atas 1250px", count: 0 }
      ];
      nodes.forEach(node => {
        if (EGO_ID && node.id === EGO_ID) summary[0].count += 1;
        else if (radialDistance(node) <= 700) summary[1].count += 1;
        else if (radialDistance(node) <= 1250) summary[2].count += 1;
        else summary[3].count += 1;
      });
      return EGO_ID ? summary : summary.slice(1);
    }

    function updateCanvasLegend(groups) {
      const types = document.getElementById("canvas-legend-types");
      if (!types) return;
      types.innerHTML = groups.map(({cat, items}) => `<div class="canvas-legend-type"><span class="canvas-legend-type-dot" style="background:${cat.color}"></span><span class="canvas-legend-type-label">${cat.label}</span><span class="canvas-legend-type-count">${items.length}</span></div>`).join("");
    }

    function renderOrbitExplainer() {
      return "";
    }

    function renderSidebarEntities(filterQuery = "") {
      const container = document.getElementById("sb-accordion-list");
      if (!container || !allData.nodes) return;

      const q = filterQuery.toLowerCase().trim();
      const catConfig = ((PRESENTATION && PRESENTATION.entity_types) || []).map(t => ({
        type: t.id,
        label: t.label || t.id,
        color: t.color || "#8A99AE",
        detail: ""
      }));
      const degMap = {};
      activeTopicEdges.forEach(l => {
        const s = getSourceId(l), t = getTargetId(l);
        degMap[s] = (degMap[s] || 0) + 1;
        degMap[t] = (degMap[t] || 0) + 1;
      });

      const groups = catConfig.map(cat => {
        let items = allData.nodes.filter(n => n.entity_type === cat.type && n.id !== EGO_ID);
        if (currentActiveNodeSet && currentActiveNodeSet.size > 0) {
          items = items.filter(n => currentActiveNodeSet.has(n.id));
        }
        if (q) items = items.filter(n => (n.display_label || n.label || n.id).toLowerCase().includes(q));
        items.sort((a, b) => (degMap[b.id] || b.metrics?.degree || 0) - (degMap[a.id] || a.metrics?.degree || 0));
        return { cat, items };
      }).filter(({items}) => items.length || !q);

      const card = ({cat, items}) => {
        const open = q ? true : (sidebarAccordionState.get(cat.type) !== false);
        const isLimited = !q && entityDisplayLimit !== null && items.length > entityDisplayLimit;
        const displayItems = isLimited ? items.slice(0, entityDisplayLimit) : items;

        return `<div class="sb-acc-group" data-type="${cat.type}">
          <button class="sb-acc-header" type="button" aria-expanded="${open}" data-type="${cat.type}">
            <span class="sb-acc-title"><span class="sb-acc-dot" style="background:${cat.color};"></span><span><strong>${cat.label}</strong><small>${cat.detail}</small></span></span>
            <span style="display:flex;align-items:center;gap:7px;"><span class="sb-acc-badge">${items.length}</span><span class="sb-acc-chevron">⌄</span></span>
          </button>
          <div class="sb-acc-body${open ? '' : ' collapsed'}">${displayItems.map(n => {
            const name = n.display_label || n.label || n.id;
            const degree = degMap[n.id] || 0;
            return `<button type="button" class="sb-entity-row" data-id="${n.id}" title="Klik untuk fokus graph"><span class="sb-entity-name" title="${name}">${name}</span><span class="sb-entity-deg" title="Degree pada graph aktif">${degree}</span></button>`;
          }).join("")}${isLimited ? `<div class="sb-entity-more" data-type="${cat.type}">+${items.length - entityDisplayLimit} lainnya (klik Semua)</div>` : ''}</div></div>`;
      };

      const byType = new Map(groups.map(group => [group.cat.type, group]));
      const makeColumn = types => types.map(type => byType.has(type) ? card(byType.get(type)) : "").join("");

      const totalNonEgo = allData.nodes.filter(n => n.id !== EGO_ID).length;
      const toolbarHtml = `<div class="sb-limit-toolbar">
        <span class="sb-limit-title">TAMPILAN ENTITAS</span>
        <div class="sb-limit-pills">
          <button class="limit-pill ${entityDisplayLimit === 5 ? 'active' : ''}" data-limit="5" type="button">5 Teratas</button>
          <button class="limit-pill ${entityDisplayLimit === null ? 'active' : ''}" data-limit="all" type="button">Semua (${totalNonEgo})</button>
        </div>
      </div>`;

      // Dua kolom dibentuk dari urutan tipe di metadata, bukan daftar tetap.
      const columnA = catConfig.filter((_, i) => i % 2 === 0).map(c => c.type);
      const columnB = catConfig.filter((_, i) => i % 2 === 1).map(c => c.type);
      container.innerHTML = toolbarHtml + `<div class="sb-entity-columns"><div class="sb-entity-column">${makeColumn(columnA)}</div><div class="sb-entity-column">${makeColumn(columnB)}</div></div>` + '<p class="sb-accordion-footer">Klik entitas untuk fokus graph · Scroll untuk seluruh daftar</p>';
      updateCanvasLegend(groups);

      container.querySelectorAll(".sb-acc-header").forEach(header => header.addEventListener("click", () => {
        const type = header.dataset.type;
        const body = header.nextElementSibling;
        const open = body.classList.contains("collapsed");
        body.classList.toggle("collapsed", !open);
        header.setAttribute("aria-expanded", String(open));
        sidebarAccordionState.set(type, open);
      }));

      container.querySelectorAll(".limit-pill").forEach(btn => {
        btn.addEventListener("click", function() {
          const lim = this.getAttribute("data-limit");
          entityDisplayLimit = lim === "5" ? 5 : null;
          renderSidebarEntities(sbSearchInput?.value || "");
        });
      });

      container.querySelectorAll(".sb-entity-more").forEach(btn => {
        btn.addEventListener("click", function() {
          entityDisplayLimit = null;
          renderSidebarEntities(sbSearchInput?.value || "");
        });
      });

      container.querySelectorAll(".sb-entity-row").forEach(row => row.addEventListener("click", function() {
        const targetNode = allData.nodes.find(n => n.id === this.dataset.id);
        if (!targetNode) return;
        selectAndInspectNode(targetNode);
      }));
    }

    function isNodeActiveInYearRange(node, sy, ey) {
      if (!node) return false;
      if (EGO_ID && node.id === EGO_ID) return true;
      const mby = node.metrics?.metrics_by_year;
      if (mby) {
        for (let y = sy; y <= ey; y++) {
          const yd = mby[String(y)];
          if (yd && yd.articles > 0) return true;
        }
        return false;
      }
      const yList = node.active_years || [];
      if (yList.length) return yList.some(y => y >= sy && y <= ey);
      // Tanpa metadata tahun, simpul dianggap aktif pada semua rentang.
      return true;
    }

    function applyCombinedFilters() {
      // 1. Compute active temporal nodes
      temporalNodeIds = new Set();
      const bounds = yearBounds();
      allData.nodes.forEach(n => {
        if (isNodeActiveInYearRange(n, bounds.start, bounds.end)) {
          temporalNodeIds.add(n.id);
        }
      });
      if (EGO_ID) temporalNodeIds.add(EGO_ID);

      // 2. Base candidate edges from currentTopic
      const topicEdges = (currentTopic && currentTopic !== "ALL")
        ? (topicNetworks[currentTopic] || [])
        : allData.links;

      // 3. Intersect with temporal nodes
      activeTopicEdges = topicEdges.filter(l => {
        const s = getSourceId(l), t = getTargetId(l);
        return temporalNodeIds.has(s) && temporalNodeIds.has(t);
      });

      // 4. Compute active node set from active edges + ego
      currentActiveNodeSet = new Set();
      activeTopicEdges.forEach(l => {
        currentActiveNodeSet.add(getSourceId(l));
        currentActiveNodeSet.add(getTargetId(l));
      });
      if (EGO_ID) currentActiveNodeSet.add(EGO_ID);

      // 5. Render active edges

      // 5b. Compute Emergent Topic Center & Update Contextual HUD
      const emergent = computeEmergentTopicCenter(currentTopic, activeTopicEdges);
      currentTopicDriver = emergent.driverId;
      updateTopicHudDisplay(emergent);

      // 5c. Dynamic Isometric Focal Translation to Emergent Topic Driver
      const driverNode = nodeMap.get(currentTopicDriver);
      const isMacro = (currentTopic === "ALL" || !driverNode);
      const offsetX = isMacro ? 0 : ((driverNode.topo_x !== undefined) ? driverNode.topo_x : (driverNode.x || 0));
      const offsetY = isMacro ? 0 : ((driverNode.topo_y !== undefined) ? driverNode.topo_y : (driverNode.y || 0));

      allData.nodes.forEach(d => {
        const tx = (d.topo_x !== undefined) ? d.topo_x : (d.x || 0);
        const ty = (d.topo_y !== undefined) ? d.topo_y : (d.y || 0);
        d.target_x = tx - offsetX;
        d.target_y = ty - offsetY;
        d.x = d.target_x;
        d.y = d.target_y;
        d.fx = d.target_x;
        d.fy = d.target_y;
        d.vx = 0;
        d.vy = 0;

        const relR = Math.hypot(d.x, d.y);
        if (d.id === currentTopicDriver) {
          d.orbit_label = isMacro ? "Pusat Inti (Ego Center 0px)" : `Pusat Wacana: ${d.id} (0px)`;
        } else if (currentActiveNodeSet.has(d.id)) {
          d.orbit_label = isMacro ? `Inner Zone (${Math.round(relR)}px dari ${egoLabel("pusat")})` : `Jarak Relasi: ${Math.round(relR)}px dari ${currentTopicDriver}`;
        } else {
          d.orbit_label = `Periferal Wacana (${Math.round(relR)}px)`;
        }
      });

      const transitionDuration = 700;
      nodeG.transition().duration(transitionDuration).ease(d3.easeCubicInOut)
        .attr("transform", d => `translate(${d.x.toFixed(1)},${d.y.toFixed(1)})`);

      activeLayer.selectAll("path.edge-path").transition().duration(transitionDuration).ease(d3.easeCubicInOut)
        .attr("d", ed => computeBezierPath(ed));

      activeLayer.selectAll("path.edge-hover-hitbox").transition().duration(transitionDuration).ease(d3.easeCubicInOut)
        .attr("d", ed => computeBezierPath(ed));

      if (minimapNodesG && minimapNodesG.node()) {
        minimapNodesG.selectAll("circle.mm-dot").transition().duration(transitionDuration).ease(d3.easeCubicInOut)
          .attr("cx", d => d.x)
          .attr("cy", d => d.y);
      }

      if (simulation) {
        simulation.nodes(allData.nodes);
        simulation.force("link").links(buildSimLinks(activeTopicEdges));
      }

      // 5d. Camera Auto-Fit centering on focal driver (0, 0)
      if (isMacro) {
        svg.transition().duration(transitionDuration).ease(d3.easeCubicInOut).call(resetGraphView);
      } else {
        // Kamera yang sama dengan tombol Fit, hanya dipersempit ke himpunan
        // aktif. Versi lama menaruh subgraf hasil filter di pojok kiri-atas,
        // filter menempel di pojok kiri-atas.
        const activeNodesList = allData.nodes.filter(n => currentActiveNodeSet.has(n.id));
        svg.transition().duration(transitionDuration).ease(d3.easeCubicInOut).call(
          zoom.transform,
          getCloseFitTransform(48, activeNodesList)
        );
      }

      // 6. Update canvas node dimming
      restoreNodeDimmedState();

      // 7. Update minimap
      updateMinimapUnified();


      // 9. Update Living Legend sidebar
      renderSidebarEntities(sbSearchInput?.value || "");
    }

    function restoreNodeDimmedState() {
      nodeG.each(function(n) {
        const isActive = currentActiveNodeSet.has(n.id);
        const isDriver = (currentTopic !== "ALL" && currentTopicDriver === n.id);
        d3.select(this)
          .classed("dimmed", !isActive)
          .style("opacity", isActive ? 1.0 : 0.04)
          .style("pointer-events", isActive ? "all" : "none");

        d3.select(this).select("circle.main-circle")
          .attr("stroke", isDriver ? "#38BDF8" : "#FFFFFF")
          .attr("stroke-width", isDriver ? 3.5 : 2.0);
      });
    }

    function updateMinimapUnified() {
      if (!minimapNodesG || !minimapNodesG.node()) return;
      minimapNodesG.selectAll("circle.mm-dot")
        .attr("opacity", d => {
          const isActive = currentActiveNodeSet.has(d.id);
          return isActive ? 0.95 : 0.15;
        });
    }

    // Two-Way Search Synchronization (Adaptive Top-Left HUD & Left Sidebar)
    const sbSearchInput = document.getElementById("sb-search-input");
    const hudSearchInput = document.getElementById("hud-search");

    function executeGlobalSearch(q) {
      const query = q.toLowerCase().trim();
      // Sync input values
      if (sbSearchInput && sbSearchInput.value !== q) sbSearchInput.value = q;
      if (hudSearchInput && hudSearchInput.value !== q) hudSearchInput.value = q;

      // Filter sidebar accordion
      renderSidebarEntities(q);

      // Filter graph canvas nodes
      if (!query) {
        nodeG.classed("dimmed", false);
      } else {
        nodeG.classed("dimmed", n => !(n.display_label || n.label || n.id).toLowerCase().includes(query));
      }
    }

    if (sbSearchInput) {
      sbSearchInput.addEventListener("input", (e) => executeGlobalSearch(e.target.value));
    }
    if (hudSearchInput) {
      hudSearchInput.addEventListener("input", (e) => executeGlobalSearch(e.target.value));
    }

    // -------------------------------------------------------------
    // Sports Network Intelligence: 3-Mode Architecture Controller
