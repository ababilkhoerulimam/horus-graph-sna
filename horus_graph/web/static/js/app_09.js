    // -------------------------------------------------------------
    function initTimelineKeyEvents() {
      fetch("/api/graph/key-events")
        .then(res => res.ok ? res.json() : null)
        .then(events => {
          if (!events || !Array.isArray(events) || events.length === 0) return;
          const timelineWrap = document.querySelector(".hud-timeline") || document.getElementById("timeline-controls-wrap");
          if (!timelineWrap) return;

          let pinContainer = document.getElementById("timeline-key-event-pins");
          if (!pinContainer) {
            pinContainer = document.createElement("div");
            pinContainer.id = "timeline-key-event-pins";
            // Deretan pin dulu disisipkan ke dalam bilah waktu, sehingga tahun
            // peristiwa terbaca sebagai kontrol waktu kedua. Sekarang ia keluar
            // dari alur bilah dan duduk di atasnya sebagai penanda peristiwa.
            pinContainer.style.cssText = "position:absolute; bottom:96px; left:50%; transform:translateX(-50%); display:flex; gap:14px; align-items:flex-end; justify-content:center; z-index:21; pointer-events:none; white-space:nowrap;";
            const slider = document.getElementById("timeline-slider");
            if (slider && slider.parentNode) {
              slider.parentNode.insertBefore(pinContainer, slider);
            }
          }
          pinContainer.innerHTML = "";
          const pinLabel = document.createElement("div");
          pinLabel.textContent = "Peristiwa";
          pinLabel.style.cssText = "font-size:11px; font-weight:700; color:#8A99AE; align-self:center;";
          pinContainer.appendChild(pinLabel);
          events.forEach(ev => {
            const pin = document.createElement("div");
            pin.className = "timeline-event-pin";
            pin.title = `${ev.date}: ${ev.title}\n${ev.description}`;
            pin.style.cssText = "cursor:pointer; pointer-events:auto; display:flex; flex-direction:column; align-items:center;";
            pin.innerHTML = `
              <div style="font-size:11px; font-weight:800; color:#38BDF8;">${ev.date.slice(0, 4)}</div>
              <div style="width:6px; height:6px; border-radius:50%; background:#38BDF8; margin-top:1px;"></div>
            `;
            pin.addEventListener("click", () => {
              if (ev.related_actors && ev.related_actors.length > 0) {
                const targetActor = ev.related_actors[0];
                const node = nodeMap.get(targetActor);
                if (node) selectAndInspectNode(node);
              }
            });
            pinContainer.appendChild(pin);
          });
        })
        .catch(() => {});
    }
    initTimelineKeyEvents();

    // Salience Backbone Network: Clean default active without manual clutter buttons

    
    function hideCanvasLoading() {
      const overlay = document.getElementById("canvas-loading-overlay");
      if (overlay) {
        overlay.style.opacity = "0";
        setTimeout(() => { overlay.style.display = "none"; }, 400);
      }
    }

    // Sinkronisasi data graf dinamis dari server lokal
    function setText(id, value) {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    }

    // Pembantu format: null berarti "belum tersedia", bukan 0.
    function formatCount(value) {
      return (value === null || value === undefined || Number.isNaN(value))
        ? "n/a"
        : Number(value).toLocaleString("id-ID");
    }

    function formatNumber(value, digits) {
      return (value === null || value === undefined || Number.isNaN(value))
        ? "n/a"
        : Number(value).toFixed(digits);
    }

    function egoNode() {
      const byId = allData.nodes.find(n => n.id === EGO_ID);
      if (byId) return byId;
      return allData.nodes.reduce((best, n) => {
        const deg = (n.metrics && n.metrics.degree) || 0;
        return !best || deg > ((best.metrics && best.metrics.degree) || 0) ? n : best;
      }, null);
    }

    // Telemetri per tahun dihitung dari artefak: simpul aktif dari
    // metrics.metrics_by_year, relasi aktif dari link.active_years.
    function computeYearTelemetry(year) {
      const activeNodes = allData.nodes.filter(
        n => n.metrics && n.metrics.metrics_by_year && n.metrics.metrics_by_year[year]
      );
      const activeIds = new Set(activeNodes.map(n => n.id));
      const edges = allData.links.filter(
        l => Array.isArray(l.active_years) && l.active_years.includes(year)
      );
      const internalEdges = edges.filter(
        l => activeIds.has(l.source) && activeIds.has(l.target)
      );
      const nodeCount = activeIds.size;
      const edgeCount = internalEdges.length;
      const ego = egoNode();
      const egoDegree = ego
        ? internalEdges.filter(l => l.source === ego.id || l.target === ego.id).length
        : 0;
      const perYear = (CORPUS_COVERAGE && CORPUS_COVERAGE.per_year) || {};
      return {
        articles: perYear[String(year)] === undefined ? null : perYear[String(year)],
        nodes: nodeCount,
        edges: edgeCount,
        density: nodeCount > 1 ? (2 * edgeCount) / (nodeCount * (nodeCount - 1)) : null,
        egoDegree: egoDegree
      };
    }

    // Seluruh angka modal dan disclosure dibaca dari metadata artefak.
    function renderArtifactFacts() {
      const meta = allData.metadata || {};
      const summary = meta.summary || {};
      const counts = meta.counts || {};
      const communities = summary.communities || {};

      setText("macro-density", formatNumber(summary.density, 4));
      setText("macro-density-sub", summary.density === null || summary.density === undefined
        ? "belum dihitung"
        : (summary.density * 100).toFixed(1) + "% koneksi aktif");
      setText("macro-modularity", formatNumber(communities.modularity, 4));
      setText("macro-modularity-sub", communities.count === undefined
        ? "komunitas belum dihitung"
        : communities.count + " komunitas wacana");
      setText("macro-transitivity", formatNumber(summary.transitivity, 4));
      setText("macro-diameter", formatCount(summary.diameter));
      setText("macro-avgpath", formatNumber(summary.average_path_length, 4));
      setText("macro-components", summary.components === undefined
        ? "n/a"
        : formatCount(summary.components) + " komponen");
      setText("macro-components-sub", "simpul terisolasi: " + formatCount(summary.isolated));

      const title = document.getElementById("community-breakdown-title");
      const consensus = meta.consensus || null;
      if (title) {
        // Stabilitas hanya ikut ditulis bila memang diukur; "n/a" pada judul
        // terbaca seperti angka yang hilang, jadi lebih baik tidak disebut.
        const stab = (consensus && typeof consensus.stability_median === "number")
          ? ` \u00b7 stabilitas median ${consensus.stability_median.toFixed(2)}`
          : "";
        title.textContent = communities.count === undefined
          ? "Struktur Komunitas Louvain"
          : `Struktur ${communities.count} Komunitas Louvain (Q = ${formatNumber(communities.modularity, 4)})${stab}`;
      }
      const breakdown = document.getElementById("community-breakdown");
      if (breakdown) {
        breakdown.innerHTML = "";
        const groups = {};
        allData.nodes.forEach(n => {
          const key = n.louvain_community;
          if (key === undefined || key === null) return;
          (groups[key] = groups[key] || []).push(n);
        });
        const stabilityOf = n => (typeof n.community_stability === "number" ? n.community_stability : null);
        const medianOf = values => {
          if (!values.length) return null;
          const sorted = values.slice().sort((a, b) => a - b);
          const middle = Math.floor(sorted.length / 2);
          return sorted.length % 2
            ? sorted[middle]
            : (sorted[middle - 1] + sorted[middle]) / 2;
        };
        Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length).forEach(key => {
          const members = groups[key].slice().sort(
            (a, b) => ((b.metrics && b.metrics.degree) || 0) - ((a.metrics && a.metrics.degree) || 0)
          );
          const top = members.slice(0, 3).map(m => m.display_label || m.label || m.id).join(", ");
          const median = medianOf(members.map(stabilityOf).filter(v => v !== null));
          const stab = median === null ? "" : ` &bull; stabil ${median.toFixed(2)}`;
          const box = document.createElement("div");
          box.className = "prov-box";
          box.innerHTML = `<strong>Komunitas ${key}:</strong> ${members.length} simpul &bull; Top: ${top}${stab}`;
          breakdown.appendChild(box);
        });
        // Simpul batas adalah hasil ukur, bukan peringatan: mereka berpindah
        // sisi pada sebagian jalankan Louvain, jadi keanggotaannya tidak boleh
        // dibaca sebagai temuan yang pasti.
        const border = document.createElement("div");
        border.className = "prov-box";
        if (!consensus || consensus.status !== "ready") {
          border.innerHTML = `<strong>Stabilitas komunitas:</strong> belum dihitung. ` +
            `${(consensus && consensus.reason) || "Jalankan build ulang untuk mengukurnya."}`;
        } else if (consensus.unstable_count > 0) {
          const names = (consensus.unstable || []).map(item => entityLabel(item.id)).join(", ");
          border.innerHTML = `<strong>Simpul batas:</strong> ${consensus.unstable_count} simpul ` +
            `berpindah sisi pada sebagian dari ${consensus.runs} jalankan Louvain. ${names}`;
        } else {
          border.innerHTML = `<strong>Simpul batas:</strong> tidak ada; seluruh simpul bertahan ` +
            `pada ${consensus.runs} jalankan Louvain (kesepakatan ARI ${formatNumber(consensus.agreement, 3)}).`;
        }
        breakdown.appendChild(border);
      }

      // Motif lokal: dua kotak, satu per motif. Alasan ketiadaan ditulis apa
      // adanya, karena kotak kosong terbaca seperti hasil ukur nol. Teks dari
      // engine masuk lewat textContent: alasannya menyebut `<bundle>`, dan
      // innerHTML menelan potongan itu sebagai tag sehingga kalimatnya bolong.
      const motifBody = document.getElementById("motif-body");
      if (motifBody) {
        motifBody.innerHTML = "";
        const motifBox = (judul) => {
          const box = document.createElement("div");
          box.className = "prov-box";
          const label = document.createElement("strong");
          label.textContent = judul;
          box.appendChild(label);
          return box;
        };
        const motifBlock = meta.motifs || {};
        const triads = motifBlock.triads || {};
        const triadBox = motifBox("Sensus triad: ");
        if (triads.status === "ready") {
          const share = triads.closed_share === null || triads.closed_share === undefined
            ? "—" : (triads.closed_share * 100).toFixed(1) + "%";
          triadBox.appendChild(document.createTextNode(
            `${formatCount(triads.triangles)} segitiga, ` +
            `${formatCount(triads.open_wedges)} baji terbuka, ` +
            `${share} triad bertepi ganda tertutup ` +
            `(dari ${formatCount(triads.triples)} triple).`
          ));
        } else {
          triadBox.appendChild(document.createTextNode(
            `tidak diukur. ${triads.reason || "Graf terlalu kecil."}`
          ));
        }
        motifBody.appendChild(triadBox);

        const club = motifBlock.rich_club || {};
        const clubBox = motifBox("Rich-club: ");
        if (club.status === "ready" && club.peak) {
          const extra = club.truncated_degrees
            ? ` ${club.truncated_degrees} ambang derajat tertinggi dipotong.`
            : "";
          clubBox.appendChild(document.createTextNode(
            `rasio puncak ${formatNumber(club.peak.ratio, 2)} pada derajat ${club.peak.degree} ` +
            `(${formatCount(club.replicates)} graf acak pembanding). ` +
            `1,0 berarti tidak ada efek di luar derajat.${extra}`
          ));
        } else {
          clubBox.appendChild(document.createTextNode(
            `tidak diukur. ${club.reason || "Jalankan horus-graph motifs --write."}`
          ));
        }
        motifBody.appendChild(clubBox);
      }

      // Disclosure korpus: angka dari /api/bootstrap (coverage).
      const cov = CORPUS_COVERAGE;
      if (cov && cov.articles) {
        const undated = Math.max(0, (cov.articles || 0) - (cov.dated || 0));
        const span = (cov.first && cov.last)
          ? `${String(cov.first).slice(0, 4)}-${String(cov.last).slice(0, 4)}`
          : "rentang tidak diketahui";
        setText(
          "disclosure-corpus-text",
          `Basis data analitik memakai ${formatCount(cov.dated)} artikel bertanggal ` +
          `dalam rentang ${span}, dari ${formatCount(cov.articles)} baris pada ` +
          `${formatCount(cov.sources)} sumber. ` +
          `${formatCount(undated)} baris tanpa tanggal tidak dihitung.`
        );
        setText(
          "prov-corpus-text",
          `Total ${formatCount(cov.articles)} baris; ${formatCount(cov.dated)} bertanggal ` +
          `(${span}), ${formatCount(undated)} tanpa tanggal.`
        );
      } else {
        setText("disclosure-corpus-text", "Cakupan korpus belum tersedia pada bundle ini.");
        setText("prov-corpus-text", "Cakupan korpus belum tersedia.");
      }

      setText(
        "prov-entity-text",
        `${formatCount(counts.entities)} entitas kanonik pada bundle ini, dihasilkan dari korpus oleh engine.`
      );

      const layers = (BOOTSTRAP && BOOTSTRAP.dataset && BOOTSTRAP.dataset.layers) || {};
      const layerNames = Object.keys(layers);
      setText(
        "prov-model-text",
        layerNames.length
          ? `Lapisan tersedia: ${layerNames.join(", ")}.`
          : "Belum ada lapisan tambahan pada bundle ini."
      );
    }

    // -------------------------------------------------------------
    // Sensitivitas ambang backbone
    // -------------------------------------------------------------
    // Satu balapan permintaan: panel ini bisa dibuka-tutup cepat, dan jawaban
    // yang datang terlambat tidak boleh menimpa jawaban yang lebih baru.
    let sensitivityCache = null;
    let sensitivityRequest = 0;

    function sensitivityAxis(values) {
      const lo = Math.min.apply(null, values);
      const hi = Math.max.apply(null, values);
      return { lo: lo, hi: hi };
    }

    // Kurva dua garis. Garis penuh = sisi yang lolos ambang (tidak pernah naik
    // saat ambang naik). Garis putus-putus = total setelah simpul terisolasi
    // diselamatkan; garis ini boleh naik, dan justru itu yang perlu terlihat.
    // Nama sumbu tidak ditulis di dalam grafik: kotak di atasnya sudah
    // menyebut ambang mana yang digambar, dan label itu dulu bertabrakan
    // dengan angka ujung kanan.
    function sensitivityChart(points, xKey, activeValue, xLabel, yLabel) {
      const W = 320, H = 130, PL = 40, PR = 12, PT = 12, PB = 22;
      const xs = points.map(p => Number(p[xKey]));
      const axis = sensitivityAxis(xs);
      const maxEdges = Math.max(1, Math.max.apply(null, points.map(p => Number(p.edges) || 0)));
      const spanX = axis.hi - axis.lo;
      const sx = v => PL + (spanX === 0 ? 0.5 : (v - axis.lo) / spanX) * (W - PL - PR);
      const sy = v => H - PB - (Number(v) / maxEdges) * (H - PT - PB);
      const line = key => points.map(p => `${sx(Number(p[xKey])).toFixed(1)},${sy(p[key]).toFixed(1)}`).join(" ");

      // Label "aktif" duduk di kaki garis, bukan di puncaknya: di puncak ia
      // bertabrakan dengan label nilai maksimum pada sumbu tegak.
      const markerX = sx(Number(activeValue));
      const markerAnchor = markerX > W * 0.7 ? "end" : "start";
      const markerShift = markerAnchor === "end" ? -3 : 3;
      const marker = points.some(p => Number(p[xKey]) === Number(activeValue))
        ? `<line x1="${markerX.toFixed(1)}" y1="${PT}" x2="${markerX.toFixed(1)}" y2="${H - PB}"
                stroke="#F59E0B" stroke-width="1" stroke-dasharray="2,2" />
           <text x="${(markerX + markerShift).toFixed(1)}" y="${H - PB - 4}" fill="#F59E0B" font-size="9"
                 text-anchor="${markerAnchor}">aktif</text>`
        : "";

      return `
        <svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img"
             aria-label="${yLabel} terhadap ${xLabel}">
          <line x1="${PL}" y1="${H - PB}" x2="${W - PR}" y2="${H - PB}" stroke="rgba(255,255,255,0.18)" />
          <line x1="${PL}" y1="${PT}" x2="${PL}" y2="${H - PB}" stroke="rgba(255,255,255,0.18)" />
          <text x="${PL - 6}" y="${PT + 8}" fill="#8A99AE" font-size="9" text-anchor="end">${maxEdges}</text>
          <text x="${PL - 6}" y="${H - PB}" fill="#8A99AE" font-size="9" text-anchor="end">0</text>
          ${marker}
          <polyline points="${line("edges")}" fill="none" stroke="#38BDF8" stroke-width="1.4" stroke-dasharray="3,3" opacity="0.85" />
          <polyline points="${line("passed")}" fill="none" stroke="#22D3EE" stroke-width="2" />
          <text x="${PL}" y="${H - 6}" fill="#8A99AE" font-size="9">${axis.lo}</text>
          <text x="${W - PR}" y="${H - 6}" fill="#8A99AE" font-size="9" text-anchor="end">${axis.hi}</text>
        </svg>`;
    }

    function sensitivityCaption(points, xKey, activeValue, xLabel) {
      const active = points.find(p => Number(p[xKey]) === Number(activeValue));
      if (!active) return `<div style="color:#F59E0B;">Ambang aktif (${activeValue}) tidak ada pada kurva ini.</div>`;
      return `<div style="margin-top:2px;color:#CBD5E1;">
        Pada ${xLabel} <strong>${activeValue}</strong>: <strong>${active.edges}</strong> sisi
        (${active.passed} lolos, ${active.rescued} diselamatkan), ${active.nodes} simpul tersentuh,
        ${active.isolated} terisolasi.
      </div>`;
    }

    function renderSensitivity(data) {
      const host = document.getElementById("sensitivity-body");
      if (!host) return;

      if (!data || data.status !== "ready") {
        // Gagal memuat bukan "nol sisi": tampilkan tanda kosong, bukan angka.
        host.textContent = "Kurva sensitivitas tidak tersedia untuk bundle ini (\u2014).";
        return;
      }

      const bySupport = data.by_support || [];
      const byNpmi = data.by_npmi || [];
      if (!bySupport.length || !byNpmi.length) {
        host.textContent = "Kurva sensitivitas kosong (\u2014).";
        return;
      }

      host.innerHTML = `
        <div style="margin-bottom:6px;">
          ${formatCount(data.candidate_pairs)} pasangan kandidat diperiksa. Garis penuh = sisi yang
          lolos ambang; garis putus-putus = total setelah simpul terisolasi diselamatkan.
          Ambang disampel per kuartil sebaran nilainya, jadi jarak mendatar tidak linier:
          titik-titiknya mengikuti di mana data benar-benar berada.
        </div>
        <div style="display:grid;grid-template-columns:repeat(2, 1fr);gap:10px;">
          <div class="prov-box">
            <div style="font-weight:800;color:#38BDF8;margin-bottom:2px;">Ambang min_support</div>
            ${sensitivityChart(bySupport, "min_support", data.active.min_support, "support", "sisi")}
            ${sensitivityCaption(bySupport, "min_support", data.active.min_support, "support")}
          </div>
          <div class="prov-box">
            <div style="font-weight:800;color:#38BDF8;margin-bottom:2px;">Ambang min_npmi</div>
            ${sensitivityChart(byNpmi, "min_npmi", data.active.min_npmi, "npmi", "sisi")}
            ${sensitivityCaption(byNpmi, "min_npmi", data.active.min_npmi, "NPMI")}
          </div>
        </div>`;
    }

    function loadSensitivity() {
      const host = document.getElementById("sensitivity-body");
      if (!host) return;
      if (sensitivityCache) { renderSensitivity(sensitivityCache); return; }
      host.textContent = "Memuat kurva sensitivitas...";
      const ticket = ++sensitivityRequest;
      fetch("/api/analysis/sensitivity?points=12")
        .then(res => {
          if (!res.ok) throw new Error("HTTP " + res.status);
          return res.json();
        })
        .then(data => {
          if (ticket !== sensitivityRequest) return;  // jawaban basi
          sensitivityCache = data;
          renderSensitivity(data);
        })
        .catch(err => {
          if (ticket !== sensitivityRequest) return;
          console.warn("[Sensitivity] Error:", err);
          host.textContent = "Kurva sensitivitas gagal dimuat (\u2014).";
        });
    }

    // -------------------------------------------------------------
    // Catatan analis
    // -------------------------------------------------------------
    // Catatan disimpan per snapshot_id di luar folder bundle, jadi ia bertahan
    // setelah server restart dan tidak ikut berubah saat bundle dibangun ulang.
    let ANNOTATIONS = null;
    let currentNoteTarget = null;

    function annotationsFor(entityId) {
      return (ANNOTATIONS || []).filter(item =>
        item.target_type === "node" && item.target_id === entityId
      );
    }

    function renderNodeNotes(entityId) {
      const list = document.getElementById("drawer-note-list");
      const count = document.getElementById("drawer-note-count");
      if (!list) return;

      // Belum dimuat: jangan tampilkan "belum ada catatan" — itu klaim.
      if (ANNOTATIONS === null) {
        list.textContent = "Memuat catatan...";
        if (count) count.textContent = "\u2014";
        return;
      }
      const items = annotationsFor(entityId);
      if (count) count.textContent = items.length;
      list.innerHTML = "";
      if (items.length === 0) {
        list.textContent = "Belum ada catatan untuk simpul ini.";
        return;
      }
      items.forEach(item => {
        const row = document.createElement("div");
        row.style.cssText = "background:var(--bg-card); border-left:3px solid #38BDF8; border-radius:0 6px 6px 0; padding:5px 8px; margin-bottom:5px; color:#CBD5E1; display:flex; gap:6px; align-items:flex-start;";
        const text = document.createElement("div");
        text.style.cssText = "flex:1; white-space:pre-wrap; word-break:break-word;";
        // textContent, bukan innerHTML: isi catatan adalah masukan manusia.
        text.textContent = item.text;
        const meta = document.createElement("div");
        meta.style.cssText = "font-size:11px; color:#8A99AE; margin-top:3px;";
        meta.textContent = item.created_at;
        const body = document.createElement("div");
        body.style.flex = "1";
        body.appendChild(text);
        body.appendChild(meta);
        const remove = document.createElement("button");
        remove.textContent = "\u00d7";
        remove.title = "Hapus catatan";
        remove.setAttribute("aria-label", "Hapus catatan");
        remove.style.cssText = "background:none; border:none; color:#8A99AE; cursor:pointer; font-size:13px; line-height:1; padding:0 2px;";
        remove.addEventListener("click", () => deleteNote(item.id));
        row.appendChild(body);
        row.appendChild(remove);
        list.appendChild(row);
      });
    }


    function saveNote() {
      const input = document.getElementById("drawer-note-input");
      if (!input || !currentNoteTarget) return;
      const text = input.value.trim();
      if (!text) return;

      const button = document.getElementById("btn-save-note");
      if (button) button.disabled = true;
      fetch("/api/annotations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_type: "node", target_id: currentNoteTarget, text: text })
      })
        .then(res => {
          if (!res.ok) throw new Error("HTTP " + res.status);
          return res.json();
        })
        .then(() => {
          input.value = "";
          loadAnnotations();
        })
        .catch(err => {
          console.warn("[Annotations] Gagal menyimpan:", err);
          const list = document.getElementById("drawer-note-list");
          if (list) list.textContent = "Catatan gagal disimpan (\u2014).";
        })
        .finally(() => {
          if (button) button.disabled = false;
        });
    }

    function deleteNote(annotationId) {
      fetch(`/api/annotations/${encodeURIComponent(annotationId)}`, { method: "DELETE" })
        .then(res => {
          if (!res.ok) throw new Error("HTTP " + res.status);
          loadAnnotations();
        })
        .catch(err => console.warn("[Annotations] Gagal menghapus:", err));
    }

    // -------------------------------------------------------------
    // Uji statistik: null model + bootstrap
