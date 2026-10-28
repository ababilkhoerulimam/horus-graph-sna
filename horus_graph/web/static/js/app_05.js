    function loadAnnotations() {
      fetch("/api/annotations")
        .then(res => {
          if (!res.ok) throw new Error("HTTP " + res.status);
          return res.json();
        })
        .then(data => {
          ANNOTATIONS = (data && data.annotations) || [];
          if (currentNoteTarget) renderNodeNotes(currentNoteTarget);
        })
        .catch(err => {
          console.warn("[Annotations] Error:", err);
          const list = document.getElementById("drawer-note-list");
          if (list) list.textContent = "Catatan gagal dimuat (\u2014).";
        });
    }

    // -------------------------------------------------------------

    // Catatan analis: pemasangan handler dan muat awal.
    const btnSaveNote = document.getElementById("btn-save-note");
    if (btnSaveNote) btnSaveNote.addEventListener("click", saveNote);
    loadAnnotations();

    // Export CSV. Nilai yang belum tersedia ditulis kosong, bukan 0: 0 adalah
    // hasil pengukuran (netral), kosong berarti belum ada data.
    function csvValue(value) {
      return (value === null || value === undefined || Number.isNaN(value)) ? "" : value;
    }

    document.getElementById("btn-export-csv").addEventListener("click", () => {
      const nodeHeaders = ["id", "label", "entity_type", "orbit_ring", "first_seen_year", "hawkes_alpha", "degree", "in_degree", "out_degree", "pagerank", "betweenness", "burt_constraint", "sentiment_status", "pos_pct", "neu_pct", "neg_pct", "stance", "articles"];
      const nodeRows = allData.nodes.map(n => {
        const m = n.metrics || {};
        const sent = nodeSentiment(n);
        return [
          `"${n.id}"`, `"${n.label}"`, `"${n.entity_type}"`, `"${n.orbit_label || ''}"`,
          csvValue(n.first_seen_year), csvValue(n.hawkes_alpha),
          csvValue(m.degree), csvValue(m.in_degree), csvValue(m.out_degree),
          csvValue(m.pagerank), csvValue(m.betweenness), csvValue(m.burt_constraint),
          // Status lapisan, bukan boolean: "awaiting_input" dan "ready" adalah
          // dua hal berbeda, dan sel kosong berarti tidak ada skor simpul ini.
          sent ? "ready" : sentimentLayerStatus(),
          csvValue(sent ? sent.pos : null), csvValue(sent ? sent.neu : null), csvValue(sent ? sent.neg : null),
          csvValue(sent ? sent.stance : null),
          csvValue(n.articles)
        ].join(",");
      });
      const csvContent = "data:text/csv;charset=utf-8," + [nodeHeaders.join(","), ...nodeRows].join("\n");
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement("a");
      link.setAttribute("href", encodedUri);
      link.setAttribute("download", `${fileSlug()}_metrics.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    });

    // Export PNG
    document.getElementById("btn-export-png").addEventListener("click", () => {
      const svgEl = document.getElementById("network-svg");
      const serializer = new XMLSerializer();
      const svgString = serializer.serializeToString(svgEl);
      const svgBlob = new Blob([svgString], {type: "image/svg+xml;charset=utf-8"});
      const URLObj = window.URL || window.webkitURL || window;
      const blobURL = URLObj.createObjectURL(svgBlob);
      const image = new Image();
      image.onload = function() {
        const canvas = document.createElement("canvas");
        canvas.width = 1800;
        canvas.height = 1200;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#050505";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
        const pngURL = canvas.toDataURL("image/png");
        const dlLink = document.createElement("a");
        dlLink.download = `${fileSlug()}.png`;
        dlLink.href = pngURL;
        document.body.appendChild(dlLink);
        dlLink.click();
        document.body.removeChild(dlLink);
      };
      image.src = blobURL;
    });

    // Laporan HTML mandiri. SVG kanvas ikut dikirim karena hanya browser yang
    // punya hasil render aktual; server menyusun provenance dan menyaring
    // gambar sebelum menempelkannya.
    const btnExportReport = document.getElementById("btn-export-report");
    if (btnExportReport) {
      btnExportReport.addEventListener("click", () => {
        const svgEl = document.getElementById("network-svg");
        const svgString = svgEl ? new XMLSerializer().serializeToString(svgEl) : null;
        btnExportReport.disabled = true;
        fetch("/api/report", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ svg: svgString })
        })
          .then(res => {
            if (!res.ok) throw new Error("HTTP " + res.status);
            return res.text();
          })
          .then(htmlText => {
            const blob = new Blob([htmlText], { type: "text/html;charset=utf-8" });
            const url = (window.URL || window.webkitURL || window).createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = `${fileSlug()}-laporan.html`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            (window.URL || window.webkitURL || window).revokeObjectURL(url);
          })
          .catch(err => console.warn("[Report] Gagal membuat laporan:", err))
          .finally(() => {
            btnExportReport.disabled = false;
          });
      });
    }

        // -------------------------------------------------------------
    // Dijkstra Causal Pathfinding & Hawkes Transmission Engine
    // -------------------------------------------------------------
    function findStrongestCausalPath(sourceId, targetId) {
      const adj = new Map();
      allData.nodes.forEach(n => adj.set(n.id, []));
      
      activeTopicEdges.forEach(l => {
        const s = getSourceId(l);
        const t = getTargetId(l);
        const alpha = l.alpha || (l.coverage_share ? l.coverage_share * 0.8 : 0.45);
        const weight = -Math.log(Math.max(0.01, alpha));
        if (adj.has(s)) adj.get(s).push({ target: t, weight, alpha, link: l, dir: true });
        if (adj.has(t)) adj.get(t).push({ target: s, weight: weight * 1.25, alpha: alpha * 0.8, link: l, dir: false });
      });

      const distances = new Map();
      const prev = new Map();
      const unvisited = new Set(allData.nodes.map(n => n.id));

      allData.nodes.forEach(n => distances.set(n.id, Infinity));
      distances.set(sourceId, 0);

      while (unvisited.size > 0) {
        let curr = null;
        let minD = Infinity;
        for (const n of unvisited) {
          const d = distances.get(n);
          if (d < minD) {
            minD = d;
            curr = n;
          }
        }

        if (!curr || minD === Infinity) break;
        if (curr === targetId) break;

        unvisited.delete(curr);

        (adj.get(curr) || []).forEach(edge => {
          if (unvisited.has(edge.target)) {
            const alt = distances.get(curr) + edge.weight;
            if (alt < distances.get(edge.target)) {
              distances.set(edge.target, alt);
              prev.set(edge.target, { from: curr, edge });
            }
          }
        });
      }

      if (!prev.has(targetId) && sourceId !== targetId) return null;

      const path = [];
      let curr = targetId;
      while (curr !== sourceId) {
        path.unshift(curr);
        const p = prev.get(curr);
        if (!p) break;
        curr = p.from;
      }
      path.unshift(sourceId);
      return path;
    }

    let currentTracerPaths = [];
    let activePathIndex = 0;

    function renderTracedPathDetails(pathIndex) {
      if (!currentTracerPaths[pathIndex]) return;
      activePathIndex = pathIndex;
      const path = currentTracerPaths[pathIndex];

      // Update Tab active status
      document.querySelectorAll(".path-tab").forEach((tab, idx) => {
        tab.classList.toggle("active", idx === pathIndex);
      });

      const pathNodesSet = new Set(path);
      const pathEdgeKeys = new Set();
      
      let diffAlpha = 1.0, hasDiff = false;
      let totalLeadTime = 0.0, hasLead = false;
      let totalWeight = 0, totalJaccard = 0, edgeCount = 0;

      const hopsData = [];

      for (let i = 0; i < path.length - 1; i++) {
        const u = path[i];
        const v = path[i+1];
        pathEdgeKeys.add(u + "->" + v);
        pathEdgeKeys.add(v + "->" + u);

        const edgeData = activeTopicEdges.find(l => 
          (getSourceId(l) === u && getTargetId(l) === v) ||
          (getSourceId(l) === v && getTargetId(l) === u)
        );

        const cat = edgeData ? edgeData.edge_category : "ego_spoke";
        const w = edgeData ? (edgeData.weight || 0) : 100;
        const jac = edgeData ? (edgeData.jaccard || 0) : 0.05;
        totalWeight += w;
        totalJaccard += jac;
        edgeCount++;

        // Real Hawkes detection
        if (cat === "hawkes_diffusion" || (edgeData && edgeData.alpha !== null && edgeData.alpha !== undefined)) {
          const a = edgeData.alpha || 0.025;
          diffAlpha *= a;
          hasDiff = true;
          if (edgeData.lead_time_min) {
            totalLeadTime += edgeData.lead_time_min;
            hasLead = true;
          }
          const leadStr = edgeData.lead_time_min ? `${Math.round(edgeData.lead_time_min)} mnt` : "Sinkron";
          hopsData.push({
            u, v, cat,
            badge: `Hawkes α: ${Number(a).toFixed(3)} | Jeda ${leadStr}`,
            badgeCol: "#F97316"
          });
        } else {
          hopsData.push({
            u, v, cat,
            badge: `${w.toLocaleString("id-ID")} art | Jaccard ${(jac * 100).toFixed(1)}%`,
            badgeCol: "#38BDF8"
          });
        }
      }

      // Visual canvas highlight
      nodeG.each(function(n) {
        const inPath = pathNodesSet.has(n.id);
        d3.select(this)
          .classed("dimmed", !inPath)
          .style("opacity", inPath ? 1.0 : 0.15);
      });

      activeLayer.selectAll("g.edge-item")
        .style("display", l => {
          const s = getSourceId(l), t = getTargetId(l);
          return (pathEdgeKeys.has(s + "->" + t) || pathEdgeKeys.has(t + "->" + s)) ? "block" : "none";
        });

      activeLayer.selectAll(".edge-path")
        .attr("stroke", l => {
          const s = getSourceId(l), t = getTargetId(l);
          return (pathEdgeKeys.has(s + "->" + t) || pathEdgeKeys.has(t + "->" + s)) ? "#38BDF8" : "#475569";
        })
        .attr("stroke-width", l => {
          const s = getSourceId(l), t = getTargetId(l);
          return (pathEdgeKeys.has(s + "->" + t) || pathEdgeKeys.has(t + "->" + s)) ? 2.8 : 0.8;
        })
        .attr("stroke-dasharray", "none")
        .attr("opacity", 1.0)
        .attr("marker-end", "url(#arrow-default)");

      // Bounding box zoom to path
      const pNodes = path.map(id => nodeMap.get(id)).filter(Boolean);
      svg.transition().duration(550).call(
        zoom.transform,
        getCloseFitTransform(64, pNodes)
      );

      // Populate Tracer Details Card
      const resultCard = document.getElementById("trace-result-card");
      resultCard.style.display = "block";
      document.getElementById("trace-hops-badge").textContent = `${path.length - 1} Langkah Kausal (${path.length} Simpul)`;
      
      document.getElementById("trace-hawkes-score").textContent = hasDiff ? `${(diffAlpha * 100).toFixed(2)}% (∏ α)` : "N/A (Ko-okurensi)";
      document.getElementById("trace-lead-time").textContent = hasLead ? `~${Math.round(totalLeadTime)} mnt (~${(totalLeadTime / 60).toFixed(1)} jam)` : "Sinkron / Afiliasi";
      
      const avgJac = edgeCount > 0 ? (totalJaccard / edgeCount) : 0;
      document.getElementById("trace-coverage-affinity").textContent = `${totalWeight.toLocaleString("id-ID")} Artikel (Jaccard: ${(avgJac * 100).toFixed(1)}%)`;

      // Timeline Steps
      const timelineWrap = document.getElementById("trace-chain-timeline");
      timelineWrap.innerHTML = "";
      path.forEach((nid, idx) => {
        const nodeObj = nodeMap.get(nid);
        const item = document.createElement("div");
        item.className = "chain-step";
        const meta = idx === 0 
          ? "Sumber Publikasi Awal (Patient Zero)" 
          : (idx === path.length - 1 ? "Entitas Target Terpapar" : "Agregator / Hub Perantara");

        let hopBadgeHtml = "";
        if (idx < hopsData.length) {
          const hop = hopsData[idx];
          hopBadgeHtml = `<div class="hop-badge" style="background:${hop.badgeCol}22; color:${hop.badgeCol}; border:1px solid ${hop.badgeCol}44; border-radius:3px; padding:2px 6px; font-size:11px; margin-top:3px; display:inline-block;">${hop.badge}</div>`;
        }

        item.innerHTML = `<div class="chain-step-circle" style="background:${nodeObj ? nodeObj.color : '#38BDF8'}; width:8px; height:8px; border-radius:50%; margin-top:5px; flex-shrink:0;"></div>
                          <div style="flex:1;">
                            <div class="chain-step-name" style="font-size:11px; font-weight:800; color:#F8FAFC;">${nodeObj ? (nodeObj.display_label || nodeObj.label) : nid}</div>
                            <div class="chain-step-meta" style="color:#94A3B8; font-size:11px;">${meta}</div>
                            ${hopBadgeHtml}
                          </div>`;
        timelineWrap.appendChild(item);
      });
    }

    function traceAndAnimatePath(sourceId, targetId) {
      const bannerEl = document.getElementById("trace-status-banner");
      if (bannerEl) bannerEl.style.display = "none";

      if (!sourceId || !targetId) {
        if (bannerEl) {
          bannerEl.textContent = "Pilih sumber dan target transmisi terlebih dahulu.";
          bannerEl.style.display = "block";
        }
        return;
      }
      if (sourceId === targetId) {
        if (bannerEl) {
          bannerEl.textContent = "Sumber dan target transmisi harus berbeda.";
          bannerEl.style.display = "block";
        }
        return;
      }

      const p1 = findStrongestCausalPath(sourceId, targetId);
      if (!p1 || p1.length < 2) {
        if (bannerEl) {
          bannerEl.textContent = `Tidak ada jalur transmisi aktif antara ${sourceId} dan ${targetId} pada filter topik ${currentTopic || 'ALL'}. Silakan ganti titik asal atau pilih topik lain.`;
          bannerEl.style.display = "block";
        }
        return;
      }

      // Compute Alternative Path (Bypass intermediate nodes)
      const intermediateNodes = new Set(p1.slice(1, -1));
      const p2 = findAlternativeCausalPath(sourceId, targetId, intermediateNodes);

      currentTracerPaths = [p1];
      if (p2 && p2.length >= 2 && p2.join("->") !== p1.join("->")) {
        currentTracerPaths.push(p2);
      }

      isTracingPath = true;
      if (window.copilotUI && typeof window.copilotUI.closeDrawer === "function") {
        window.copilotUI.closeDrawer();
      }
      const tracerDrawerEl = document.getElementById("tracer-drawer");
      if (tracerDrawerEl) tracerDrawerEl.style.display = "block";
      const nodeDrawerEl = document.getElementById("node-drawer");
      if (nodeDrawerEl) nodeDrawerEl.style.display = "none";

      document.getElementById("btn-toggle-tracer").classList.add("active");
      document.getElementById("btn-nav-graph").classList.remove("active");

      // Activate Path Tabs
      const pathTabsEl = document.getElementById("path-tabs");
      if (pathTabsEl) {
        pathTabsEl.style.display = currentTracerPaths.length > 1 ? "flex" : "none";
        pathTabsEl.style.gap = "6px";
        pathTabsEl.style.marginBottom = "10px";
      }

      renderTracedPathDetails(0);
    }

    function findAlternativeCausalPath(sourceId, targetId, penaltyNodes) {
      const adj = new Map();
      allData.nodes.forEach(n => adj.set(n.id, []));

      activeTopicEdges.forEach(l => {
        const s = getSourceId(l);
        const t = getTargetId(l);
        const w = l.weight || 10;
        const baseCost = 1.0 / Math.sqrt(Math.max(1, w));
        const penS = penaltyNodes.has(s) ? 6.0 : 1.0;
        const penT = penaltyNodes.has(t) ? 6.0 : 1.0;

        if (adj.has(s)) adj.get(s).push({ target: t, cost: baseCost * penT, link: l });
        if (adj.has(t)) adj.get(t).push({ target: s, cost: baseCost * penS, link: l });
      });

      const dist = new Map();
      const prev = new Map();
      const unvis = new Set(allData.nodes.map(n => n.id));

      allData.nodes.forEach(n => dist.set(n.id, Infinity));
      dist.set(sourceId, 0);

      while (unvis.size > 0) {
        let curr = null;
        let minD = Infinity;
        for (const n of unvis) {
          const d = dist.get(n);
          if (d < minD) { minD = d; curr = n; }
        }
        if (!curr || minD === Infinity || curr === targetId) break;
        unvis.delete(curr);

        (adj.get(curr) || []).forEach(edge => {
          if (unvis.has(edge.target)) {
            const alt = dist.get(curr) + edge.cost;
            if (alt < dist.get(edge.target)) {
              dist.set(edge.target, alt);
              prev.set(edge.target, curr);
            }
          }
        });
      }

      if (!prev.has(targetId) && sourceId !== targetId) return null;
      const path = [];
      let c = targetId;
      while (c !== sourceId) {
        path.unshift(c);
        c = prev.get(c);
        if (!c) return null;
      }
      path.unshift(sourceId);
      return path;
    }

    function resetTracePath() {
      isTracingPath = false;
      document.getElementById("trace-result-card").style.display = "none";
      const bannerEl = document.getElementById("trace-status-banner");
      if (bannerEl) bannerEl.style.display = "none";
      document.getElementById("btn-toggle-tracer").classList.remove("active");
      document.getElementById("btn-nav-graph").classList.add("active");
      deactivateNodes();
      svg.transition().duration(400).call(resetGraphView);
    }

    // Populate Select Options and Preset Pills in Tracer Drawer
    function initTracerControls() {
      const srcSelect = document.getElementById("trace-source");
      const tgtSelect = document.getElementById("trace-target");
      if (!srcSelect || !tgtSelect) return;

      srcSelect.innerHTML = "";
      tgtSelect.innerHTML = "";

      // Sort nodes alphabetically
      const sortedNodes = [...allData.nodes].sort((a, b) => (a.display_label || a.label).localeCompare(b.display_label || b.label));

      sortedNodes.forEach(n => {
        const label = n.display_label || n.label;
        const opt1 = document.createElement("option");
        opt1.value = n.id;
        opt1.textContent = `${label} (${n.entity_type})`;
        srcSelect.appendChild(opt1);

        const opt2 = document.createElement("option");
        opt2.value = n.id;
        opt2.textContent = `${label} (${n.entity_type})`;
        tgtSelect.appendChild(opt2);
      });

      // Default asal/tujuan dipilih dari struktur: pusat (bila ada) dan
      // tetangganya dengan bobot terbesar.
      if (sortedNodes.length) {
        const source = EGO_ID || sortedNodes[0].id;
        srcSelect.value = source;
        const strongest = (allData.links || [])
          .filter(l => getSourceId(l) === source || getTargetId(l) === source)
          .sort((a, b) => (b.weight || 0) - (a.weight || 0))[0];
        let target = sortedNodes.find(n => n.id !== source);
        if (strongest) {
          const other = getSourceId(strongest) === source ? getTargetId(strongest) : getSourceId(strongest);
          if (other !== source) target = sortedNodes.find(n => n.id === other) || target;
        }
        if (target) tgtSelect.value = target.id;
      }

      // Preset: empat sisi terkuat pada graf, bukan pasangan tetap di kode.
      const presetWrap = document.getElementById("preset-pill-wrap");
      if (presetWrap) {
        presetWrap.innerHTML = "";
        const presets = [...(allData.links || [])]
          .sort((a, b) => (b.weight || 0) - (a.weight || 0))
          .slice(0, 4)
          .map(l => {
            const src = getSourceId(l);
            const tgt = getTargetId(l);
            return {
              src,
              tgt,
              title: l.category_label || labelOf("edge", "Sisi"),
              label: `${src} ➔ ${tgt}`
            };
          });

        presets.forEach(p => {
          const pill = document.createElement("div");
          pill.className = "preset-pill";
          pill.innerHTML = `<span><strong>${p.title}:</strong> ${p.label}</span><span>➔</span>`;
          pill.addEventListener("click", () => {
            srcSelect.value = p.src;
            tgtSelect.value = p.tgt;
            traceAndAnimatePath(p.src, p.tgt);
          });
          presetWrap.appendChild(pill);
        });
      }
    }

    // -------------------------------------------------------------
    // Comprehensive UI Listeners (Nav, Modal, Tracer, Topic Filter)
    // -------------------------------------------------------------
    const tracerDrawerEl = document.getElementById("tracer-drawer");
    const nodeDrawerEl = document.getElementById("node-drawer");

    // 1. Left Nav Rail: Graph Canvas
    document.getElementById("btn-nav-graph").addEventListener("click", () => {
      document.getElementById("btn-nav-graph").classList.add("active");
      document.getElementById("btn-toggle-tracer").classList.remove("active");
      if (tracerDrawerEl) tracerDrawerEl.style.display = "none";
      if (nodeDrawerEl) nodeDrawerEl.style.display = "none";
      if (isTracingPath) resetTracePath();
      svg.transition().duration(400).call(resetGraphView);
    });

    // 2. Left Nav Rail: Causal Path Tracer
    document.getElementById("btn-toggle-tracer").addEventListener("click", () => {
      if (!tracerDrawerEl) return;
      const isOpen = tracerDrawerEl.style.display === "block";
      if (isOpen) {
        tracerDrawerEl.style.display = "none";
        document.getElementById("btn-toggle-tracer").classList.remove("active");
        document.getElementById("btn-nav-graph").classList.add("active");
        if (isTracingPath) resetTracePath();
      } else {
        if (window.copilotUI && typeof window.copilotUI.closeDrawer === "function") {
          window.copilotUI.closeDrawer();
        }
        tracerDrawerEl.style.display = "block";
        if (nodeDrawerEl) nodeDrawerEl.style.display = "none";
        document.getElementById("btn-toggle-tracer").classList.add("active");
        document.getElementById("btn-nav-graph").classList.remove("active");
      }
    });

    // Close Tracer Drawer
    document.getElementById("tracer-close").addEventListener("click", () => {
      if (tracerDrawerEl) tracerDrawerEl.style.display = "none";
      document.getElementById("btn-toggle-tracer").classList.remove("active");
      document.getElementById("btn-nav-graph").classList.add("active");
      if (isTracingPath) resetTracePath();
    });

    // Run Tracer Button
    document.getElementById("btn-run-trace").addEventListener("click", () => {
      const src = document.getElementById("trace-source").value;
      const tgt = document.getElementById("trace-target").value;
      traceAndAnimatePath(src, tgt);
    });

    // Reset Tracer Button
    document.getElementById("btn-reset-trace").addEventListener("click", () => {
      resetTracePath();
    });

    // Path Tabs Switcher
    document.querySelectorAll(".path-tab").forEach(tab => {
      tab.addEventListener("click", function() {
        const idx = parseInt(this.getAttribute("data-path-idx"), 10);
        renderTracedPathDetails(idx);
      });
    });

    // Open in Tracer Button from Node Drawer (Pure Shortcut Navigasi)
    const btnOpenTracerEl = document.getElementById("btn-open-in-tracer");
    if (btnOpenTracerEl) {
      btnOpenTracerEl.addEventListener("click", () => {
        if (lockedNode) {
          if (window.copilotUI && typeof window.copilotUI.closeDrawer === "function") {
            window.copilotUI.closeDrawer();
          }
          document.getElementById("node-drawer").style.display = "none";
          const tracerDrawerEl = document.getElementById("tracer-drawer");
          if (tracerDrawerEl) tracerDrawerEl.style.display = "block";

          // Sync rail button active state
          document.getElementById("btn-toggle-tracer").classList.add("active");
          document.getElementById("btn-nav-graph").classList.remove("active");

          // Pre-fill Target
          const tgtSelect = document.getElementById("trace-target");
          if (tgtSelect) tgtSelect.value = lockedNode.id;

          // Titik awal cerdas: pusat bila ada, kalau tidak ujung terkuat dari
          // simpul yang sedang dibuka. Dataset tanpa pusat tetap punya asal.
          const srcSelect = document.getElementById("trace-source");
          if (srcSelect) {
            const endpointsOf = link => [getSourceId(link), getTargetId(link)];
            const connected = allData.links
              .filter(l => endpointsOf(l).includes(lockedNode.id))
              .sort((a, b) => (b.weight || 0) - (a.weight || 0));
            if (EGO_ID && lockedNode.id !== EGO_ID) {
              srcSelect.value = EGO_ID;
            } else if (connected.length) {
              const [a, b] = endpointsOf(connected[0]);
              srcSelect.value = a === lockedNode.id ? b : a;
            } else {
              const other = (allData.nodes || []).find(n => n.id !== lockedNode.id);
              if (other) srcSelect.value = other.id;
            }
          }

          // Clear previous errors or results for clean shortcut entry
          const bannerEl = document.getElementById("trace-status-banner");
          if (bannerEl) bannerEl.style.display = "none";
          document.getElementById("trace-result-card").style.display = "none";
          const pathTabsEl = document.getElementById("path-tabs");
          if (pathTabsEl) pathTabsEl.style.display = "none";
        }
      });
    }



    // 4. Header Topic Filter Dropdown
    const topicBtnEl = document.getElementById("topic-btn");
    const topicMenuEl = document.getElementById("topic-menu");
    const topicLabelEl = document.getElementById("topic-label");

    if (topicBtnEl && topicMenuEl) {
      topicBtnEl.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = topicMenuEl.classList.contains("show");
        document.querySelectorAll(".dropdown-menu").forEach(m => m.classList.remove("show", "open"));
        if (!isOpen) {
          topicMenuEl.classList.add("show");
        }
      });

      topicMenuEl.querySelectorAll(".dropdown-item").forEach(item => {
        item.addEventListener("click", function(e) {
          e.stopPropagation();
          topicMenuEl.querySelectorAll(".dropdown-item").forEach(i => i.classList.remove("active"));
          this.classList.add("active");
          const val = this.getAttribute("data-val");
          topicLabelEl.textContent = (val === "ALL") ? "Topik: Semua Wacana (Makro)" : `Topik: ${this.textContent.trim()}`;
          topicMenuEl.classList.remove("show", "open");

          if (isTracingPath) resetTracePath();
          currentTopic = val;
          lockedNode = null;
          deactivateNodes();
          applyCombinedFilters();
        });
      });

      document.addEventListener("click", () => {
        topicMenuEl.classList.remove("show", "open");
      });
    }

    // Initialize Tracer Controls
    initTracerControls();

    // Canvas click resets focus
    svg.on("click", () => {
      if (isTracingPath) resetTracePath();
      lockedNode = null;
      deactivateNodes();
      document.getElementById("node-drawer").style.display = "none";
    });
  

    

  

    // -------------------------------------------------------------
    // Pencarian entitas: indeks dari data/entity_index.json
    // -------------------------------------------------------------
    const searchInput = document.getElementById("hud-search");
    const suggBox = document.getElementById("search-suggestions");

    if (searchInput && suggBox) {
      searchInput.addEventListener("input", function(e) {
        const query = e.target.value.toLowerCase().trim();
        if (query.length < 2) {
          suggBox.style.display = "none";
          return;
        }

        if (!ENTITY_INDEX.length) {
          suggBox.innerHTML = '<div style="padding:10px;font-size:11px;color:#F87171;">Indeks entitas belum tersedia (data/entity_index.json gagal dimuat).</div>';
          suggBox.style.display = "block";
          return;
        }

        const matches = ENTITY_INDEX.filter(ent =>
          ent.name.toLowerCase().includes(query) || String(ent.rid).toLowerCase().includes(query)
        ).slice(0, 10);

        if (matches.length === 0) {
          suggBox.innerHTML = '<div style="padding:10px;font-size:11px;color:#94A3B8;">Tidak ditemukan entitas.</div>';
          suggBox.style.display = "block";
          return;
        }

        suggBox.innerHTML = "";
        matches.forEach(ent => {
          const item = document.createElement("div");
          item.className = "sugg-item";
          item.innerHTML = `<div><div class="sugg-name">${ent.name}</div><div style="font-size:11px;color:#8A99AE;">${ent.type} • ${formatCount(ent.df)} dokumen</div></div>` +
            `<span class="sugg-badge sugg-tag-canvas">Di Kanvas</span>`;

          item.addEventListener("click", () => {
            searchInput.value = ent.name;
            suggBox.style.display = "none";
            selectEntityFromIndex(ent);
          });
          suggBox.appendChild(item);
        });
        suggBox.style.display = "block";
      });

      document.addEventListener("click", function(e) {
        if (!searchInput.contains(e.target) && !suggBox.contains(e.target)) {
          suggBox.style.display = "none";
        }
      });
    }

    function selectEntityFromIndex(ent) {
      const canvasNode = allData.nodes.find(n => n.id === ent.id || n.label === ent.name);
      if (canvasNode) {
        selectAndInspectNode(canvasNode);
        return;
      }
      // Indeks dan artefak graf berasal dari build yang sama; ketidakcocokan
      // berarti salah satu berkas basi, jadi dilaporkan, bukan disintesis.
      console.warn("[Index] Entitas '" + ent.name + "' tidak ada di artefak graf.");
      suggBox.innerHTML = '<div style="padding:10px;font-size:11px;color:#F87171;">Entitas ada di indeks tetapi tidak di artefak graf. Jalankan build ulang.</div>';
      suggBox.style.display = "block";
    }

  

    // -------------------------------------------------------------
    // 3 Analysis Modes & Interactive Controls Logic
