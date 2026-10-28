    // ----------------------------------------------------------

    const SCALE_K = 1.38;

    // Koordinat awal: pakai topo_x/topo_y bila bundle membawanya; kalau tidak,
    // sebar deterministik supaya paint pertama tidak menumpuk di titik nol.
    function initNodeCoordinates() {
      const total = Math.max(1, allData.nodes.length);
      allData.nodes.forEach((n, index) => {
        const hasTopo = (n.topo_x !== undefined && n.topo_y !== undefined);
        let posX = hasTopo ? n.topo_x : (n.x || 0);
        let posY = hasTopo ? n.topo_y : (n.y || 0);
        if (!hasTopo && !n.x && !n.y) {
          const angle = (index / total) * Math.PI * 2;
          const radius = 180 + 14 * Math.sqrt(index);
          posX = Math.cos(angle) * radius;
          posY = Math.sin(angle) * radius;
        }
        const posR = Math.hypot(posX, posY);

        n.x = posX;
        n.y = posY;
        n.fx = posX;
        n.fy = posY;
        n.sonar_r = posR;
        n.sector = hasTopo ? "topological" : (n.sector || "center");

        if (EGO_ID && n.id === EGO_ID) {
          n.orbit_label = n.orbit_label || "Pusat";
        } else if (posR <= 700) {
          n.orbit_label = `Inner Zone (${Math.round(posR)}px dari ${egoLabel("pusat")})`;
        } else if (posR <= 1250) {
          n.orbit_label = `Tactical Arena (${Math.round(posR)}px dari ${egoLabel("pusat")})`;
        } else {
          n.orbit_label = `Outer Horizon (${Math.round(posR)}px dari ${egoLabel("pusat")})`;
        }
      });
    }

    function resolveNode(nodeRef) {
      if (!nodeRef) return null;
      if (typeof nodeRef === "object" && nodeRef.x !== undefined) return nodeRef;
      return nodeMap.get(nodeRef) || null;
    }

    // Anti-Overlap Geometric Edge Path (Two-Sided Clearance + Outward Quadratic Bezier for Alter Chords)
    function computeBezierPath(d) {
      const sNode = resolveNode(d.source);
      const tNode = resolveNode(d.target);
      if (!sNode || !tNode) return "";

      const sx = sNode.x, sy = sNode.y;
      const tx = tNode.x, ty = tNode.y;
      const dx = tx - sx;
      const dy = ty - sy;
      const dist = Math.hypot(dx, dy) || 1;

      const sRadius = sNode.node_radius || (sNode.id === EGO_ID ? 28.0 : 12.0);
      const tRadius = tNode.node_radius || (tNode.id === EGO_ID ? 28.0 : 12.0);

      // Clean straight lines with two-sided perimeter clearance across all edges (zero curvature)
      const sClear = sRadius + 2.5;
      const tClear = tRadius + 4.5;
      const startX = sx + (dx / dist) * sClear;
      const startY = sy + (dy / dist) * sClear;
      const endX = tx - (dx / dist) * tClear;
      const endY = ty - (dy / dist) * tClear;
      return `M ${startX.toFixed(1)} ${startY.toFixed(1)} L ${endX.toFixed(1)} ${endY.toFixed(1)}`;
    }

    // Render Edges
    // Anti-occlusion Set: non-spoke cross-chords that slice through unrelated third nodes
    // Tidak ada lagi daftar edge teroklusi yang ditulis tangan: label
    // ditata ulang saat render, sehingga berlaku untuk dataset apa pun.
    const OCCLUDED_EDGES = new Set();
    let currentMode = "actor_network"; // "actor_network" | "topic_actor" | "narrative_temporal"
    let currentMinWeight = 10;
    let currentMinNpmi = 0.20;
    let showEgoSpokes = true;
    let currentMediaLens = "ALL";
    let hideMediaNodes = false;
    const categoryFilters = {
      intra_squad: true,
      ego_spoke: true,
      tactical_link: true,
      rivalry_clash: false,
      media_coverage: false,
      hawkes_diffusion: false
    };

    function shouldDisplayEdge(d) {
      if (currentMode !== "actor_network" && currentMode !== "narrative_temporal") {
        return false;
      }
      if (hideMediaNodes) {
        const sId = getSourceId(d), tId = getTargetId(d);
        const sNode = nodeMap.get(sId), tNode = nodeMap.get(tId);
        if (isSourceNode(sNode)) return false;
        if (isSourceNode(tNode)) return false;
      }
      const cat = d.edge_category;
      if (cat === "intra_squad" && !categoryFilters.intra_squad) return false;
      if (cat === "ego_spoke" && !categoryFilters.ego_spoke) return false;
      if ((cat === "tactical_link" || cat === "cohort_mesh") && !categoryFilters.tactical_link) return false;
      if (cat === "rivalry_clash" && !categoryFilters.rivalry_clash) return false;
      if (cat === "media_coverage" && !categoryFilters.media_coverage) return false;
      if (cat === "hawkes_diffusion" && !categoryFilters.hawkes_diffusion) return false;

      // Spoke core and intra squad always display
      if (cat === "ego_spoke" || cat === "intra_squad") return true;

      const sig = d.significance || {};
      const npmi = sig.npmi !== undefined ? sig.npmi : d.npmi;
      // NPMI yang tidak dikirim bukan nol. Nilai tak dikenal dibiarkan lolos
      // ambang, karena menggugurkannya berarti menyatakan ia terukur rendah.
      if (currentMinNpmi !== null && npmi !== undefined && npmi !== null && npmi < currentMinNpmi) {
        return false;
      }
      return true;
    }

    function updateEdgeCountBadge() {
      const visibleCount = activeLayer.selectAll("g.edge-item")
        .filter(function() { return d3.select(this).style("display") !== "none"; })
        .size();
      const badgeElem = document.getElementById("hud-edge-count");
      if (badgeElem) badgeElem.textContent = `${visibleCount} sisi`;

      // Himpunan aktif yang kosong berarti belum ada filter, bukan nol simpul.
      const filtered = (typeof currentActiveNodeSet !== "undefined")
        && currentActiveNodeSet && currentActiveNodeSet.size > 0;
      if (filtered) {
        updateMacroStats(currentActiveNodeSet.size, visibleCount);
      } else {
        updateMacroStats();
      }
    }

    function getEdgeColor(l) {
      // Heider (1946) Signed Sentiment SNA Edge Polarity
      if ((l.sentiment_valence !== undefined && l.sentiment_valence < 0) || l.edge_category === "rivalry_clash") {
        return "#EF4444"; // Signed Negative Friction (rivalry clash tension)
      }
      if (l.edge_category === "intra_squad") return "#10B981"; // Positive Squad Synergy
      if (l.edge_category === "ego_spoke") return "#38BDF8"; // Positive Core Affiliation
      if (l.edge_category === "cohort_mesh") return "#A855F7"; // Positive Cohort Mesh
      if (l.edge_category === "management_institutional") return "#F59E0B"; // Institutional
      if (l.edge_category === "regulator_venue") return "#8A99AE"; // Contextual Venue
      if (l.edge_category === "media_coverage") return "#94A3B8"; // Media Wire
      return "#FFFFFF"; // Fallback pure white
    }

    function getEdgeOpacity(d) {
      if (d.edge_category === "ego_spoke") return 0.70; // Core Ego Spoke stays prominent
      if (d.edge_category === "intra_squad") return 0.50; // Tactical squad relations
      if (d.edge_category === "rivalry_clash") return 0.20; // Subdued rivalry tension to eliminate red haze
      if (d.edge_category === "media_coverage") return 0.16; // Subdued cross-cutting media wire lines
      if (d.edge_category === "hawkes_diffusion") return 0.20;
      return 0.25;
    }

    function getEdgeWidth(d) {
      const sId = getSourceId(d), tId = getTargetId(d);
      const isSpoke = sId === EGO_ID || tId === EGO_ID;
      if (isSpoke) return 1.8;
      if (d.edge_category === "intra_squad") return 1.3;
      if (d.edge_category === "rivalry_clash") return 0.9;
      if (d.edge_category === "media_coverage") return 0.75;
      return 0.85;
    }

    function getEdgeMarker(d) {
      if ((d.sentiment_valence !== undefined && d.sentiment_valence < 0) || d.edge_category === "rivalry_clash") {
        return "url(#arrow-clash)";
      }
      return "url(#arrow-default)";
    }

    function onEdgeHover(event, d) {
      const s = getSourceId(d), t = getTargetId(d);
      const srcNode = nodeMap.get(s), tgtNode = nodeMap.get(t);
      const srcLabel = srcNode ? (srcNode.display_label || srcNode.label || s) : s;
      const tgtLabel = tgtNode ? (tgtNode.display_label || tgtNode.label || t) : t;

      d3.select(event.currentTarget.parentNode).select(".edge-path")
        .attr("stroke", "#38BDF8")
        .attr("stroke-width", ed => getEdgeWidth(ed) + 2.5)
        .attr("opacity", 1.0);

      if (nodeTooltipEl) {
        nodeTooltipEl.style.display = "block";
        nodeTooltipEl.innerHTML = `
          <div style="font-weight:800; font-size:11px; color:#F8FAFC; margin-bottom:3px;">${srcLabel} ⟷ ${tgtLabel}</div>
          <div style="font-size:11px; color:#38BDF8;">${d.category_label || d.edge_category || 'Relasi Asosiasi'}</div>
          <div style="font-size:11px; color:#10B981; margin-top:2px;">${(d.weight === undefined || d.weight === null) ? "—" : d.weight} artikel bersama</div>
          <div style="font-size:11px; color:#F59E0B; margin-top:4px; font-weight:700;">➔ Klik garis untuk membuka bukti artikel</div>
        `;
        nodeTooltipEl.style.left = (event.pageX + 15) + "px";
        nodeTooltipEl.style.top = (event.pageY - 20) + "px";
      }
    }

    function onEdgeMove(event) {
      if (nodeTooltipEl && nodeTooltipEl.style.display === "block") {
        nodeTooltipEl.style.left = (event.pageX + 15) + "px";
        nodeTooltipEl.style.top = (event.pageY - 20) + "px";
      }
    }

    function onEdgeLeave(event, d) {
      d3.select(event.currentTarget.parentNode).select(".edge-path")
        .attr("stroke", ed => getEdgeColor(ed))
        .attr("stroke-width", ed => getEdgeWidth(ed))
        .attr("opacity", ed => getEdgeOpacity(ed));
      if (nodeTooltipEl) nodeTooltipEl.style.display = "none";
    }

    function renderActiveEdges(edgeList) {
      // Di atas ambang, sisi digambar canvas: satu path SVG per sisi berarti
      // 50.000 elemen yang harus ditata ulang setiap frame.
      if (window.HorusCanvas && HorusCanvas.active) {
        HorusCanvas.setEdges(edgeList);
        updateEdgeCountBadge();
        return;
      }
      const linkSel = activeLayer.selectAll("g.edge-item")
        .data(edgeList, d => getSourceId(d) + "->" + getTargetId(d));

      linkSel.exit().remove();

      const linkEnter = linkSel.enter().append("g").attr("class", "edge-item");
      linkEnter.append("path").attr("class", "edge-hover-hitbox");
      linkEnter.append("path").attr("class", "edge-path");

      const linkMerge = linkEnter.merge(linkSel);
      linkMerge.style("display", d => shouldDisplayEdge(d) ? "block" : "none");

      linkMerge.select(".edge-hover-hitbox")
        .attr("d", d => computeBezierPath(d))
        .on("mouseenter", (event, d) => onEdgeHover(event, d))
        .on("mousemove", (event) => onEdgeMove(event))
        .on("mouseleave", (event, d) => onEdgeLeave(event, d))
        .on("click", (event, d) => {
          event.stopPropagation();
          inspectEdgeDetails(d);
        });

      linkMerge.select(".edge-path")
        .attr("d", d => computeBezierPath(d))
        .attr("stroke", d => getEdgeColor(d))
        .attr("stroke-width", d => getEdgeWidth(d))
        .attr("stroke-dasharray", "6, 4")
        .attr("opacity", d => getEdgeOpacity(d))
        .attr("marker-end", d => getEdgeMarker(d));

      updateEdgeCountBadge();
    }


    // -------------------------------------------------------------
    // Render Nodes (True Circle Nodes with Hover Capsule Expansion)
    // -------------------------------------------------------------
    // Core anchors that always show subtle label plate underneath to eliminate clutter
    // Label yang selalu tampil ditentukan entities.is_anchor.
    function isAnchorNode(d) {
      return !!(d && d.is_anchor);
    }

    let nodeG = null;

    // Nama aksesibel satu simpul. Derajat hanya disebut kalau memang diukur;
    // angka karangan di sini akan terbaca sebagai hasil analisis oleh pembaca
    // layar, sama buruknya dengan angka karangan di layar.
    function nodeAriaLabel(d) {
      const label = d.display_label || d.label || d.id;
      const type = d.entity_type || d.type || null;
      const degree = Number.isFinite(d.degree) ? d.degree
        : (d.metrics && Number.isFinite(d.metrics.degree) ? d.metrics.degree : null);
      const parts = [label];
      if (type) parts.push(type);
      if (degree !== null) parts.push("derajat " + degree);
      return parts.join(", ");
    }

    function focusGraphNode(node) {
      if (!nodeG || !node) return;
      nodeG.attr("tabindex", -1);
      const target = nodeG.filter(d => d.id === node.id);
      target.attr("tabindex", 0);
      const el = target.node();
      if (el && typeof el.focus === "function") el.focus();
    }

    function buildNodeLayer() {
      nodeG = nodeLayer.selectAll("g.node-item")
      .data(allData.nodes, d => d.id)
      .join("g")
      .attr("class", "node-item")
      .attr("transform", d => `translate(${d.x.toFixed(1)},${d.y.toFixed(1)})`)
      .style("cursor", "pointer")
      // Satu simpul saja yang masuk urutan Tab; panah memindahkan fokus di
      // antara simpul. Dengan tabindex=0 untuk semua, pengguna keyboard harus
      // melewati 77 perhentian sebelum bisa keluar dari kanvas.
      .attr("tabindex", (d, index) => (index === 0 ? 0 : -1))
      .attr("role", "button")
      .attr("aria-label", d => nodeAriaLabel(d))
      .on("focus", function() {
        nodeG.attr("tabindex", -1);
        d3.select(this).attr("tabindex", 0);
      })
      .on("keydown", function(event, d) {
        if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
          event.preventDefault();
          event.stopPropagation();
          selectAndInspectNode(d);
          return;
        }
        const step = (event.key === "ArrowRight" || event.key === "ArrowDown") ? 1
          : (event.key === "ArrowLeft" || event.key === "ArrowUp") ? -1 : 0;
        if (!step) return;
        const nodes = allData.nodes;
        if (!nodes.length) return;
        event.preventDefault();
        focusGraphNode(nodes[(nodes.indexOf(d) + step + nodes.length) % nodes.length]);
      })
      .on("click", (event, d) => {
        if (event.defaultPrevented) return;
        event.stopPropagation();
        selectAndInspectNode(d);
      })
      .on("mouseenter", function(event, d) {
        if (isTracingPath) return;
        highlightNodeConnections(d);
        showNodeTooltip(event, d);
      })
      .on("mousemove", function(event) {
        moveNodeTooltip(event);
      })
      .on("mouseleave", function() {
        if (isTracingPath) return;
        if (!lockedNode) resetNodeHighlight();
        hideNodeTooltip();
      })
      .call(d3.drag()
        .filter(() => false) // d3.drag disabled per user request: static topological layout locked
      );

    nodeG.each(function(d) {
      const el = d3.select(this);
      const isSun = d.id === EGO_ID;
      const isAnchor = isAnchorNode(d);
      const displayLabel = d.display_label || d.label;
      const nodeColor = d.color || "#8A99AE";

      // 0. Solid Background Shield (Masks any edge passing underneath this node)
      const baseRadius = computeNodeRadius(d);
      d.node_radius = baseRadius;

      el.append("circle")
        .attr("class", "node-shield")
        .attr("r", baseRadius + (isSun ? 6 : 3.5))
        .attr("fill", "#050505")
        .attr("stroke", "none");

      // 1. Center Sun (simpul pusat) Dual Focal Concentric Aura
      if (isSun) {
        el.append("circle")
          .attr("class", "sun-outer-aura")
          .attr("r", 44)
          .attr("fill", "none")
          .attr("stroke", "rgba(56, 189, 248, 0.35)")
          .attr("stroke-width", 1.5)
          .attr("stroke-dasharray", "4, 3");

        el.append("circle")
          .attr("class", "sun-aura")
          .attr("r", 34)
          .attr("fill", "none")
          .attr("stroke", "#38BDF8")
          .attr("stroke-width", 2.0)
          .attr("opacity", 0.9);
      }

      // 2. Sub-Hub Concentric Outer Accent Ring (Tier 1) - crisp and glowing
      if (d.radius_tier === 1 && !isSun) {
        el.append("circle")
          .attr("class", "subhub-accent-ring")
          .attr("r", (d.node_radius || 22.0) + 4.5)
          .attr("fill", "none")
          .attr("stroke", nodeColor)
          .attr("stroke-width", 2.0)
          .attr("stroke-dasharray", "4, 3")
          .attr("opacity", 0.85);
      }

      // 3. Main Circle Node Body
      el.append("circle")
        .attr("class", "main-circle")
        .attr("r", baseRadius)
        .attr("fill", nodeColor)
        .attr("stroke", isSun ? "#38BDF8" : "#FFFFFF")
        .attr("stroke-width", isSun ? 3.5 : (d.radius_tier === 1 ? 2.4 : (d.radius_tier === 2 ? 1.6 : 1.0)));

      // 4. Label tetap: pusat, anchor dari data, dan peringkat teratas.
      // Sisanya menunggu hover. Batasnya proporsional terhadap jumlah simpul
      // supaya graf 12 simpul tidak dipenuhi label dan graf 1.000 simpul tidak
      // kehilangan konteks.
      if (isSun || isAnchor || d.label_priority <= labelBudget()) {
        const labelLen = displayLabel.length;
        const charWidth = isSun ? 6.8 : 6.0;
        const platePad = isSun ? 16 : 12;
        const plateW = Math.max(30, labelLen * charWidth + platePad);
        const plateH = isSun ? 16 : 14;
        const plateY = baseRadius + (isSun ? 8 : 4);

        el.append("rect")
          .attr("class", "label-plate")
          .attr("x", -plateW / 2)
          .attr("y", plateY)
          .attr("width", plateW)
          .attr("height", plateH)
          .attr("rx", 3.0)
          .attr("fill", "#050505")
          .attr("stroke", isSun ? "rgba(56, 189, 248, 0.45)" : "rgba(255, 255, 255, 0.18)")
          .attr("stroke-width", isSun ? 1.0 : 0.7)
          .style("opacity", 1.0);

        el.append("text")
          .attr("class", "static-label")
          .attr("x", 0)
          .attr("y", plateY + (isSun ? 11.5 : 10))
          .attr("text-anchor", "middle")
          .attr("font-size", isSun ? "10.5px" : "9px")
          .attr("font-weight", isSun ? "900" : "800")
          .attr("fill", isSun ? "#38BDF8" : "#F8FAFC")
          .attr("pointer-events", "none")
          .style("opacity", 1.0)
          .text(displayLabel);
      }

      // 5. Hover Pill Capsule (Instant High-Contrast Pill on Demand for All 77 Nodes)
      const pillG = el.append("g").attr("class", "hover-pill");
      const textLen = displayLabel.length;
      const pillW = Math.max(76, textLen * 7.2 + 24);
      const pillH = isSun ? 28 : (d.radius_tier === 1 ? 25 : 23);

      pillG.append("rect")
        .attr("x", -pillW / 2)
        .attr("y", -pillH / 2)
        .attr("width", pillW)
        .attr("height", pillH)
        .attr("rx", pillH / 2)
        .attr("fill", nodeColor)
        .attr("stroke", "#FFFFFF")
        .attr("stroke-width", 2.0)
        .attr("filter", "drop-shadow(0 0 12px rgba(56, 189, 248, 0.8))");

      pillG.append("text")
        .attr("text-anchor", "middle")
        .attr("dy", 4)
        .attr("fill", "#FFFFFF")
        .attr("font-size", "10px")
        .attr("font-weight", "800")
        .text(displayLabel);
    });
    }

    // Label yang tampil sekaligus. Proporsional, bukan angka tetap: 12 simpul
    // tidak perlu 40 label, 1.000 simpul tidak cukup 40 kalau semuanya penting.
    function labelBudget() {
      const total = (allData.nodes || []).length;
      return Math.min(40, Math.max(8, Math.ceil(total * 0.15)));
    }

    let labelBudgetPending = false;

    function scheduleLabelBudget() {
      if (labelBudgetPending) return;
      labelBudgetPending = true;
      requestAnimationFrame(() => {
        labelBudgetPending = false;
        applyLabelBudget();
      });
    }

    function applyLabelBudget() {
      if (!nodeG) return;
      const candidates = [];
      nodeG.each(function (d) {
        const plate = this.querySelector(".label-plate");
        const textEl = this.querySelector(".static-label");
        if (!plate || !textEl) return;
        plate.style.display = "";
        textEl.style.display = "";
        candidates.push({ d, plate, textEl });
      });
      // Peringkat teratas menang lebih dulu; label yang bertabrakan
      // disembunyikan. Tata letak tidak bergerak (drag dimatikan), jadi cukup
      // dihitung ulang setelah simulasi berhenti dan setelah zoom berakhir.
      candidates.sort((a, b) => (a.d.label_priority || 0) - (b.d.label_priority || 0));
      const taken = [];
      candidates.forEach(({ d, plate, textEl }) => {
        const box = textEl.getBoundingClientRect();
        const area = {
          left: box.left - 3,
          right: box.right + 3,
          top: box.top - 3,
          bottom: box.bottom + 3
        };
        const clash = taken.some(
          other => !(area.right < other.left || area.left > other.right || area.bottom < other.top || area.top > other.bottom)
        );
        const visible = !clash || d.id === EGO_ID;
        plate.style.display = visible ? "" : "none";
        textEl.style.display = visible ? "" : "none";
        if (visible) taken.push(area);
      });
    }

    // Neighborhood Highlight
    function highlightNodeConnections(centerNode) {
      const neighborIds = new Set([centerNode.id]);
      const connectedEdgeSet = new Set();

      activeTopicEdges.forEach(l => {
        const sId = getSourceId(l), tId = getTargetId(l);
        if (sId === centerNode.id) {
          neighborIds.add(tId);
          connectedEdgeSet.add(l);
        }
        if (tId === centerNode.id) {
          neighborIds.add(sId);
          connectedEdgeSet.add(l);
        }
      });

      // 1. Isolate Nodes: connected nodes stay 100% lit; non-connected drop to 0.08 shadow silhouette
      nodeG.classed("dimmed", n => !neighborIds.has(n.id));
      nodeG.classed("active", n => n.id === centerNode.id);

      // 2. Isolate Edges: Causal Direction Split (Cyan Outgoing vs Amber Incoming)!
      activeLayer.selectAll("g.edge-item")
        .style("display", l => connectedEdgeSet.has(l) ? "block" : "none");

      activeLayer.selectAll(".edge-path")
        .attr("stroke", l => {
          const sId = getSourceId(l), tId = getTargetId(l);
          if (sId === centerNode.id) return "#38BDF8"; // OUTGOING: Electric Cyan
          if (tId === centerNode.id) return "#F59E0B"; // INCOMING: Warm Amber
          return "#F1F5F9";
        })
        .attr("stroke-width", l => {
          const sId = getSourceId(l), tId = getTargetId(l);
          const isConnected = sId === centerNode.id || tId === centerNode.id;
          return isConnected ? 2.5 : 0.6;
        })
        .attr("stroke-dasharray", "6, 4")
        .attr("opacity", l => {
          const sId = getSourceId(l), tId = getTargetId(l);
          const isConnected = sId === centerNode.id || tId === centerNode.id;
          return isConnected ? 1.0 : 0.08;
        })
        .attr("marker-end", l => {
          const sId = getSourceId(l), tId = getTargetId(l);
          if (sId === centerNode.id) return "url(#arrow-out)";
          if (tId === centerNode.id) return "url(#arrow-in)";
          return "url(#arrow-default)";
        });
    }

    function resetNodeHighlight() {
      if (lockedNode) {
        highlightNodeConnections(lockedNode);
        return;
      }

      nodeG.classed("active", false);
      restoreNodeDimmedState();
      activeLayer.selectAll("g.edge-item")
        .style("display", d => shouldDisplayEdge(d) ? "block" : "none");

      activeLayer.selectAll(".edge-path")
        .attr("stroke", l => getEdgeColor(l))
        .attr("stroke-width", l => getEdgeWidth(l))
        .attr("stroke-dasharray", "6, 4")
        .attr("opacity", l => getEdgeOpacity(l))
        .attr("marker-end", l => getEdgeMarker(l));

      updateEdgeCountBadge();
    }

    // -------------------------------------------------------------
    // Rich Interactive Node Intelligence Tooltip ("Shape Kotak")
    // -------------------------------------------------------------
    const nodeTooltipEl = document.getElementById("node-tooltip");

    function showNodeTooltip(event, d) {
      if (!nodeTooltipEl) return;
      const m = d.metrics || {};
      const isSun = d.id === EGO_ID;
      const displayLabel = d.display_label || d.label;
      const desc = entityDescription(d);

      document.getElementById("ntt-name").textContent = displayLabel;
      const badge = document.getElementById("ntt-badge");
      badge.textContent = d.entity_type;
      badge.style.backgroundColor = (d.color || "#8A99AE") + "33";
      badge.style.color = d.color || "#38BDF8";

      document.getElementById("ntt-desc").textContent = desc;
      
      // `corpus_sample_n` tidak pernah dikirim serializer; `articles` adalah
      // jumlah artikel yang benar-benar menyebut entitas ini.
      const sampN = [m.corpus_sample_n, d.articles, d.size]
        .find(v => v !== undefined && v !== null);
      const sampLabel = sampN === undefined ? null : Number(sampN).toLocaleString("id-ID");
      document.getElementById("ntt-volume").textContent = sampLabel === null ? "\u2014" : `${sampLabel} artikel`;

      // Peran taktis hanya ada bila bundle membawa blok `tactical`; tidak ada
      // serializer yang mengirimnya hari ini, jadi tanpa blok barisnya kosong.
      const tac = d.tactical || {};
      document.getElementById("ntt-role").textContent = tac.role
        ? `${tac.role}${tac.rank ? ` (#${tac.rank})` : ""}`
        : "\u2014";

      // Causal Flow metrics (Inflow vs Outflow)
      let inCount = 0, outCount = 0;
      activeTopicEdges.forEach(l => {
        if (getSourceId(l) === d.id) outCount++;
        if (getTargetId(l) === d.id) inCount++;
      });
      const flowEl = document.getElementById("ntt-flow");
      if (flowEl) {
        flowEl.innerHTML = `<span style="color:#38BDF8;font-weight:700;">↗ Out: ${outCount}</span> &nbsp;|&nbsp; <span style="color:#F59E0B;font-weight:700;">↘ In: ${inCount}</span>`;
      }

      // Sentiment bar
      const sent = nodeSentiment(d);
      if (sent) {
        document.getElementById("ntt-stance-bar").style.display = "flex";
        document.getElementById("ntt-bar-pos").style.width = sent.pos + "%";
        document.getElementById("ntt-bar-neu").style.width = sent.neu + "%";
        document.getElementById("ntt-bar-neg").style.width = sent.neg + "%";

        const stanceText = (sent.stance >= 0 ? "+" : "") + sent.stance.toFixed(2);
        const stanceEl = document.getElementById("ntt-stance-text");
        stanceEl.textContent = stanceText + " Stance (Pos " + sent.pos + "%)";
        stanceEl.style.color = sent.stance >= 0 ? "#16A34A" : "#DC2626";
        document.getElementById("ntt-neg-pct").textContent = "Neg " + sent.neg + "%";
      } else {
        document.getElementById("ntt-stance-bar").style.display = "none";
        document.getElementById("ntt-stance-text").textContent = sentimentUnavailableLabel();
        document.getElementById("ntt-stance-text").style.color = "var(--text-dim)";
        document.getElementById("ntt-neg-pct").textContent = "";
      }

      moveNodeTooltip(event);
      nodeTooltipEl.style.display = "block";
    }

    function moveNodeTooltip(event) {
      if (!nodeTooltipEl) return;
      const pad = 16;
      let left = (event.clientX || event.pageX) + pad;
      let top = (event.clientY || event.pageY) - 10;
      
      // Viewport safety boundary
      if (left + 330 > window.innerWidth) {
        left = (event.clientX || event.pageX) - 330;
      }
      if (top + 230 > window.innerHeight) {
        top = window.innerHeight - 240;
      }

      nodeTooltipEl.style.left = left + "px";
      nodeTooltipEl.style.top = Math.max(10, top) + "px";
    }

    function hideNodeTooltip() {
      if (nodeTooltipEl) nodeTooltipEl.style.display = "none";
    }

    function zoomToNode(node, duration = 750, factor = 2.2) {
      if (!svg || !zoom || !node) return;
      // Skala dihitung dari kamera keseluruhan, bukan angka tetap: 2,4 di satuan
      // viewBox hanya 0,46x di layar, jadi "zoom ke simpul" justru menjauh.
      const overview = getCloseFitTransform().k;
      const targetScale = Math.max(0.15, Math.min(8, overview * factor));
      svg.transition().duration(duration).call(zoom.transform, cameraAt(node.x, node.y, targetScale));
    }

    function selectAndInspectNode(d) {
      lockedNode = d;
      highlightNodeConnections(d);
      populateDrawerDetails(d);
      zoomToNode(d, 700);
    }

    // -------------------------------------------------------------
    // Sentimen simpul: satu pembaca, satu bentuk.
