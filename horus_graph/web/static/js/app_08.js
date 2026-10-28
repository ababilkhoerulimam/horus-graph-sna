    // -------------------------------------------------------------
    let bipartiteDataCache = null;

    function renderBipartiteTopicActor() {
      bipartiteLayer.selectAll("*").remove();

      const loadingText = bipartiteLayer.append("text")
        .attr("x", 0).attr("y", 0)
        .attr("fill", "#38BDF8").attr("font-size", "16px").attr("text-anchor", "middle")
        .text("Memuat Jaringan Bipartite Topik-Aktor...");

      const renderData = (data) => {
        bipartiteLayer.selectAll("*").remove();
        if (!data || !data.topics || !data.actors) return;

        // Enterprise 3-Level Sankey Architecture (Media -> Topik -> Aktor)
        if (data.sankey_data && data.sankey_data.nodes && data.sankey_data.links) {
          const sankey = data.sankey_data;
          const mediaNodes = sankey.nodes.filter(n => n.level === 0);
          const topicNodes = sankey.nodes.filter(n => n.level === 1);
          const actorNodes = sankey.nodes.filter(n => n.level === 2);

          const colX = { 0: -750, 1: 0, 2: 750 };
          const nodeLayoutMap = new Map();

          // Level 0 (Media Sources) layout
          const mediaTotalH = 700;
          const mediaYSpacing = mediaNodes.length > 1 ? mediaTotalH / (mediaNodes.length - 1) : 0;
          const mediaStartY = -mediaTotalH / 2;
          mediaNodes.forEach((n, i) => {
            nodeLayoutMap.set(n.id, {
              x: colX[0],
              y: mediaStartY + i * mediaYSpacing,
              width: 200,
              height: cardHeight(n, 42),
              data: n
            });
          });

          // Level 1 (Topics) layout
          const topicTotalH = 580;
          const topicYSpacing = topicNodes.length > 1 ? topicTotalH / (topicNodes.length - 1) : 0;
          const topicStartY = -topicTotalH / 2;
          topicNodes.forEach((n, i) => {
            nodeLayoutMap.set(n.id, {
              x: colX[1],
              y: topicStartY + i * topicYSpacing,
              width: 260,
              height: cardHeight(n, 52),
              data: n
            });
          });

          // Level 2 (Actors) layout
          const actorTotalH = 720;
          const actorYSpacing = actorNodes.length > 1 ? actorTotalH / (actorNodes.length - 1) : 0;
          const actorStartY = -actorTotalH / 2;
          actorNodes.forEach((n, i) => {
            nodeLayoutMap.set(n.id, {
              x: colX[2],
              y: actorStartY + i * actorYSpacing,
              width: 220,
              height: cardHeight(n, 38),
              data: n
            });
          });

          // Header Banners (jumlah dibaca dari sankey, bukan literal)
          const headerG = bipartiteLayer.append("g").attr("class", "sankey-headers");
          const headers = [
            { x: colX[0], y: -415, title: "1. LENSA MEDIA EKSTERNAL", subtitle: `${mediaNodes.length} Saluran Pengamat / Sindikasi`, color: "#EA580C" },
            { x: colX[1], y: -415, title: "2. AGENDA FRAMING NARRATIF", subtitle: `${topicNodes.length} Klaster Isu Liputan Klub`, color: "#38BDF8" },
            { x: colX[2], y: -415, title: "3. AKTOR KUNCI & SENTIMEN", subtitle: `${actorNodes.length} Figur Lapangan & Manajemen`, color: "#10B981" }
          ];

          headers.forEach(h => {
            const hg = headerG.append("g").attr("transform", `translate(${h.x}, ${h.y})`);
            hg.append("rect")
              .attr("x", -120).attr("y", -20).attr("width", 240).attr("height", 42)
              .attr("rx", 6).attr("fill", "rgba(15, 23, 42, 0.90)")
              .attr("stroke", h.color).attr("stroke-width", 1.5).attr("stroke-opacity", 0.7);
            hg.append("text")
              .attr("x", 0).attr("y", -3).attr("text-anchor", "middle")
              .attr("fill", "#F8FAFC").attr("font-size", "11px").attr("font-weight", "800")
              .text(h.title);
            hg.append("text")
              .attr("x", 0).attr("y", 12).attr("text-anchor", "middle")
              .attr("fill", "#94A3B8").attr("font-size", "9px").attr("font-weight", "600")
              .text(h.subtitle);
          });

          // Flow Links
          const linkG = bipartiteLayer.append("g").attr("class", "sankey-links");
          const linkItems = linkG.selectAll("path")
            .data(sankey.links.filter(l => nodeLayoutMap.has(l.source) && nodeLayoutMap.has(l.target)))
            .enter().append("path")
            .attr("class", "sankey-ribbon")
            .attr("d", d => {
              const src = nodeLayoutMap.get(d.source);
              const tgt = nodeLayoutMap.get(d.target);
              const x1 = src.x + src.width / 2;
              const y1 = src.y;
              const x2 = tgt.x - tgt.width / 2;
              const y2 = tgt.y;
              const cx1 = x1 + (x2 - x1) * 0.45;
              const cy1 = y1;
              const cx2 = x1 + (x2 - x1) * 0.55;
              const cy2 = y2;
              return `M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`;
            })
            .attr("fill", "none")
            .attr("stroke", d => {
              // Valensi hanya ada bila lapisan sentimen mengisi tepi ini.
              if (typeof d.sentiment !== "number") return "#38BDF8";
              if (d.sentiment > 0.05) return "#10B981";
              if (d.sentiment < -0.05) return "#EF4444";
              return "#38BDF8";
            })
            .attr("stroke-width", d => Math.max(2.5, Math.min(18, (d.value || 1) * 0.55)))
            .attr("stroke-opacity", 0.32)
            .style("cursor", "pointer")
            .on("mouseenter", function(event, d) {
              d3.select(this).attr("stroke-opacity", 0.95).attr("stroke-width", Math.max(4.5, Math.min(22, (d.value || 1) * 0.55 + 3)));
              const srcNode = nodeLayoutMap.get(d.source);
              const tgtNode = nodeLayoutMap.get(d.target);
              const srcLabel = srcNode ? srcNode.data.label : d.source;
              const tgtLabel = tgtNode ? tgtNode.data.label : d.target;
              if (nodeTooltipEl) {
                nodeTooltipEl.style.display = "block";
                nodeTooltipEl.innerHTML = `
                  <div style="font-weight:800; font-size:11px; color:#F8FAFC; margin-bottom:4px;">${srcLabel} ➔ ${tgtLabel}</div>
                  <div style="font-size:11px; color:#38BDF8;">Volume Aliran: ${d.value} artikel</div>
                  ${typeof d.sentiment === "number"
                    ? `<div style="font-size:11px; color:${d.sentiment >= 0 ? '#10B981' : '#EF4444'};">Valensi Sentimen: ${(d.sentiment >= 0 ? '+' : '') + Number(d.sentiment).toFixed(2)}</div>`
                    : ""}
                `;
                nodeTooltipEl.style.left = (event.pageX + 15) + "px";
                nodeTooltipEl.style.top = (event.pageY - 20) + "px";
              }
            })
            .on("mouseleave", function() {
              d3.select(this).attr("stroke-opacity", 0.32).attr("stroke-width", d => Math.max(2.5, Math.min(18, (d.value || 1) * 0.55)));
              if (nodeTooltipEl) nodeTooltipEl.style.display = "none";
            });

          // Draw Sankey Nodes
          const nodeG = bipartiteLayer.append("g").attr("class", "sankey-nodes");
          const allNodes = [...mediaNodes, ...topicNodes, ...actorNodes];

          const nodeItems = nodeG.selectAll("g.sankey-node")
            .data(allNodes)
            .enter().append("g")
            .attr("class", "sankey-node")
            .attr("transform", d => {
              const pos = nodeLayoutMap.get(d.id);
              return `translate(${pos.x}, ${pos.y})`;
            })
            .style("cursor", "pointer")
            .on("mouseenter", (event, d) => {
              linkItems.attr("stroke-opacity", l => (l.source === d.id || l.target === d.id) ? 0.95 : 0.04);
            })
            .on("mouseleave", () => {
              linkItems.attr("stroke-opacity", 0.32);
            })
            .on("click", (event, d) => {
              if (d.category === "actor") {
                const raw = d.raw_id || d.id.replace("actor:", "");
                const realNode = nodeMap.get(raw);
                if (realNode) selectAndInspectNode(realNode);
              }
            });

          // Node Card Rectangles
          nodeItems.append("rect")
            .attr("x", d => -nodeLayoutMap.get(d.id).width / 2)
            .attr("y", d => -nodeLayoutMap.get(d.id).height / 2)
            .attr("width", d => nodeLayoutMap.get(d.id).width)
            .attr("height", d => nodeLayoutMap.get(d.id).height)
            .attr("rx", 6)
            .attr("fill", d => {
              if (d.category === "media") return "rgba(234, 88, 12, 0.16)";
              if (d.category === "topic") return "rgba(56, 189, 248, 0.16)";
              return "rgba(15, 23, 42, 0.92)";
            })
            .attr("stroke", d => d.color || "#38BDF8")
            .attr("stroke-width", d => d.category === "topic" ? 2.0 : 1.2);

          // Card Icon Dot
          nodeItems.append("circle")
            .attr("cx", d => -nodeLayoutMap.get(d.id).width / 2 + 14)
            .attr("cy", 0)
            .attr("r", 4.5)
            .attr("fill", d => d.color || "#38BDF8");

          // Node Main Label
          nodeItems.append("text")
            .attr("x", d => -nodeLayoutMap.get(d.id).width / 2 + 26)
            .attr("y", 4)
            .attr("fill", "#F8FAFC")
            .attr("font-size", d => d.category === "topic" ? "11.5px" : "10px")
            .attr("font-weight", "700")
            .text(d => {
              const maxL = d.category === "topic" ? 24 : 17;
              return d.label.length > maxL ? d.label.slice(0, maxL) + "..." : d.label;
            });

          // Node Sentiment Badge for Actors
          // Badge sentimen hanya untuk aktor yang punya skor; sebelumnya
          // setiap aktor menampilkan +0.00 yang terbaca sebagai hasil ukur.
          nodeItems.filter(d => d.category === "actor" && typeof d.sentiment === "number").append("text")
            .attr("x", d => nodeLayoutMap.get(d.id).width / 2 - 10)
            .attr("y", 3.5)
            .attr("text-anchor", "end")
            .attr("fill", d => d.sentiment >= 0 ? "#10B981" : "#EF4444")
            .attr("font-size", "9px")
            .attr("font-weight", "700")
            .text(d => (d.sentiment >= 0 ? "+" : "") + Number(d.sentiment).toFixed(2));

          // Update Macro Stats
          const statNodes = document.getElementById("stat-active-nodes");
          if (statNodes) statNodes.textContent = `${allNodes.length}`;
          const statEdges = document.getElementById("stat-active-edges");
          if (statEdges) statEdges.textContent = `${sankey.links.length}`;
          const statComm = document.getElementById("stat-active-communities");
          if (statComm) statComm.textContent = "3 Tiers";
          return;
        }

        const topics = data.topics;
        const actors = data.actors.slice(0, 50); // 50 aktor representatif untuk kenyamanan visual
        const edges = data.edges || [];

        // Left Column: Topics
        const topicColX = -850;
        const topicYSpacing = 220;
        const topicStartY = -((topics.length - 1) * topicYSpacing) / 2;
        const topicMap = new Map();

        topics.forEach((t, i) => {
          const ty = topicStartY + i * topicYSpacing;
          topicMap.set(t.id, { x: topicColX, y: ty, data: t });
        });

        // Right Column: Actors
        const actorColX = 850;
        const actorYSpacing = 36;
        const actorStartY = -((actors.length - 1) * actorYSpacing) / 2;
        const actorMap = new Map();

        actors.forEach((a, i) => {
          const ay = actorStartY + i * actorYSpacing;
          actorMap.set(a.id, { x: actorColX, y: ay, data: a });
        });

        // Ribbons / Links
        const linkG = bipartiteLayer.append("g").attr("class", "bipartite-links");
        const linkItems = linkG.selectAll("path")
          .data(edges.filter(e => topicMap.has(e.topic) && actorMap.has(e.actor)))
          .enter().append("path")
          .attr("class", "bipartite-edge")
          .attr("d", d => {
            const src = topicMap.get(d.topic);
            const tgt = actorMap.get(d.actor);
            const x1 = src.x + 160, y1 = src.y;
            const x2 = tgt.x - 70, y2 = tgt.y;
            const cx1 = x1 + 350, cy1 = y1;
            const cx2 = x2 - 350, cy2 = y2;
            return `M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`;
          })
          .attr("fill", "none")
          .attr("stroke", d => {
            if (d.sentiment > 0.05) return "#10B981";
            if (d.sentiment < -0.05) return "#EF4444";
            return "#38BDF8";
          })
          .attr("stroke-width", d => Math.max(1.0, Math.min(5.5, (d.npmi + 0.3) * 5.0)))
          .attr("stroke-opacity", 0.30)
          .style("cursor", "pointer")
          .on("mouseenter", function(event, d) {
            d3.select(this).attr("stroke-opacity", 0.95).attr("stroke-width", 4.0);
            if (nodeTooltipEl) {
              nodeTooltipEl.style.display = "block";
              nodeTooltipEl.innerHTML = `
                <div style="font-weight:800; font-size:11px; color:#F8FAFC; margin-bottom:4px;">${d.topic} ⟷ ${d.actor}</div>
                <div style="font-size:11px; color:#38BDF8;">NPMI: ${(d.npmi >= 0 ? "+" : "") + Number(d.npmi).toFixed(3)}</div>
                <div style="font-size:11px; color:${d.sentiment >= 0 ? '#10B981' : '#EF4444'};">Sentimen: ${(d.sentiment >= 0 ? "+" : "") + Number(d.sentiment).toFixed(2)}</div>
                <div style="font-size:11px; color:#94A3B8;">${d.article_count || 1} artikel berita</div>
              `;
              nodeTooltipEl.style.left = (event.pageX + 15) + "px";
              nodeTooltipEl.style.top = (event.pageY - 20) + "px";
            }
          })
          .on("mouseleave", function() {
            d3.select(this).attr("stroke-opacity", 0.30).attr("stroke-width", d => Math.max(1.0, Math.min(5.5, (d.npmi + 0.3) * 5.0)));
            if (nodeTooltipEl) nodeTooltipEl.style.display = "none";
          });

        // Topic Nodes (Left Column)
        const topicG = bipartiteLayer.append("g").attr("class", "bipartite-topics");
        const topicNodes = topicG.selectAll("g")
          .data(topics)
          .enter().append("g")
          .attr("transform", d => {
            const pos = topicMap.get(d.id);
            return `translate(${pos.x}, ${pos.y})`;
          })
          .style("cursor", "pointer")
          .on("mouseenter", (event, d) => {
            linkItems.attr("stroke-opacity", e => e.topic === d.id ? 0.90 : 0.04);
          })
          .on("mouseleave", () => {
            linkItems.attr("stroke-opacity", 0.30);
          });

        topicNodes.append("rect")
          .attr("x", -150).attr("y", -24)
          .attr("width", 300).attr("height", 48)
          .attr("rx", 8)
          .attr("fill", d => d.color || "#0284C7")
          .attr("fill-opacity", 0.22)
          .attr("stroke", d => d.color || "#38BDF8")
          .attr("stroke-width", 2.0);

        topicNodes.append("text")
          .attr("x", -135).attr("y", 4)
          .attr("fill", "#F8FAFC").attr("font-size", "12px").attr("font-weight", "800")
          .text(d => d.name || d.id);

        topicNodes.append("text")
          .attr("x", 135).attr("y", 4)
          .attr("text-anchor", "end")
          .attr("fill", "#38BDF8").attr("font-size", "10px").attr("font-weight", "700")
          .text(d => (d.article_count === undefined || d.article_count === null) ? "— art" : `${d.article_count} art`);

        // Actor Nodes (Right Column)
        const actorG = bipartiteLayer.append("g").attr("class", "bipartite-actors");
        const actorNodes = actorG.selectAll("g")
          .data(actors)
          .enter().append("g")
          .attr("transform", d => {
            const pos = actorMap.get(d.id);
            return `translate(${pos.x}, ${pos.y})`;
          })
          .style("cursor", "pointer")
          .on("mouseenter", (event, d) => {
            linkItems.attr("stroke-opacity", e => e.actor === d.id ? 0.95 : 0.04);
          })
          .on("mouseleave", () => {
            linkItems.attr("stroke-opacity", 0.30);
          })
          .on("click", (event, d) => {
            const realNode = nodeMap.get(d.id);
            if (realNode) selectAndInspectNode(realNode);
          });

        // Kartu aktor memakai peringkat simpul aslinya dari nodeMap, jadi
        // metrik ukuran yang dipilih di toolbar juga berlaku di mode ini.
        // Rentang 20..32 karena baris aktor hanya berjarak 36 piksel.
        const actorRankSource = (d) => nodeMap.get(d.id) || d;
        const actorCardH = (d) => cardHeight(actorRankSource(d), 26, 20, 32);
        actorNodes.append("rect")
          .attr("x", -60)
          .attr("y", d => -actorCardH(d) / 2)
          .attr("width", 170)
          .attr("height", d => actorCardH(d))
          .attr("rx", 4)
          .attr("fill", "rgba(15, 23, 42, 0.85)")
          .attr("stroke", d => d.color || "#8A99AE")
          .attr("stroke-width", 1.0);

        actorNodes.append("circle")
          .attr("cx", -48).attr("cy", 0)
          .attr("r", 5)
          .attr("fill", d => d.color || "#38BDF8");

        actorNodes.append("text")
          .attr("x", -36).attr("y", 3.5)
          .attr("fill", "#E2E8F0").attr("font-size", "9.5px").attr("font-weight", "700")
          .text(d => (d.name || d.id).slice(0, 18));

        // Update Macro Stats
        const statNodes = document.getElementById("stat-active-nodes");
        if (statNodes) statNodes.textContent = `${topics.length + actors.length}`;
        const statEdges = document.getElementById("stat-active-edges");
        if (statEdges) statEdges.textContent = `${edges.length}`;
        const statComm = document.getElementById("stat-active-communities");
        if (statComm) statComm.textContent = `${topics.length}`;
      };

      if (bipartiteDataCache) {
        renderData(bipartiteDataCache);
        return;
      }

      fetch("/api/topics/actor-network?t=" + Date.now())
        .then(res => res.ok ? res.json() : null)
        .then(data => {
          if (data && data.topics && data.topics.length) {
            bipartiteDataCache = data;
            renderData(data);
          } else {
            loadingText.text("Belum ada topik pada bundle ini.").attr("fill", "#94A3B8");
          }
        })
        .catch(err => {
          console.warn("[Bipartite Mode] Gagal memuat jaringan topik-aktor:", err);
          loadingText.text("Gagal memuat data bipartite.").attr("fill", "#EF4444");
        });
    }

    // -------------------------------------------------------------
    // Mode 03: Narrative & Temporal Diff Comparison
    // -------------------------------------------------------------
    function resetNodeTemporalDiff() {
      nodeG.each(function(d) {
        const isSun = d.id === EGO_ID;
        d3.select(this).select("circle.main-circle")
          .attr("stroke", "#FFFFFF")
          .attr("stroke-width", isSun ? 3.0 : (d.radius_tier === 1 ? 2.4 : (d.radius_tier === 2 ? 1.6 : 1.0)))
          .attr("stroke-dasharray", "none");
      });
    }

    // Angka hasil komparasi boleh nol, tetapi "tidak ada" bukan nol.
    function countOrDash(value) {
      return (value === undefined || value === null || Number.isNaN(Number(value))) ? "—" : value;
    }

    function runTemporalComparison() {
      const baseSel = document.getElementById("sel-compare-baseline");
      const tgtSel = document.getElementById("sel-compare-target");
      const basePeriod = baseSel ? baseSel.value : "";
      const tgtPeriod = tgtSel ? tgtSel.value : "";
      // Tanpa dua irisan waktu nyata tidak ada yang bisa dibandingkan.
      if (!basePeriod || !tgtPeriod) return;

      fetch(`/api/graph/compare?baseline=${encodeURIComponent(basePeriod)}&target=${encodeURIComponent(tgtPeriod)}`)
        .then(res => {
          if (!res.ok) throw new Error("HTTP " + res.status);
          return res.json();
        })
        .then(data => {
          if (!data) return;
          const gainedSet = new Set(data.nodes_gained || []);
          const lostSet = new Set(data.nodes_lost || []);

          nodeG.each(function(d) {
            const el = d3.select(this);
            const circle = el.select("circle.main-circle");
            if (gainedSet.has(d.id)) {
              // Gained actor: vivid pulsing green ring
              circle.attr("stroke", "#10B981")
                .attr("stroke-width", 3.8)
                .attr("stroke-dasharray", "none");
            } else if (lostSet.has(d.id)) {
              // Lost / exited actor: red dashed ring
              circle.attr("stroke", "#EF4444")
                .attr("stroke-width", 2.8)
                .attr("stroke-dasharray", "4, 3");
            } else {
              circle.attr("stroke", "#FFFFFF")
                .attr("stroke-width", 1.5)
                .attr("stroke-dasharray", "none");
            }
          });

          // Update macro stats
          const statNodes = document.getElementById("stat-active-nodes");
          if (statNodes) statNodes.textContent = `${countOrDash(data.gained_count)} Masuk / ${countOrDash(data.lost_count)} Keluar`;
          const statEdges = document.getElementById("stat-active-edges");
          if (statEdges) statEdges.textContent = `${countOrDash(data.persisted_count)} Pilar Tetap`;
          const statDens = document.getElementById("stat-active-density");
          if (statDens) statDens.textContent = `Δ Perbandingan: ${basePeriod.toUpperCase()} ➔ ${tgtPeriod.toUpperCase()}`;

          renderEpochDiff(data);
        })
        .catch(err => {
          console.warn("[Temporal Compare] Error:", err);
          // Kegagalan perbandingan tidak boleh tampil sebagai "0 masuk / 0 keluar".
          const statNodes = document.getElementById("stat-active-nodes");
          if (statNodes) statNodes.textContent = "\u2014";
          const statEdges = document.getElementById("stat-active-edges");
          if (statEdges) statEdges.textContent = "\u2014";
          const statDens = document.getElementById("stat-active-density");
          if (statDens) statDens.textContent = "Perbandingan gagal dimuat";
        });
    }

    // -------------------------------------------------------------
    // Diff epos: tabel berperingkat
    // -------------------------------------------------------------
    function entityLabel(entityId) {
      const node = allData.nodes.find(n => n.id === entityId);
      return (node && (node.display_label || node.label)) || entityId;
    }

    // Delta kosong berarti "tidak ada dua pengukuran", bukan nol.
    function deltaText(value, digits) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "\u2014";
      const number = Number(value);
      const sign = number > 0 ? "+" : "";
      return sign + number.toFixed(digits);
    }

    function deltaColor(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "#8A99AE";
      return Number(value) > 0 ? "#10B981" : (Number(value) < 0 ? "#EF4444" : "#8A99AE");
    }

    function communityCell(row, mapping) {
      if (row.baseline_community === null || row.baseline_community === undefined) {
        return "\u2014";
      }
      const target = (row.target_community === null || row.target_community === undefined)
        ? "\u2014" : row.target_community;
      // Label komunitas tidak bisa dibandingkan langsung; perpindahan hanya
      // ditandai bila pemetaan tumpang tindih mengatakannya berpindah. Tanpa
      // penjelasan, "1 → 1 pindah" terbaca seperti kesalahan.
      const mark = row.community_shifted ? ' <span style="color:#F59E0B;">pindah</span>' : "";
      const expected = mapping ? mapping[row.baseline_community] : null;
      const title = (row.community_shifted && expected !== null && expected !== undefined)
        ? `Mayoritas anggota komunitas ${row.baseline_community} berakhir di komunitas ${expected}; simpul ini tidak mengikutinya.`
        : "";
      return `<span title="${title}">${row.baseline_community} \u2192 ${target}${mark}</span>`;
    }

    function epochTable(rows, judul, mapping) {
      if (!rows || rows.length === 0) {
        return `<div style="margin-bottom:10px;"><strong>${judul}</strong>
          <div style="color:#8A99AE;">Tidak ada simpul yang bisa dibandingkan.</div></div>`;
      }
      const body = rows.map(row => `
        <tr>
          <td style="padding:4px 8px 4px 0;color:#CBD5E1;">${entityLabel(row.id)}</td>
          <td style="padding:4px 8px;color:${deltaColor(row.delta_betweenness)};font-weight:700;">${deltaText(row.delta_betweenness, 4)}</td>
          <td style="padding:4px 8px;color:#94A3B8;">${countOrDash(row.baseline_degree)} \u2192 ${countOrDash(row.target_degree)}</td>
          <td style="padding:4px 0;color:#94A3B8;">${communityCell(row, mapping)}</td>
        </tr>`).join("");
      return `
        <div style="margin-bottom:12px;">
          <div style="font-weight:800;color:#38BDF8;margin-bottom:4px;">${judul}</div>
          <table style="width:100%;border-collapse:collapse;font-size:11px;">
            <thead>
              <tr style="color:#8A99AE;text-align:left;">
                <th style="padding-bottom:4px;">Entitas</th>
                <th style="padding-bottom:4px;">ΔBetweenness</th>
                <th style="padding-bottom:4px;">Degree</th>
                <th style="padding-bottom:4px;">Komunitas</th>
              </tr>
            </thead>
            <tbody>${body}</tbody>
          </table>
        </div>`;
    }

    function edgeList(rows, judul, arah) {
      if (!rows || rows.length === 0) {
        return `<div><strong>${judul}</strong> <span style="color:#8A99AE;">tidak ada</span></div>`;
      }
      const items = rows.map(row =>
        `<div style="color:#CBD5E1;">${entityLabel(row.source)} ${arah} ${entityLabel(row.target)}
         <span style="color:#8A99AE;">(support ${countOrDash(row.support)}, NPMI ${formatNumber(row.npmi, 3)})</span></div>`
      ).join("");
      return `<div style="margin-bottom:8px;"><strong>${judul}</strong>${items}</div>`;
    }

    function renderEpochDiff(data) {
      const body = document.getElementById("epoch-diff-body");
      const subtitle = document.getElementById("epoch-diff-subtitle");
      const modal = document.getElementById("modal-epoch-diff");
      if (!body) return;

      if (!data || data.available === false) {
        body.textContent = (data && data.message) || "Perbandingan tidak tersedia (\u2014).";
        if (modal) modal.classList.add("open");
        return;
      }

      const agreement = data.community_agreement;
      const communityMapping = {};
      (data.community_map || []).forEach(item => {
        communityMapping[item.baseline] = item.target;
      });
      const agreementText = (agreement === null || agreement === undefined)
        ? "Kesepakatan komunitas: tidak ada simpul bertahan (\u2014)."
        : `Kesepakatan komunitas antar epos (ARI): <strong>${formatNumber(agreement, 4)}</strong>; ` +
          `${countOrDash(data.community_shifted_count)} simpul berpindah komunitas.`;

      if (subtitle) {
        subtitle.textContent =
          `${String(data.baseline_period).toUpperCase()} \u2192 ${String(data.target_period).toUpperCase()}: ` +
          `${countOrDash(data.gained_count)} masuk, ${countOrDash(data.lost_count)} keluar, ` +
          `${countOrDash(data.persisted_count)} bertahan.`;
      }

      body.innerHTML = `
        <div style="margin-bottom:10px;">${agreementText}</div>
        ${epochTable(data.top_gainers, "Betweenness naik", communityMapping)}
        ${epochTable(data.top_losers, "Betweenness turun", communityMapping)}
        <div style="border-top:1px solid rgba(255,255,255,0.08);padding-top:8px;">
          ${edgeList(data.edges_gained, `Sisi baru (${countOrDash(data.edges_gained_count)})`, "\u2194")}
          ${edgeList(data.edges_lost, `Sisi hilang (${countOrDash(data.edges_lost_count)})`, "\u2194")}
        </div>`;
      body.dataset.filled = "1";

      if (modal) modal.classList.add("open");
    }

    const btnRunCompare = document.getElementById("btn-run-comparison");
    const btnShowDiff = document.getElementById("btn-show-diff");
    if (btnShowDiff) {
      btnShowDiff.addEventListener("click", () => {
        const modal = document.getElementById("modal-epoch-diff");
        // Tanpa perbandingan sebelumnya, tombol ini tidak boleh membuka panel
        // kosong yang terbaca seperti "tidak ada yang berubah".
        const body = document.getElementById("epoch-diff-body");
        if (modal && body && body.dataset.filled === "1") modal.classList.add("open");
      });
    }
    if (btnRunCompare) {
      btnRunCompare.addEventListener("click", () => runTemporalComparison());
    }

    // -------------------------------------------------------------
    // Timeline Milestone Event Markers
