    // -------------------------------------------------------------
    // Perhitungannya ~1 menit di server, jadi permintaan pertama hanya
    // memulai pekerjaan. Panel memantau, dan selama belum ada hasil ia
    // menuliskan status — bukan angka.
    let inferenceCache = null;
    let inferencePoll = null;

    const INFERENCE_POLL_MS = 3000;
    const INFERENCE_POLL_LIMIT = 40;   // ~2 menit

    function stopInferencePoll() {
      if (inferencePoll !== null) {
        clearTimeout(inferencePoll);
        inferencePoll = null;
      }
    }

    function pValueText(value, resolution) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "tidak teruji";
      }
      // p tidak pernah ditulis 0: angka terkecil yang bisa dinyatakan uji
      // empiris adalah batas resolusinya, bukan nol.
      const floor = (resolution === null || resolution === undefined) ? null : 2 * resolution;
      if (floor !== null && Number(value) <= floor + 1e-9) {
        return "p \u2264 " + floor.toFixed(3);
      }
      return "p = " + Number(value).toFixed(3);
    }

    function renderInference(data) {
      const host = document.getElementById("inference-body");
      if (!host) return;

      if (!data || data.status === "computing") {
        const resamples = (data && data.resamples) || 0;
        host.innerHTML = `Sedang dihitung di latar belakang (${formatCount(resamples)} resampling).
          Panel ini akan terisi sendiri; angka tidak ditampilkan sebelum uji selesai.`;
        return;
      }

      if (data.status === "failed") {
        host.textContent = "Uji statistik gagal dihitung (\u2014). " + (data.detail || "");
        return;
      }

      const block = data.inference || {};
      const nullModel = block.null_model || {};
      const resolution = block.p_value_resolution;
      const bootstrap = block.bootstrap || {};
      const ari = bootstrap.ari || {};

      const names = [["modularity", "Modularitas Q"], ["transitivity", "Transitivitas"],
                     ["assortativity", "Asortativitas"]];
      const rows = names.map(([key, label]) => {
        const observed = (nullModel.observed || {})[key];
        const z = (nullModel.z || {})[key];
        const p = (nullModel.p_value || {})[key];
        return `<tr>
          <td style="padding:4px 8px 4px 0;color:#CBD5E1;">${label}</td>
          <td style="padding:4px 8px;color:#F8FAFC;font-weight:700;">${formatNumber(observed, 4)}</td>
          <td style="padding:4px 8px;color:#94A3B8;">${formatNumber(z, 2)}</td>
          <td style="padding:4px 0;color:${p === null || p === undefined ? "#8A99AE" : "#22D3EE"};">${pValueText(p, resolution)}</td>
        </tr>`;
      }).join("");

      const resolutionText = (resolution === null || resolution === undefined)
        ? "Resolusi uji tidak tersedia (tidak ada resample)."
        : `Resolusi uji: 1/(${formatCount(nullModel.resamples)} + 1) = ${Number(resolution).toFixed(4)}; ` +
          `batas dua sisi ${(2 * Number(resolution)).toFixed(3)}. p tidak pernah ditulis 0.`;

      const ariText = (ari.mean === null || ari.mean === undefined)
        ? "Stabilitas komunitas: tidak ada resample (\u2014)."
        : `Stabilitas komunitas (ARI): <strong>${formatNumber(ari.mean, 4)}</strong> ` +
          `dengan rentang p05\u2013p95 <strong>${formatNumber(ari.p05, 4)}\u2013${formatNumber(ari.p95, 4)}</strong>.`;

      host.innerHTML = `
        <div style="margin-bottom:6px;">
          Pembanding: ${formatCount(nullModel.resamples)} graf acak berderajat sama (double-edge swap),
          seed ${nullModel.seed === undefined ? "\u2014" : nullModel.seed}.
          ${resolutionText}
        </div>
        <div class="prov-box" style="margin-bottom:8px;">
          <table style="width:100%;border-collapse:collapse;font-size:11px;">
            <thead>
              <tr style="color:#8A99AE;text-align:left;">
                <th style="padding-bottom:4px;">Metrik</th>
                <th style="padding-bottom:4px;">Teramati</th>
                <th style="padding-bottom:4px;">z</th>
                <th style="padding-bottom:4px;">Uji</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div>${ariText}</div>`;
    }

    function loadInference(attempt) {
      const host = document.getElementById("inference-body");
      if (!host) return;
      if (inferenceCache) { renderInference(inferenceCache); return; }

      const round = attempt || 0;
      fetch("/api/inference")
        .then(res => {
          if (!res.ok && res.status !== 202) throw new Error("HTTP " + res.status);
          return res.json();
        })
        .then(data => {
          if (!data) return;
          if (data.status === "computing") {
            renderInference(data);
            if (round < INFERENCE_POLL_LIMIT) {
              stopInferencePoll();
              inferencePoll = setTimeout(() => loadInference(round + 1), INFERENCE_POLL_MS);
            }
            return;
          }
          stopInferencePoll();
          inferenceCache = data;
          renderInference(data);
        })
        .catch(err => {
          stopInferencePoll();
          console.warn("[Inference] Error:", err);
          host.textContent = "Uji statistik gagal dimuat (\u2014).";
        });
    }

    // Satu-satunya penulis kartu KPI. `visibleNodes`/`visibleEdges` diisi saat
    // filter menyembunyikan sebagian graf; tanpa argumen berarti seluruh graf.
    function updateMacroStats(visibleNodes, visibleEdges) {
      const totalNodes = allData.nodes.length;
      const totalEdges = allData.links.length;
      const nodes = (visibleNodes === undefined || visibleNodes === null) ? totalNodes : visibleNodes;
      const edges = (visibleEdges === undefined || visibleEdges === null) ? totalEdges : visibleEdges;
      setText("stat-active-nodes", nodes);
      setText("stat-active-edges", edges);
      setText("stat-total-edges", totalEdges);

      const summary = (allData.metadata && allData.metadata.summary) || {};
      const full = (edges === totalEdges && nodes === totalNodes);
      if (full) {
        // Angka engine untuk graf penuh. Null berarti belum diukur, bukan nol.
        const measured = (summary.density === null || summary.density === undefined)
          ? null : Number(summary.density);
        setText("stat-active-density", measured === null
          ? "Densitas: —"
          : "Densitas: " + measured.toFixed(4));
      } else {
        // Densitas himpunan yang terlihat, bukan densitas jaringan: beda besaran,
        // jadi beda label. Tanpa label ini, 0,160 dan 0,1623 tampak bertengkar.
        const dens = nodes > 1 ? (2 * edges) / (nodes * (nodes - 1)) : null;
        setText("stat-active-density", dens === null
          ? "Densitas tampilan: —"
          : "Densitas tampilan: " + dens.toFixed(4));
      }

      // Komunitas dan korpus tidak ikut tersaring, jadi selalu angka penuh.
      // Simpul tanpa komunitas tidak dihitung sebagai satu komunitas.
      const communities = new Set(
        allData.nodes.map(n => n.louvain_community).filter(v => v !== undefined && v !== null)
      ).size;
      setText("stat-active-communities", communities);
      const counts = (allData.metadata && allData.metadata.counts) || {};
      setText("stat-active-corpus", counts.articles ? counts.articles.toLocaleString("id-ID") : "—");
      renderArtifactFacts();
    }

    function showBootError(message) {
      const overlay = document.getElementById("canvas-loading-overlay");
      if (!overlay) return;
      const copy = (PRESENTATION && PRESENTATION.wording) || {};
      overlay.style.pointerEvents = "auto";
      overlay.style.opacity = "1";
      overlay.style.display = "flex";
      overlay.innerHTML =
        "<div style=\"font-size:13px; font-weight:800; color:#F87171;\">" +
        escapeHtml(copy.boot_error || "Data gagal dimuat") + "</div>" +
        "<div style=\"font-size:11px; color:#94A3B8; margin-top:6px; max-width:440px; text-align:center;\">" +
        escapeHtml(message) + "</div>" +
        "<div style=\"font-size:11px; color:#8A99AE; margin-top:8px;\">" +
        escapeHtml(copy.no_bundle || "") + "</div>";
    }

    function escapeHtml(value) {
      return String(value == null ? "" : value).replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[ch]));
    }

    // Istilah struktural ("Simpul", "Sisi", "Artikel") selalu lewat sini supaya
    // bundle yang menimpa presentation.labels ikut terpakai di seluruh UI.
    function labelOf(key, fallback) {
      const labels = (PRESENTATION && PRESENTATION.labels) || {};
      return labels[key] || fallback || key;
    }

    // Nama berkas ekspor mengikuti dataset, bukan nama domain di kode.
    function fileSlug() {
      const dataset = (BOOTSTRAP && BOOTSTRAP.dataset) || {};
      const source = dataset.id || (PRESENTATION && PRESENTATION.title) || "horus-graph";
      return String(source)
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "") || "horus_graph";
    }

    // Tipe "sumber" ditentukan oleh metadata tipe entitas, bukan nama tetap.
    function sourceTypeIds() {
      return ((PRESENTATION && PRESENTATION.entity_types) || [])
        .map(entry => entry.id || entry.label)
        .filter(id => id && /source|media|portal|outlet|sumber|press/i.test(String(id)));
    }

    function isSourceNode(node) {
      if (!node) return false;
      return sourceTypeIds().includes(node.entity_type);
    }

    function egoLabel(fallback) {
      const ego = (PRESENTATION && PRESENTATION.ego) || null;
      const value = ego ? (ego.label || ego.id) : "";
      return value || fallback || "";
    }

    // Kalimat aturan tindakan ditulis di metadata dengan placeholder {label},
    // {type}, {cluster}, {articles}, {centre}. Tidak ada nama domain di sini.
    function fillTemplate(template, node, articleCount) {
      if (!template) return "";
      const ego = (PRESENTATION && PRESENTATION.ego) || null;
      const values = {
        label: (node && (node.label || node.id)) || "",
        type: (node && (typeLabel(node.entity_type) || node.entity_type)) || "",
        cluster: (node && (node.cluster_label || node.cluster)) || "",
        articles: articleCount == null
          ? (node && node.articles != null ? Number(node.articles).toLocaleString("id-ID") : "—")
          : articleCount,
        centre: ego ? (ego.label || ego.id) : ""
      };
      return String(template).replace(/\{(\w+)\}/g, (match, key) =>
        Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match);
    }

    function hexToRgba(hex, alpha) {
      const raw = String(hex || "").replace("#", "").trim();
      const full = raw.length === 3 ? raw.split("").map(ch => ch + ch).join("") : raw;
      if (full.length !== 6 || /[^0-9a-fA-F]/.test(full)) return `rgba(148, 163, 184, ${alpha})`;
      const num = parseInt(full, 16);
      return `rgba(${(num >> 16) & 255}, ${(num >> 8) & 255}, ${num & 255}, ${alpha})`;
    }

    // Semua teks tampilan berasal dari presentation; tidak ada nama domain di sini.
    function applyPresentation(presentation) {
      PRESENTATION = presentation || {};
      EGO_ID = PRESENTATION.ego ? PRESENTATION.ego.id : null;
      // Modul lain (copilot, tracer) membaca metadata lewat window.
      window.PRESENTATION = PRESENTATION;
      window.EGO_ID = EGO_ID;

      LOUVAIN_COLORS = communityColors();

      const title = PRESENTATION.title || "Horus Graph";
      const subtitle = PRESENTATION.subtitle || "";
      const titleEl = document.getElementById("app-title");
      const subtitleEl = document.getElementById("app-subtitle");
      const overviewSubtitleEl = document.getElementById("modal-overview-subtitle");
      if (titleEl) { titleEl.textContent = title; titleEl.title = title; }
      if (subtitleEl) { subtitleEl.textContent = subtitle; subtitleEl.title = subtitle; }
      if (overviewSubtitleEl) {
        overviewSubtitleEl.textContent = subtitle || "Struktur makro jaringan dan integritas korpus.";
      }
      document.title = title;
    }

    // Asal korpus ditulis manifest, bukan di kode: fork dengan pipeline lain
    // menampilkan nama pipeline-nya sendiri.
    function renderGeneratorBadge(dataset) {
      const el = document.getElementById("sb-generator");
      if (!el) return;
      const generator = (dataset && dataset.generator) || {};
      const name = generator.name || "";
      const version = generator.version ? " v" + generator.version : "";
      el.textContent = name ? name + version : "\u2014";
      el.title = name ? "Pipeline penghasil bundle: " + name + version : "Manifest tidak menyebut pipeline";
    }

    // Rentang tahun panel kanan diambil dari date_range bundle, bukan ditulis
    // tetap di markup: bundle lain punya rentang lain.
    function renderYearSpan() {
      const el = document.getElementById("drawer-year-span");
      if (!el) return;
      const years = timelineYears().filter(y => y !== null);
      if (!years.length) {
        el.textContent = "\u2014";
        el.style.color = "var(--text-muted)";
        return;
      }
      el.textContent = years[0] + " \u2013 " + years[years.length - 1];
      el.style.color = "var(--accent-blue)";
    }

    // ---------------------------------------------------------------
    // View state di URL.
    //
    // Tujuan: satu temuan bisa diserahkan sebagai tautan, bukan sebagai
    // instruksi lisan ("buka mode 2, filter Person, zoom ke Bravo"). Field
    // divalidasi satu per satu; nilai asing diabaikan, bukan dilempar, supaya
    // tautan lama tidak pernah menghasilkan layar rusak.
    //
    // Token tidak pernah masuk sini: ia hidup di sessionStorage dan URL hanya
    // memuat keadaan tampilan.
    // ---------------------------------------------------------------
    const VIEW_HASH_VERSION = "1";
    const VIEW_CHOICES = {
      m: ["actor_network", "topic_actor", "narrative_temporal"],
      c: ["type", "louvain", "sentiment"],
      k: ["volume", "degree", "betweenness", "burt", "uniform"]
    };
    // Nama pendek di URL, nama yang dipakai kode di dalam.
    const VIEW_FIELDS = { m: "mode", c: "color", k: "sizing" };
    const VIEW_DEFAULTS = { weight: 10, npmi: 0.20 };

    function readViewState() {
      const raw = (window.location.hash || "").replace(/^#/, "");
      if (!raw) return {};
      let params;
      try {
        params = new URLSearchParams(raw);
      } catch (err) {
        return {};
      }
      if (params.get("v") !== VIEW_HASH_VERSION) return {};

      const state = {};
      Object.keys(VIEW_CHOICES).forEach(key => {
        const value = params.get(key);
        if (VIEW_CHOICES[key].indexOf(value) !== -1) state[VIEW_FIELDS[key]] = value;
      });

      const number = key => {
        const value = parseFloat(params.get(key));
        return Number.isFinite(value) ? value : null;
      };
      const year = number("y");
      if (year !== null) state.year = Math.round(year);
      const weight = number("w");
      if (weight !== null) state.minWeight = weight;
      const npmi = number("n");
      if (npmi !== null) state.minNpmi = npmi;

      const topic = params.get("t");
      if (topic) state.topic = topic;
      const selected = params.get("s");
      if (selected) state.selected = selected;

      const camera = (params.get("z") || "").split(",").map(parseFloat);
      if (camera.length === 3 && camera.every(Number.isFinite)) {
        state.camera = { k: camera[0], x: camera[1], y: camera[2] };
      }
      return state;
    }

    function viewStateHash() {
      const transform = svg && svg.node() ? d3.zoomTransform(svg.node()) : d3.zoomIdentity;
      const params = new URLSearchParams();
      params.set("v", VIEW_HASH_VERSION);
      params.set("m", currentMode);
      if (currentTopic && currentTopic !== "ALL") params.set("t", currentTopic);
      if (currentColorMode !== "type") params.set("c", currentColorMode);
      if (currentSizingMetric !== "prominence") params.set("k", currentSizingMetric);
      if (currentMinWeight !== VIEW_DEFAULTS.weight) params.set("w", String(currentMinWeight));
      if (currentMinNpmi !== VIEW_DEFAULTS.npmi) params.set("n", String(currentMinNpmi));
      // `y` adalah tahun yang sedang dilihat, bukan batas rentang dataset:
      // currentStartYear diisi otomatis oleh yearBounds() dan akan berbohong
      // tentang filter yang tidak pernah dipilih pengguna.
      const years = timelineYears();
      const yearIndex = timelineSlider ? parseInt(timelineSlider.value, 10) : 0;
      const selectedYear = years[yearIndex];
      if (selectedYear !== undefined && selectedYear !== null) {
        params.set("y", String(selectedYear));
      }
      if (lockedNode) params.set("s", lockedNode.id);
      params.set(
        "z",
        [transform.k, transform.x, transform.y].map(v => Math.round(v * 1000) / 1000).join(",")
      );
      return "#" + params.toString();
    }

    let viewStatePending = false;
    let pendingViewState = readViewState();
    let viewStateFlushed = false;

    function flushViewState() {
      if (viewStateFlushed || !pendingViewState) return;
      viewStateFlushed = true;
      const state = pendingViewState;
      pendingViewState = null;
      applyViewState(state);
    }

    function syncViewStateToHash() {
      // Jangan menimpa tautan sebelum keadaan di dalamnya sempat diterapkan.
      if (!viewStateFlushed && pendingViewState) return;
      if (viewStatePending) return;
      viewStatePending = true;
      requestAnimationFrame(() => {
        viewStatePending = false;
        if (!BOOTSTRAP) return;  // sebelum data siap, hash belum bermakna
        const next = viewStateHash();
        if (window.location.hash === next) return;
        history.replaceState(null, "", window.location.pathname + window.location.search + next);
      });
    }

    function restoreSelection(nodeId) {
      const node = (allData.nodes || []).find(item => item.id === nodeId);
      if (!node) return;
      lockedNode = node;
      highlightNodeConnections(node);
      populateDrawerDetails(node);
    }

    function applyViewState(state) {
      if (!state) return;
      if (state.sizing) currentSizingMetric = state.sizing;
      if (state.color) currentColorMode = state.color;
      if (state.minWeight !== undefined) currentMinWeight = state.minWeight;
      if (state.minNpmi !== undefined) currentMinNpmi = state.minNpmi;
      if (state.topic) currentTopic = state.topic;

      if (state.mode) switchAppMode(state.mode);
      refreshNodeStyles();
      applyCombinedFilters();

      if (state.year !== undefined && typeof updateTimelineView === "function") {
        updateTimelineView(state.year);
      }
      if (state.selected) restoreSelection(state.selected);
      if (state.camera) {
        const { k, x, y } = state.camera;
        svg.call(zoom.transform, d3.zoomIdentity.translate(x, y).scale(k));
      }
    }

    // Setiap interaksi mengubah keadaan; menulis hash dari satu tempat lebih
    // sulit lupa daripada menambahkan pemanggilan di tiap handler.
    ["click", "change", "keyup"].forEach(evt => {
      document.addEventListener(evt, () => syncViewStateToHash(), true);
    });

    function normalizeNode(node) {
      // Bidang yang tidak dikirim API diisi default netral. Skala ukuran
      // (size_rank, rank_*, radius_tier, label_priority) datang dari payload
      // dan tidak pernah dihitung ulang di sini.
      // API mengirim metrik sebagai kolom datar dan komunitas sebagai
      // `community`, jadi keduanya dipetakan ke bentuk yang dipakai UI.
      const metrics = node.metrics || {
        degree: node.degree,
        pagerank: node.pagerank,
        betweenness: node.betweenness,
        closeness: node.closeness,
        burt_constraint: node.burt_constraint,
        effective_size: node.effective_size,
        articles: node.articles
      };
      const normalized = Object.assign({
        display_label: node.label,
        cluster: "",
        sector: "",
        description: "",
        orbit_label: "",
        active_years: [],
        first_seen_year: null,
        structural_hole_role: "",
        // null, bukan 0: 0 adalah id komunitas yang sah, jadi default 0
        // menempatkan simpul tanpa komunitas ke dalam komunitas nol.
        louvain_community: node.community === undefined ? null : node.community,
        burt_constraint: null,
        effective_size: null,
        pagerank: null,
        betweenness: null,
        degree: 0,
        articles: 0,
        is_anchor: false,
        is_ego: false,
        // Skala ukuran dari engine; default hanya berlaku untuk payload lama.
        size_rank: 0,
        rank_degree: 0,
        rank_volume: 0,
        rank_betweenness: 0,
        rank_burt: 0,
        radius_tier: 5,
        label_priority: Number.MAX_SAFE_INTEGER,
        metrics
      }, node);
      normalized.metrics = metrics;
      return normalized;
    }

    function normalizeLink(link) {
      return Object.assign({
        edge_category: "cooccurrence",
        relation_type: "cooccurrence",
        category_label: "Ko-okurensi",
        is_validated: false,
        sentiment_valence: null,
        added_for_support: false
      }, link);
    }

    async function bootstrapVisualizer() {
      try {
        const res = await fetch("/api/bootstrap?t=" + Date.now());
        if (!res.ok) {
          const detail = await res.json().catch(() => ({}));
          throw new Error(detail.detail || ("HTTP " + res.status));
        }
        const payload = await res.json();
        if (!payload.graph || !Array.isArray(payload.graph.nodes) || !payload.graph.nodes.length) {
          throw new Error("Bundle tidak memuat satu pun simpul");
        }

        applyPresentation(payload.presentation);
        BOOTSTRAP = payload;
        renderGeneratorBadge(payload.dataset);
        renderYearSpan();

        allData = {
          nodes: payload.graph.nodes.map(normalizeNode),
          links: payload.graph.links.map(normalizeLink),
          metadata: {
            counts: payload.dataset.counts,
            summary: payload.graph.summary,
            // Stabilitas komunitas per simpul; blok ini boleh tidak ada pada
            // payload lama, jadi pembacanya selalu memakai fallback.
            consensus: payload.graph.consensus || null,
            motifs: payload.graph.motifs || null
          }
        };
        allData.nodes.forEach(n => {
          n.color = n.color || colorForType(n.entity_type);
          n.node_radius = computeNodeRadius(n);
        });
        initNodeCoordinates();

        TOPIC_NODE_MAP = buildTopicMap(payload.topics);
        applyTemporalData(payload.epochs);
        applyCorpusCoverage(payload.coverage);
        applyEntityIndex(payload.entity_index);
        // Menu filter dibangun dari data setelah simpul/sisi tersedia.
        populateEdgeCategoryMenu();
        populateMediaLensMenu();
        buildTopicNetworks();
        const canvasMode = !!(window.HorusCanvas && HorusCanvas.handles(allData.nodes.length));
        if (canvasMode) {
          HorusCanvas.mount(allData);
          // Lapisan SVG dibiarkan kosong, tetapi `nodeG` tetap seleksi kosong
          // supaya fungsi filter dan label yang memanggilnya jadi no-op,
          // bukan error.
          nodeG = nodeLayer.selectAll("g.node-item");
        } else {
          buildNodeLayer();
        }
        renderMinimapNodes();
        updateMacroStats();
        updateTimelineMilestone(null);
        applyCombinedFilters();
        // Sisi belum pernah digambar sampai ada filter yang memicu render;
        // boot harus menggambar subgraf awal secara eksplisit.
        renderActiveEdges(activeTopicEdges);
        updateEdgeCountBadge();
        renderSidebarEntities();
        if (!canvasMode) initForceSimulation();
        hideCanvasLoading();
        // Tautan diterapkan setelah tata letak berhenti bergerak: mode topik
        // butuh render bipartit yang belum siap sebelum itu. Timer di bawah
        // hanya jaring pengaman bila simulasi tidak pernah selesai.
        setTimeout(flushViewState, 1500);
      } catch (err) {
        console.error("[Visualizer] Gagal memuat artefak graf:", err);
        showBootError(err.message || String(err));
      }
    }

    bootstrapVisualizer();

