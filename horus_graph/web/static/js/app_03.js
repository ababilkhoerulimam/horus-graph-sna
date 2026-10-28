    // -------------------------------------------------------------
    // Serializer hanya mengirim blok `sentiment` bila lapisan sentimen ada di
    // bundle. Semua konsumen lewat sini supaya tidak ada lagi angka cadangan:
    // tanpa lapisan, hasilnya null dan panel wajib menampilkan status kosong.
    function nodeSentiment(node) {
      const block = node && node.sentiment;
      if (!block || block.status !== "ready") return null;
      // Null dan string kosong harus ditolak sebelum Number(): Number(null)
      // dan Number("") sama-sama 0, dan 0 terbaca sebagai "terukur netral".
      if (block.pos === null || block.pos === undefined
          || block.neu === null || block.neu === undefined
          || block.neg === null || block.neg === undefined) return null;
      const pos = Number(block.pos);
      const neu = Number(block.neu);
      const neg = Number(block.neg);
      if (!Number.isFinite(pos) || !Number.isFinite(neu) || !Number.isFinite(neg)) return null;
      const stance = (block.stance === null || block.stance === undefined)
        ? (pos - neg) / 100
        : Number(block.stance);
      if (!Number.isFinite(stance)) return null;
      return { pos, neu, neg, stance, confidence: block.confidence, method: block.method };
    }

    // Status lapisan sentimen menurut manifest, bukan menurut ada-tidaknya field.
    function sentimentLayerStatus() {
      const layers = (BOOTSTRAP && BOOTSTRAP.dataset && BOOTSTRAP.dataset.layers) || {};
      return layers.sentiment || "awaiting_input";
    }

    function sentimentUnavailableLabel() {
      return sentimentLayerStatus() === "awaiting_input"
        ? "Lapisan sentimen belum tersedia (awaiting_input)"
        : "Sentimen tidak tersedia untuk simpul ini";
    }

    function inspectEdgeDetails(d) {
      if (window.copilotUI && typeof window.copilotUI.closeDrawer === "function") {
        window.copilotUI.closeDrawer();
      }
      const nodeDrawer = document.getElementById("node-drawer");
      if (nodeDrawer) nodeDrawer.style.display = "none";
      const tracer = document.getElementById("tracer-drawer");
      if (tracer) tracer.style.display = "none";

      const edgeDrawer = document.getElementById("edge-evidence-drawer");
      if (edgeDrawer) edgeDrawer.style.display = "block";

      const sId = getSourceId(d), tId = getTargetId(d);
      const titleEl = document.getElementById("edge-evidence-title");
      if (titleEl) titleEl.textContent = `${sId} ⟷ ${tId}`;

      const relLabels = {
        "ego_club_affiliation": "Relasi Afiliasi Klub",
        "teammate_or_tactical_pair": "Kemitraan Taktis Skuad",
        "inter_club_rivalry": "Rivalitas Antar-Klub",
        "media_wire_transmission": "Sindikasi Kawat Media",
        "media_coverage_focus": "Fokus Liputan Media",
        "contextual_cooccurrence": "Ko-okurensi Kontekstual"
      };
      const typeEl = document.getElementById("edge-evidence-type");
      if (typeEl) typeEl.textContent = relLabels[d.relation_type] || d.category_label || d.edge_category || "Relasi";

      const DASH = "\u2014";
      const fmt = (value, digits) => (value === undefined || value === null || Number.isNaN(Number(value)))
        ? DASH
        : Number(value).toFixed(digits);

      // Semua angka diambil dari objek sisi yang sudah ada di kanvas. Route
      // bukti hanya menambah daftar artikel, jadi tidak ada lagi nilai cadangan
      // yang tampil sebagai hasil ukur.
      const sig = d.significance || {};
      const npmiVal = d.npmi !== undefined ? d.npmi : sig.npmi;
      const edgeValence = (d.sentiment_valence !== undefined) ? d.sentiment_valence : sig.sentiment_valence;

      const valBadge = document.getElementById("edge-evidence-valence-badge");
      if (valBadge) {
        if (edgeValence === undefined || edgeValence === null) {
          // Valensi hanya bermakna bila lapisan sentimen ada.
          valBadge.textContent = "";
        } else {
          valBadge.textContent = `Valensi: ${(edgeValence >= 0 ? "+" : "") + Number(edgeValence).toFixed(2)}`;
          valBadge.style.color = edgeValence >= 0 ? "#10B981" : "#EF4444";
        }
      }

      const npmiEl = document.getElementById("edge-metric-npmi");
      if (npmiEl) npmiEl.textContent = (npmiVal === undefined || npmiVal === null)
        ? DASH : (npmiVal >= 0 ? "+" : "") + Number(npmiVal).toFixed(3);
      const saltonEl = document.getElementById("edge-metric-salton");
      if (saltonEl) saltonEl.textContent = fmt(d.salton_cosine, 3);
      const jaccardEl = document.getElementById("edge-metric-jaccard");
      if (jaccardEl) jaccardEl.textContent = fmt(d.jaccard, 3);
      const weightEl = document.getElementById("edge-metric-weight");
      if (weightEl) weightEl.textContent = (d.weight === undefined || d.weight === null)
        ? DASH : `${d.weight} artikel`;

      const snippetsWrap = document.getElementById("edge-evidence-snippets-wrap");
      const countEl = document.getElementById("edge-evidence-sample-count");
      if (snippetsWrap) {
        snippetsWrap.innerHTML = '<div style="font-size:11px; color:#8A99AE; font-style:italic; padding:6px 0;">Memuat bukti kutipan berita...</div>';
      }
      if (countEl) countEl.textContent = "";

      const fail = (message) => {
        if (countEl) countEl.textContent = "Gagal";
        if (snippetsWrap) {
          snippetsWrap.innerHTML = `<div style="font-size:11px; color:#F87171; font-style:italic; padding:6px 0;">${message}</div>`;
        }
      };

      fetch(`/api/edges/evidence?source=${encodeURIComponent(sId)}&target=${encodeURIComponent(tId)}`)
        .then(res => {
          if (!res.ok) {
            // 404 di sini berarti sisi tidak ada di jaringan, bukan alasan
            // untuk menampilkan panel kosong tanpa penjelasan.
            throw new Error(res.status === 404 ? "Sisi ini tidak ada di jaringan bundle." : "HTTP " + res.status);
          }
          return res.json();
        })
        .then(data => {
          if (!snippetsWrap) return;
          const snips = Array.isArray(data.evidence) ? data.evidence : [];
          if (countEl) countEl.textContent = `${snips.length} Cuplikan`;

          if (snips.length === 0) {
            snippetsWrap.innerHTML = '<div style="font-size:11px; color:#8A99AE; font-style:italic;">Tidak ada artikel yang menyebut kedua entitas ini.</div>';
            return;
          }

          snippetsWrap.innerHTML = "";
          snips.forEach(sn => {
            const card = document.createElement("div");
            card.className = "headline-item";
            card.style.cssText = "margin-bottom:6px; padding:6px 8px; background:rgba(255,255,255,0.03); border-radius:4px; border-left:2px solid #38BDF8;";
            const title = document.createElement("div");
            title.style.cssText = "font-weight:700; color:#F8FAFC; font-size:11px; margin-bottom:2px;";
            title.textContent = sn.title || "(tanpa judul)";
            const meta = document.createElement("div");
            meta.style.cssText = "font-size:11px; color:#8A99AE; margin-top:3px; display:flex; justify-content:space-between; gap:6px;";
            const site = document.createElement("span");
            site.textContent = sn.site || DASH;
            const date = document.createElement("span");
            date.textContent = (sn.published_at || "").slice(0, 10) || DASH;
            meta.append(site, date);
            card.append(title, meta);
            if (sn.url) {
              const link = document.createElement("a");
              link.href = sn.url;
              link.target = "_blank";
              link.rel = "noopener noreferrer";
              link.textContent = "Buka artikel";
              link.style.cssText = "font-size:11px; color:#38BDF8; text-decoration:none;";
              card.appendChild(link);
            }
            snippetsWrap.appendChild(card);
          });
        })
        .catch(err => {
          console.warn("[Edge Evidence] Gagal memuat kutipan:", err);
          fail(err && err.message ? err.message : "Bukti kutipan tidak dapat dimuat.");
        });
    }

    const btnCloseEdge = document.getElementById("btn-close-edge-drawer");
    if (btnCloseEdge) {
      btnCloseEdge.addEventListener("click", () => {
        const edgeDrawer = document.getElementById("edge-evidence-drawer");
        if (edgeDrawer) edgeDrawer.style.display = "none";
      });
    }

    function deactivateNodes() {
      lockedNode = null;
      resetNodeHighlight();
    }

    function populateDrawerDetails(d) {
      if (window.copilotUI && typeof window.copilotUI.closeDrawer === "function") {
        window.copilotUI.closeDrawer();
      }
      const edgeDrawer = document.getElementById("edge-evidence-drawer");
      if (edgeDrawer) edgeDrawer.style.display = "none";
      const drawer = document.getElementById("node-drawer");
      drawer.style.display = "block";
      const tracer = document.getElementById("tracer-drawer");
      if (tracer) tracer.style.display = "none";

      document.getElementById("drawer-name").textContent = d.display_label || d.label || d.id;
      // Catatan menempel pada entitas, bukan pada simpul kanvas: id yang
      // dipakai adalah id entitas, sama dengan yang dipakai API.
      currentNoteTarget = d.id;
      renderNodeNotes(d.id);
      const typeEl = document.getElementById("drawer-type");
      typeEl.textContent = d.entity_type;
      typeEl.style.backgroundColor = (d.color || "#7C3AED") + "22";
      typeEl.style.color = d.color || "#7C3AED";

      // Populate Role Summary & Recent Changes
      const roleSumBox = document.getElementById("drawer-role-summary-box");
      if (roleSumBox) {
        let roleSum = d.role_summary;
        if (!roleSum) {
          // Kalimat peran berasal dari presentation.action_rules; {label} dan
          // {type} diganti di sini. Tidak ada nama domain di kode.
          const rules = (PRESENTATION && PRESENTATION.action_rules) || {};
          const key = d.is_ego ? "ego" : (rules[d.entity_type] ? d.entity_type : "default");
          const rule = rules[key];
          if (rule && rule.body) {
            roleSum = rule.body
              .replace(/\{label\}/g, d.label || d.id)
              .replace(/\{type\}/g, typeLabel(d.entity_type) || d.entity_type || "");
          } else {
            roleSum = `${d.label || d.id} — ${typeLabel(d.entity_type) || d.entity_type || ""}`;
          }
        }
        roleSumBox.textContent = roleSum;
      }

      const recentChgBox = document.getElementById("drawer-recent-changes-box");
      if (recentChgBox) {
        let recentChg = d.recent_changes;
        if (!recentChg) {
          const years = (d.active_years || []).slice().sort();
          recentChg = years.length
            ? `Aktif pada ${years[0]}-${years[years.length - 1]} (${years.length} tahun terpantau).`
            : "Tidak ada aktivitas bertanggal pada korpus ini.";
        }
        recentChgBox.textContent = recentChg;
      }

      // Sektor & Louvain Cluster Meta
      const clusterMetaEl = document.getElementById("drawer-cluster-meta");
      if (clusterMetaEl) {
        const clusterLabels = {};
        ((PRESENTATION && PRESENTATION.clusters) || []).forEach(c => {
          clusterLabels[c.id] = c.label || c.id;
        });
        const cLabel = clusterLabels[d.cluster] || d.cluster || labelOf("cluster", "Klaster");
        const commLabel = d.louvain_community_label || (d.louvain_community ? `Komunitas #${d.louvain_community}` : "");
        // Stabilitas dibaca dari payload apa adanya: simpul tanpa rekan
        // komunitas mengirim null, dan itu bukan "stabil sempurna".
        const stab = (typeof d.community_stability === "number")
          ? ` \u00b7 stabil ${d.community_stability.toFixed(2)}`
          : "";
        clusterMetaEl.textContent = commLabel
          ? `• ${cLabel} (${commLabel}${stab})`
          : `• ${cLabel}`;
      }

      // Panel metrik hanya menampilkan yang benar-benar dikirim serializer.
      // Nilai cadangan dihapus: angka contoh terbaca sebagai hasil analisis.
      const DASH = "\u2014";
      document.getElementById("drawer-comm").textContent = d.orbit_label || DASH;

      const m = d.metrics || {};
      const sent = nodeSentiment(d);
      // `corpus_sample_n` tidak pernah dikirim serializer; `articles` adalah
      // jumlah artikel yang benar-benar menyebut entitas ini.
      const sampN = [m.corpus_sample_n, d.articles, d.size]
        .find(v => v !== undefined && v !== null);
      const sampLabel = sampN === undefined ? null : Number(sampN).toLocaleString("id-ID");
      // Keyakinan hanya bermakna bila lapisan sentimen ada.
      const conf = sent && sent.confidence !== null && sent.confidence !== undefined
        ? Number(sent.confidence).toFixed(2)
        : "";
      const volumeEl = document.getElementById("drawer-volume");
      if (sampLabel === null) {
        volumeEl.textContent = DASH;
      } else {
        volumeEl.textContent = conf ? `${sampLabel} artikel (${conf})` : `${sampLabel} artikel`;
      }

      const deg = (m.degree !== undefined && m.degree !== null) ? m.degree : null;
      document.getElementById("drawer-degree").textContent = deg === null ? DASH : `${deg} koneksi (Undirected)`;

      const pr = (m.pagerank !== undefined && m.pagerank !== null) ? Number(m.pagerank).toFixed(4) : null;
      const bw = (m.betweenness !== undefined && m.betweenness !== null) ? Number(m.betweenness).toFixed(4) : null;
      document.getElementById("drawer-betweenness").textContent =
        (pr === null && bw === null) ? DASH : `PR: ${pr === null ? DASH : pr} | BW: ${bw === null ? DASH : bw}`;

      // Histogram tahunan. `metrics_by_year` tidak pernah dikirim serializer,
      // jadi tanpa cabang kedua setiap tahun akan tampil "0 artikel" — angka
      // karangan. `active_years` adalah data nyata dari artikel bertanggal.
      const yearHistWrap = document.getElementById("drawer-year-histogram");
      const yearTitleRow = document.getElementById("drawer-year-title-row");
      const yearTitle = document.getElementById("drawer-year-title");
      if (yearHistWrap) {
        yearHistWrap.innerHTML = "";
        const yearsList = timelineYears().filter(y => y !== null).map(y => String(y));
        const mYears = m.metrics_by_year;
        const activeYears = new Set((d.active_years || []).map(y => String(y)));
        // Mode volume hanya bila seluruh tahun punya angka; mode kehadiran
        // hanya bila ada active_years; selain itu panel disembunyikan.
        const hasVolume = mYears && yearsList.some(y => mYears[y] && mYears[y].articles !== undefined);
        const hasPresence = activeYears.size > 0;
        if (!hasVolume && !hasPresence) {
          if (yearTitleRow) yearTitleRow.style.display = "none";
          yearHistWrap.style.display = "none";
        } else {
          if (yearTitleRow) yearTitleRow.style.display = "";
          yearHistWrap.style.display = "";
          if (yearTitle) yearTitle.textContent = hasVolume ? "Tren Volume Artikel Tahunan" : "Tahun Aktif Entitas";
          const yearData = yearsList.map(y => ({
            year: y,
            count: hasVolume ? (mYears[y]?.articles ?? 0) : null,
            active: hasVolume ? (mYears[y]?.articles ?? 0) > 0 : activeYears.has(y)
          }));
          const maxArticles = Math.max(1, ...yearData.map(yd => yd.count || 0));

          const histContainer = document.createElement("div");
          histContainer.style.cssText = "display:flex; justify-content:space-between; align-items:flex-end; height:52px; padding:6px 8px; background:var(--bg-card); border:1px solid var(--border-subtle); border-radius:6px; gap:4px;";

          yearData.forEach(yd => {
            const barHeightPct = hasVolume
              ? Math.max(8, Math.round(((yd.count || 0) / maxArticles) * 100))
              : (yd.active ? 100 : 8);
            const colEl = document.createElement("div");
            colEl.style.cssText = "display:flex; flex-direction:column; align-items:center; flex:1; height:100%; justify-content:flex-end; gap:3px;";
            colEl.title = hasVolume
              ? `Tahun ${yd.year}: ${yd.count.toLocaleString("id-ID")} artikel`
              : `Tahun ${yd.year}: ${yd.active ? "aktif" : "tidak ada sebutan"}`;
            const head = hasVolume
              ? (yd.count > 999 ? (yd.count / 1000).toFixed(1) + "k" : String(yd.count))
              : (yd.active ? "\u25CF" : "");
            colEl.innerHTML = `
              <div style="font-size:11px; font-weight:800; color:${yd.active ? '#38BDF8' : '#8A99AE'};">${head}</div>
              <div style="width:100%; max-width:18px; height:${barHeightPct}%; background:${yd.active ? 'linear-gradient(to top, #0284C7, #38BDF8)' : 'rgba(255,255,255,0.06)'}; border-radius:2px 2px 0 0;"></div>
              <div style="font-size:11px; font-weight:700; color:#94A3B8;">${yd.year.slice(2)}</div>
            `;
            histContainer.appendChild(colEl);
          });
          yearHistWrap.appendChild(histContainer);
        }
      }

      // Sentiment bar. Bar dan stance hanya muncul bila lapisan sentimen ada;
      // sebelumnya blok ini mengarang Pos 14 / Neu 83 / Neg 3.
      const sentTrack = document.querySelector(".sentiment-bar-track");
      const sentLegend = document.querySelector(".sent-legend");
      const stanceEl = document.getElementById("drawer-stance-score");
      const negTotalEl = document.getElementById("drawer-neg-total-badge");

      if (sent) {
        if (sentTrack) sentTrack.style.display = "";
        if (sentLegend) sentLegend.style.display = "";
        document.getElementById("sent-bar-pos").style.width = sent.pos + "%";
        document.getElementById("sent-bar-neu").style.width = sent.neu + "%";
        document.getElementById("sent-bar-neg").style.width = sent.neg + "%";
        document.getElementById("sent-lbl-pos").textContent = "Pos " + sent.pos + "%";
        document.getElementById("sent-lbl-neu").textContent = "Neu " + sent.neu + "%";
        document.getElementById("sent-lbl-neg").textContent = "Neg " + sent.neg + "%";
        const stanceText = (sent.stance >= 0 ? "+" : "") + sent.stance.toFixed(2);
        stanceEl.textContent = stanceText + " Stance";
        stanceEl.style.color = sent.stance >= 0 ? "#16A34A" : "#DC2626";
        if (negTotalEl) negTotalEl.textContent = "Total Negatif: " + sent.neg + "%";
      } else {
        if (sentTrack) sentTrack.style.display = "none";
        if (sentLegend) sentLegend.style.display = "none";
        stanceEl.textContent = sentimentLayerStatus() === "awaiting_input" ? "awaiting_layer" : DASH;
        stanceEl.style.color = "var(--text-muted)";
        if (negTotalEl) negTotalEl.textContent = DASH;
      }

      // Negative Drivers
      const driversWrap = document.getElementById("drawer-neg-drivers");
      driversWrap.innerHTML = "";
      const drivers = m.negative_drivers || [];
      if (drivers.length === 0) {
        driversWrap.innerHTML = sent
          ? '<div style="font-size:11px; color:var(--text-dim); font-style:italic;">Tidak ada anomali sentimen negatif signifikan.</div>'
          : `<div style="font-size:11px; color:var(--text-dim); font-style:italic;">${sentimentUnavailableLabel()}.</div>`;
      } else {
        drivers.forEach(dr => {
          const card = document.createElement("div");
          card.className = "neg-driver-card";
          card.innerHTML = `
            <div class="neg-driver-header" style="display:flex; justify-content:space-between; font-size:11px;">
              <span style="font-weight:700; color:#F8FAFC;"># ${dr.topic}</span>
              <span style="font-weight:800; color:#FCA5A5;">${dr.impact_pct}% porsi</span>
            </div>
            <div style="width:100%; height:3px; background:rgba(255,255,255,0.08); border-radius:2px; margin-top:4px; overflow:hidden;">
              <div style="width:${Math.min(100, dr.impact_pct)}%; height:100%; background:#EF4444; border-radius:2px;"></div>
            </div>
          `;
          driversWrap.appendChild(card);
        });
      }

      // Tactical Recommendation. Bila artefak tak memuat blok taktis, panel
      // menampilkan garis kosong, bukan prioritas/peran rekaan.
      const tact = d.tactical || {};
      const hasTactical = Object.keys(tact).length > 0;
      const tactSection = document.getElementById("drawer-tactical-section");
      if (tactSection) tactSection.style.display = hasTactical ? "" : "none";
      const priorityEl = document.getElementById("drawer-tactical-priority");
      const hasPriority = !!tact.priority;
      priorityEl.textContent = hasPriority ? tact.priority : DASH;
      priorityEl.style.backgroundColor = !hasPriority ? "rgba(148,163,184,0.15)"
        : (tact.priority === "CRITICAL" ? "rgba(239, 68, 68, 0.2)" : (tact.priority === "HIGH" ? "rgba(249, 115, 22, 0.2)" : "rgba(14, 165, 233, 0.2)"));
      priorityEl.style.color = !hasPriority ? "var(--text-muted)"
        : (tact.priority === "CRITICAL" ? "#EF4444" : (tact.priority === "HIGH" ? "#F97316" : "#38BDF8"));

      document.getElementById("drawer-tactical-role").textContent = tact.role || DASH;
      document.getElementById("drawer-tactical-rank").textContent = tact.rank ? `Rank #${tact.rank}` : "";

      const actBadge = document.getElementById("drawer-tactical-action-badge");
      if (actBadge) {
        const hasAction = !!tact.action;
        actBadge.textContent = hasAction ? tact.action.replace(/_/g, " ") : DASH;
        actBadge.style.background = hasAction ? "rgba(56, 189, 248, 0.15)" : "rgba(148,163,184,0.15)";
        actBadge.style.color = hasAction ? "#38BDF8" : "var(--text-muted)";
      }
      document.getElementById("drawer-tactical-justification").textContent = tact.justification || "";

      // Ronald Burt (1992) Structural Holes Metrics
      const burtConstraintRaw = (m.burt_constraint !== undefined && m.burt_constraint !== null)
        ? m.burt_constraint
        : (d.burt_constraint !== undefined && d.burt_constraint !== null ? d.burt_constraint : null);
      const effectiveSizeRaw = (m.effective_size !== undefined && m.effective_size !== null)
        ? m.effective_size
        : (d.effective_size !== undefined && d.effective_size !== null ? d.effective_size : null);
      const burtConstraint = burtConstraintRaw === null ? null : Number(burtConstraintRaw).toFixed(4);
      const effectiveSize = effectiveSizeRaw === null ? null : Number(effectiveSizeRaw).toFixed(2);
      // null, bukan NaN: NaN membuat semua perbandingan di bawah bernilai false
      // dan badge diam-diam mempertahankan teks dari markup.
      const cNum = burtConstraint === null ? null : Number(burtConstraint);

      const burtRoleBadge = document.getElementById("drawer-burt-role-badge");
      const burtConstraintEl = document.getElementById("drawer-burt-constraint");
      const burtEsEl = document.getElementById("drawer-burt-es");
      const burtDescEl = document.getElementById("drawer-burt-desc");

      if (burtRoleBadge) {
        if (cNum === null) {
          burtRoleBadge.textContent = DASH;
          burtRoleBadge.style.background = "rgba(148, 163, 184, 0.15)";
          burtRoleBadge.style.color = "var(--text-muted)";
          if (burtDescEl) burtDescEl.textContent = "Artefak tidak memuat metrik structural holes untuk simpul ini.";
        } else if (cNum < 0.25) {
          burtRoleBadge.textContent = "HIGH AUTONOMY (TERTIUS)";
          burtRoleBadge.style.background = "rgba(16, 185, 129, 0.2)";
          burtRoleBadge.style.color = "#10B981";
          if (burtDescEl) burtDescEl.textContent = "Tertius Gaudens Broker: Memiliki otonomi struktural tinggi menjembatani klaster terputus tanpa redundansi informasi.";
        } else if (cNum <= 0.45) {
          burtRoleBadge.textContent = "BALANCED BRIDGE";
          burtRoleBadge.style.background = "rgba(56, 189, 248, 0.2)";
          burtRoleBadge.style.color = "#38BDF8";
          if (burtDescEl) burtDescEl.textContent = "Balanced Bridge: Menghubungkan beberapa kelompok dengan ketergantungan relasional seimbang.";
        } else {
          burtRoleBadge.textContent = "EMBEDDED CLIQUE";
          burtRoleBadge.style.background = "rgba(148, 163, 184, 0.2)";
          burtRoleBadge.style.color = "#94A3B8";
          if (burtDescEl) burtDescEl.textContent = "Embedded Clique: Keterikatan tinggi dalam kelompok tertutup dengan saluran komunikasi berulang.";
        }
      }
      if (burtConstraintEl) burtConstraintEl.textContent = burtConstraint === null ? DASH : burtConstraint;
      if (burtEsEl) burtEsEl.textContent = effectiveSize === null ? DASH : effectiveSize;

      // Populate Executive PR Risk & Action Card
      const actionCardEl = document.getElementById("drawer-action-card");
      const actionTitleEl = document.getElementById("drawer-action-title");
      const actionBadgeEl = document.getElementById("drawer-action-badge");
      const actionDescEl = document.getElementById("drawer-action-desc");

      if (actionCardEl && actionTitleEl && actionDescEl && actionBadgeEl) {
        // Aturan tindakan bersifat struktural (media / constraint tinggi /
        // otonom / seimbang); kalimatnya datang dari presentation.action_rules.
        // Tanpa metrik struktural tidak ada dasar memilih aturan mana pun.
        const rules = (PRESENTATION && PRESENTATION.action_rules) || {};
        const isMedia = (typeLabel(d.entity_type) || "").toLowerCase() === "source";
        if (cNum === null && !isMedia) {
          actionBadgeEl.textContent = DASH;
          actionBadgeEl.style.background = "rgba(148,163,184,0.15)";
          actionBadgeEl.style.color = "var(--text-muted)";
          actionCardEl.style.borderLeftColor = "var(--border-subtle)";
          actionTitleEl.textContent = DASH;
          actionDescEl.textContent = "Metrik struktural simpul ini tidak tersedia di bundle.";
        } else {
          const roleKey = isMedia ? "media" : (cNum > 0.45 ? "dependent" : (cNum < 0.25 ? "broker" : "default"));
          const rule = rules[roleKey] || {};
          const tone = {
            media: "#EA580C", dependent: "#EF4444", broker: "#10B981", default: "#38BDF8"
          }[roleKey];
          actionBadgeEl.textContent = rule.badge || roleKey.toUpperCase();
          actionBadgeEl.style.background = hexToRgba(tone, 0.2);
          actionBadgeEl.style.color = tone;
          actionCardEl.style.borderLeftColor = tone;
          actionTitleEl.textContent = fillTemplate(rule.title, d, sampLabel) || (d.label || d.id);
          actionDescEl.textContent = fillTemplate(rule.body, d, sampLabel) || "";
        }
      }

      // Causal Driver & 2-Hop Path Annotation
      const causalActorEl = document.getElementById("drawer-causal-actor");
      const causalRoleEl = document.getElementById("drawer-causal-role");
      const causalChainEl = document.getElementById("drawer-causal-chain");
      const causalBadgeEl = document.getElementById("drawer-causal-badge");

      if (causalActorEl) {
        // Semua kalimat berasal dari presentation.wording; rantai dibentuk dari
        // ego opsional, jadi dataset tanpa pusat tetap punya jalur yang benar.
        const wording = (PRESENTATION && PRESENTATION.wording) || {};
        const egoMeta = (PRESENTATION && PRESENTATION.ego) || null;
        const centreName = egoMeta ? (egoMeta.label || egoMeta.id) : "";
        const nodeLabel = d.label || d.id;
        const pathTo = (actor, target) => (centreName
          ? `[${actor}] ➔ [${centreName}] ➔ [${target}]`
          : `[${actor}] ➔ [${target}]`);

        if (d.causal_driver_actor && d.causal_driver_actor !== EGO_ID) {
          if (causalBadgeEl) {
            causalBadgeEl.textContent = wording.causal_mediated || "MEDIASI AKTOR";
            causalBadgeEl.style.background = "rgba(245, 158, 11, 0.2)";
            causalBadgeEl.style.color = "#F59E0B";
          }
          causalActorEl.textContent = d.causal_driver_actor;
          causalRoleEl.textContent = d.causal_driver_role || "Aktor pemicu utama dalam relasi sebab-akibat.";
          causalChainEl.textContent = pathTo(d.causal_driver_actor, nodeLabel);
        } else if (d.is_causal_driver && d.driven_entities && d.driven_entities.length > 0) {
          if (causalBadgeEl) {
            causalBadgeEl.textContent = wording.causal_driver || "AKTOR PENGGERAK";
            causalBadgeEl.style.background = "rgba(16, 185, 129, 0.2)";
            causalBadgeEl.style.color = "#10B981";
          }
          causalActorEl.textContent = nodeLabel;
          causalRoleEl.textContent = fillTemplate(
            wording.causal_driver_role,
            d
          ) || `Aktor kunci yang menggerakkan ${d.driven_entities.length} entitas terkait.`;
          const sampleDriven = d.driven_entities.slice(0, 3).join(", ");
          const moreText = d.driven_entities.length > 3 ? "..." : "";
          causalChainEl.textContent = pathTo(nodeLabel, `${sampleDriven}${moreText}`);
        } else if (EGO_ID && d.id === EGO_ID) {
          if (causalBadgeEl) {
            causalBadgeEl.textContent = wording.causal_core || "POROS";
            causalBadgeEl.style.background = "rgba(56, 189, 248, 0.2)";
            causalBadgeEl.style.color = "#38BDF8";
          }
          causalActorEl.textContent = nodeLabel;
          causalRoleEl.textContent = wording.causal_core_role || "Titik pusat yang menghubungkan aktor dan pihak terkait.";
          causalChainEl.textContent = centreName
            ? `[${wording.causal_actor_placeholder || "Aktor"}] ➔ [${centreName}] ➔ [${wording.causal_target_placeholder || "Terkait"}]`
            : nodeLabel;
        } else {
          if (causalBadgeEl) {
            causalBadgeEl.textContent = wording.causal_anchor || "JANGKAR";
            causalBadgeEl.style.background = "rgba(148, 163, 184, 0.2)";
            causalBadgeEl.style.color = "#94A3B8";
          }
          causalActorEl.textContent = d.causal_driver_actor || nodeLabel;
          causalRoleEl.textContent = d.causal_driver_role || "Simpul jangkar pada jaringan ini.";
          causalChainEl.textContent = centreName
            ? `[${nodeLabel}] ➔ [${centreName}]`
            : `[${nodeLabel}]`;
        }
      }

      // Dynamic Neighbors from allData.links (Fixed empty neighbors bug)
      const chipsWrap = document.getElementById("drawer-neighbors-wrap");
      chipsWrap.innerHTML = "";
      
      const connectedEdges = allData.links.filter(l => getSourceId(l) === d.id || getTargetId(l) === d.id);
      connectedEdges.sort((a, b) => (b.weight || 0) - (a.weight || 0));
      const topNeighbors = connectedEdges.slice(0, 8);

      if (topNeighbors.length === 0) {
        chipsWrap.innerHTML = '<div style="font-size:11px; color:var(--text-dim); font-style:italic;">Tidak ada entitas terhubung aktif.</div>';
      } else {
        topNeighbors.forEach(edge => {
          const s = getSourceId(edge), t = getTargetId(edge);
          const neighborId = (s === d.id) ? t : s;
          const otherNode = nodeMap.get(neighborId);
          const col = otherNode ? otherNode.color : "#38BDF8";
          const label = otherNode ? (otherNode.display_label || otherNode.label) : neighborId;
          const w = edge.weight ? edge.weight.toLocaleString("id-ID") : "1";

          const chip = document.createElement("div");
          chip.className = "neighbor-chip";
          chip.style.cssText = "display:inline-flex; align-items:center; gap:5px; background:var(--bg-card); border:1px solid var(--border-subtle); border-radius:4px; padding:3px 7px; font-size:11px; color:var(--text-main); cursor:pointer; transition:border-color 0.15s;";
          chip.title = `Klik untuk fokus ke ${label} (${w} artikel bersama)`;
          chip.innerHTML = `<span class="chip-dot" style="background:${col}; width:7px; height:7px; border-radius:50%; flex-shrink:0;"></span><span style="max-width:125px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${label}</span><span style="font-size:11px; color:#94A3B8; font-weight:800; margin-left:auto;">${w}</span>`;
          chip.addEventListener("click", () => {
            if (otherNode) {
              selectAndInspectNode(otherNode);
            }
          });
          chipsWrap.appendChild(chip);
        });
      }

      // Headlines
      const headlinesWrap = document.getElementById("drawer-headlines-wrap");
      headlinesWrap.innerHTML = "";
      (m.headlines || []).forEach(hl => {
        const item = document.createElement("div");
        item.className = "headline-item";
        item.textContent = '"' + hl + '"';
        headlinesWrap.appendChild(item);
      });
    }

    document.getElementById("drawer-close").addEventListener("click", (e) => {
      e.stopPropagation();
      document.getElementById("node-drawer").style.display = "none";
      lockedNode = null;
      deactivateNodes();
    });

    document.getElementById("btn-focus-node").addEventListener("click", () => {
      if (lockedNode) {
        zoomToNode(lockedNode, 500);
      }
    });

    document.getElementById("btn-close-focus").addEventListener("click", () => {
      lockedNode = null;
      deactivateNodes();
      document.getElementById("node-drawer").style.display = "none";
      svg.transition().duration(400).call(resetGraphView);
    });

    // Dock Controls
    document.getElementById("btn-fit").addEventListener("click", () => {
      svg.transition().duration(400).call(resetGraphView);
    });

    document.getElementById("btn-in").addEventListener("click", () => {
      svg.transition().duration(200).call(zoom.scaleBy, 1.25);
    });

    document.getElementById("btn-out").addEventListener("click", () => {
      svg.transition().duration(200).call(zoom.scaleBy, 0.80);
    });



    const btnFullscreen = document.getElementById("btn-dock-fullscreen");
    if (btnFullscreen) {
      btnFullscreen.addEventListener("click", () => {
        if (!document.fullscreenElement) {
          document.documentElement.requestFullscreen().catch(() => {});
        } else {
          if (document.exitFullscreen) document.exitFullscreen().catch(() => {});
        }
      });
    }

    const btnHeaderFilter = document.getElementById("btn-header-filter");
    if (btnHeaderFilter) {
      btnHeaderFilter.addEventListener("click", () => {
        const sbBtn = document.getElementById("btn-toggle-sidebar");
        if (sbBtn) sbBtn.click();
      });
    }

    let currentLayoutMode = "topological"; // Default Mode 2: Topological SNA
    let simulation = null;

    function buildSimLinks(edges) {
      return (edges || []).map(l => ({
        source: getSourceId(l),
        target: getTargetId(l),
        weight: l.weight || 10,
        npmi: l.npmi || 0.1
      }));
    }

    function initForceSimulation() {
      if (typeof d3.forceSimulation !== "function") return;

      const simNodes = allData.nodes;
      const simLinks = buildSimLinks(activeTopicEdges);

      simulation = d3.forceSimulation(simNodes)
        .force("charge", d3.forceManyBody().strength(d => -(d.node_radius * 16 + 130)))
        .force("link", d3.forceLink(simLinks)
          .id(d => d.id)
          .distance(d => {
            const sId = typeof d.source === "object" ? d.source.id : d.source;
            const tId = typeof d.target === "object" ? d.target.id : d.target;
            const isEgo = (sId === EGO_ID || tId === EGO_ID);
            const w = d.weight || 10;
            const npmi = d.npmi || 0.1;
            // Damped ego distance so lateral community forces dominate
            return isEgo ? 460 : Math.max(55, 340 / Math.sqrt(Math.max(1, w)) * (1.2 - Math.max(0, npmi)));
          })
          .strength(d => {
            const sId = typeof d.source === "object" ? d.source.id : d.source;
            const tId = typeof d.target === "object" ? d.target.id : d.target;
            const isEgo = (sId === EGO_ID || tId === EGO_ID);
            return isEgo ? 0.08 : 0.65;
          })
        )
        .force("collide", d3.forceCollide().radius(d => (d.node_radius || 15) + 24).iterations(3))
        .force("center", d3.forceCenter(0, 0))
        .force("x", d3.forceX(0).strength(0.035))
        .force("y", d3.forceY(0).strength(0.035))
        .alphaDecay(0.022)
        .on("tick", () => {
          nodeG.attr("transform", d => `translate(${d.x.toFixed(1)},${d.y.toFixed(1)})`);
          activeLayer.selectAll("path.edge-path").attr("d", ed => computeBezierPath(ed));
          activeLayer.selectAll("path.edge-hover-hitbox").attr("d", ed => computeBezierPath(ed));
          if (minimapNodesG && minimapNodesG.node()) {
            minimapNodesG.selectAll("circle.mm-dot")
              .attr("cx", d => d.x)
              .attr("cy", d => d.y);
          }
        })
        .on("end", () => {
          // Sekali saja, setelah tata letak berhenti bergerak: sebelum ini
          // kotak pembatasnya masih berubah tiap tick.
          if (!viewStateFlushed) resetGraphView();
          applyLabelBudget();
          flushViewState();
        });
    }

    let currentTopicDriver = EGO_ID;

    function computeEmergentTopicCenter(topic, edges) {
      if (!topic || topic === "ALL" || !edges || edges.length === 0) {
        const fallback = EGO_ID || ((allData.nodes || [])[0] || {}).id || null;
        return { driverId: fallback, score: 0, participantCount: (allData.nodes || []).length };
      }

      const scores = {};
      const participants = new Set();

      edges.forEach(l => {
        const s = getSourceId(l), t = getTargetId(l);
        participants.add(s);
        participants.add(t);
        const w = l.weight || 1;
        const npmi = l.npmi || (l.significance && l.significance.npmi) || 0;
        const baseScore = Math.log1p(w) * (1.0 + Math.max(0, npmi) * 2.5);
        scores[s] = (scores[s] || 0) + (s === EGO_ID ? baseScore * 0.05 : baseScore);
        scores[t] = (scores[t] || 0) + (t === EGO_ID ? baseScore * 0.05 : baseScore);
      });

      let topNode = null;
      let maxScore = -1;
      // In specialized discourse topics, promote non-ego emergent thematic driver
      Object.keys(scores).forEach(nid => {
        if (nid !== EGO_ID && scores[nid] > maxScore) {
          maxScore = scores[nid];
          topNode = nid;
        }
      });
      if (!topNode) {
        topNode = EGO_ID || Object.keys(scores)[0] || null;
        maxScore = (topNode && scores[topNode]) || 0;
      }

      return {
        driverId: topNode,
        score: maxScore,
        participantCount: participants.size
      };
    }

