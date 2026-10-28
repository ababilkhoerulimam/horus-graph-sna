/**
 * Renderer canvas untuk graf besar.
 *
 * SVG membuat satu elemen DOM per simpul dan per sisi. Pada 77 simpul itu
 * wajar; pada 10.000 simpul / 50.000 sisi ia menjadi 60.000 elemen yang harus
 * ditata ulang setiap tick simulasi — diukur 2 fps pada mesin pengembangan.
 * Canvas menggambar semuanya sebagai piksel, jadi biayanya sebanding dengan
 * luas yang digambar, bukan dengan jumlah elemen.
 *
 * Yang dijaga:
 *
 * 1. Ambangnya eksplisit. Di bawah `THRESHOLD` simpul, jalur SVG tetap dipakai
 *    apa adanya: ia punya tooltip, label, dan navigasi keyboard yang sudah
 *    diuji. Canvas hanya mengambil alih saat SVG memang tidak lagi layak.
 * 2. Tata letak tidak dijalankan dengan simulasi gaya. Simulasi pada 10.000
 *    simpul butuh puluhan detik dan hasilnya berbeda tiap muat; susunan
 *    filotaksis deterministik memberi sebaran yang merata dalam hitungan
 *    milidetik.
 * 3. Level-of-detail: sisi disembunyikan saat zoom sangat jauh, label hanya
 *    saat zoom dekat dan hanya untuk simpul berderajat tertinggi.
 */
(function () {
  "use strict";

  const THRESHOLD = 2000;
  const EDGE_MIN_ZOOM = 0.25;
  const LABEL_MIN_ZOOM = 0.8;
  const LABEL_BUDGET = 60;
  const HIT_RADIUS = 12;

  const state = {
    active: false,
    canvas: null,
    ctx: null,
    nodes: [],
    edges: [],
    labels: [],
    width: 0,
    height: 0,
    k: 1,
    tx: 0,
    ty: 0,
    frame: 0,
    behavior: null,
    // Simpul yang lolos filter. null berarti semua aktif; ini pembeda yang
    // penting, karena Set kosong berarti "tidak ada yang lolos".
    activeIds: null,
    query: ""
  };

  function handles(count) {
    return Number(count) > THRESHOLD;
  }

  /**
   * Susunan filotaksis: jarak antar simpul merata tanpa simulasi.
   * Deterministik, O(n), dan tidak bergantung pada urutan pemanggilan.
   */
  function layout(nodes) {
    const golden = Math.PI * (3 - Math.sqrt(5));
    const radius = Math.sqrt(nodes.length) * 26;
    nodes.forEach((node, index) => {
      const r = radius * Math.sqrt((index + 0.5) / nodes.length);
      const angle = index * golden;
      node.x = Math.cos(angle) * r;
      node.y = Math.sin(angle) * r;
    });
  }

  function mount(data) {
    const host = svg && svg.node() ? svg.node().parentElement : null;
    if (!host) return false;

    const canvas = document.createElement("canvas");
    canvas.className = "graph-canvas";
    canvas.style.position = "absolute";
    canvas.style.inset = "0";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.cursor = "grab";
    host.appendChild(canvas);

    state.canvas = canvas;
    state.ctx = canvas.getContext("2d", { alpha: true });
    state.nodes = data.nodes || [];
    // Sisi diarahkan ke objek simpulnya sekali di sini. Kalau tidak, tiap
    // gambar harus mencari ujungnya, dan sisi yang ujungnya berupa id akan
    // dilewati diam-diam — kanvas kosong tanpa satu pun error.
    const byId = new Map(state.nodes.map(node => [node.id, node]));
    state.edges = (data.links || [])
      .map(link => ({
        source: byId.get(typeof getSourceId === "function" ? getSourceId(link) : link.source),
        target: byId.get(typeof getTargetId === "function" ? getTargetId(link) : link.target)
      }))
      .filter(edge => edge.source && edge.target);
    state.labels = state.nodes
      .slice()
      .sort((a, b) => (b.degree || 0) - (a.degree || 0))
      .slice(0, LABEL_BUDGET);
    state.active = true;

    layout(state.nodes);
    resize();
    bindZoom(canvas);
    bindPointer(canvas);
    // Tanpa fit, skala 1:1 pada 10.000 simpul hanya menampilkan sekitar 7%
    // luas graf: kanvas tampak kosong padahal isinya ada.
    fit();
    draw();

    window.addEventListener("resize", resize);
    return true;
  }

  function resize() {
    if (!state.canvas) return;
    const rect = state.canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    state.width = Math.max(1, Math.round(rect.width));
    state.height = Math.max(1, Math.round(rect.height));
    state.canvas.width = Math.round(state.width * ratio);
    state.canvas.height = Math.round(state.height * ratio);
    state.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    draw();
  }

  function bindZoom(canvas) {
    if (typeof d3 === "undefined") return;
    const behavior = d3.zoom()
      .scaleExtent([0.05, 8])
      .on("zoom", event => {
        state.k = event.transform.k;
        state.tx = event.transform.x;
        state.ty = event.transform.y;
        draw();
      });
    state.behavior = behavior;
    d3.select(canvas).call(behavior);
  }

  function bindPointer(canvas) {
    canvas.addEventListener("click", event => {
      const node = pick(event);
      if (node && typeof selectAndInspectNode === "function") selectAndInspectNode(node);
    });
    canvas.addEventListener("mousemove", event => {
      canvas.style.cursor = pick(event) ? "pointer" : "grab";
    });
  }

  /** Simpul terdekat dalam radius klik, dihitung di ruang layar. */
  function pick(event) {
    const rect = state.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    let best = null;
    let bestDistance = HIT_RADIUS * HIT_RADIUS;
    for (const node of state.nodes) {
      const sx = (node.x * state.k) + state.tx + (state.width / 2);
      const sy = (node.y * state.k) + state.ty + (state.height / 2);
      const dx = sx - x;
      const dy = sy - y;
      const distance = (dx * dx) + (dy * dy);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = node;
      }
    }
    return best;
  }

  /** Ubah zoom secara programatik; dipakai pengukur dan tombol reset tampilan. */
  function setView(k) {
    state.k = Math.max(0.05, Math.min(8, Number(k) || 1));
    draw();
  }

  function setEdges(edges) {
    const byId = new Map(state.nodes.map(node => [node.id, node]));
    state.edges = (edges || [])
      .map(link => ({
        source: byId.get(typeof getSourceId === "function" ? getSourceId(link) : link.source),
        target: byId.get(typeof getTargetId === "function" ? getTargetId(link) : link.target)
      }))
      .filter(edge => edge.source && edge.target);
    draw();
  }

  /**
   * Bingkai seluruh graf di dalam viewport.
   *
   * Diukur dari kotak pembatas simpul, bukan dari viewBox SVG: kanvas tidak
   * punya viewBox, dan memakai skala tetap membuat graf besar tampil sebagai
   * titik-titik di tengah layar.
   */
  function fit(paddingPx = 48) {
    if (!state.nodes.length || !state.width) return;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const node of state.nodes) {
      const r = node.node_radius || 6;
      minX = Math.min(minX, node.x - r);
      maxX = Math.max(maxX, node.x + r);
      minY = Math.min(minY, node.y - r);
      maxY = Math.max(maxY, node.y + r);
    }
    const spanX = Math.max(1, maxX - minX);
    const spanY = Math.max(1, maxY - minY);
    const usableW = Math.max(1, state.width - (paddingPx * 2));
    const usableH = Math.max(1, state.height - (paddingPx * 2));
    const k = Math.max(0.05, Math.min(8, Math.min(usableW / spanX, usableH / spanY)));
    state.k = k;
    state.tx = -((minX + maxX) / 2) * k;
    state.ty = -((minY + maxY) / 2) * k;
    // Transform d3 ikut disetel, kalau tidak zoom berikutnya melompat balik ke
    // posisi lama: dua sumber kebenaran untuk satu angka.
    if (state.behavior && typeof d3 !== "undefined") {
      d3.select(state.canvas).call(
        state.behavior.transform,
        d3.zoomIdentity.translate(state.tx, state.ty).scale(k)
      );
    }
    draw();
  }

  /** Simpul yang lolos filter; null berarti semua. */
  function setActive(ids) {
    if (ids === null || ids === undefined) {
      state.activeIds = null;
    } else {
      state.activeIds = new Set(Array.from(ids, value => (typeof value === "object" ? value.id : value)));
    }
    draw();
  }

  /** Pencarian teks: simpul yang tidak cocok diredupkan, bukan dihilangkan. */
  function setQuery(text) {
    state.query = String(text || "").trim().toLowerCase();
    draw();
  }

  /** Gambar ulang setelah radius atau warna simpul berubah di luar kanvas. */
  function refresh() {
    draw();
  }

  /**
   * Porsi simpul yang jatuh di dalam viewport. Dipakai pengukur, bukan UI:
   * kanvas yang tidak di-fit tetap "bekerja" tapi hanya menampilkan sepetak.
   */
  function coverage() {
    if (!state.nodes.length || !state.width) return 0;
    let inside = 0;
    for (const node of state.nodes) {
      const sx = (node.x * state.k) + state.tx + (state.width / 2);
      const sy = (node.y * state.k) + state.ty + (state.height / 2);
      if (sx >= 0 && sx <= state.width && sy >= 0 && sy <= state.height) inside += 1;
    }
    return inside / state.nodes.length;
  }

  function _visible(node) {
    if (state.query) {
      const label = String(node.display_label || node.label || node.id || "").toLowerCase();
      if (!label.includes(state.query)) return false;
    }
    if (state.activeIds && !state.activeIds.has(node.id)) return false;
    return true;
  }

  function draw() {
    const ctx = state.ctx;
    if (!ctx) return;
    const k = state.k;

    ctx.clearRect(0, 0, state.width, state.height);
    ctx.save();
    ctx.translate((state.width / 2) + state.tx, (state.height / 2) + state.ty);
    ctx.scale(k, k);

    if (k >= EDGE_MIN_ZOOM) {
      ctx.strokeStyle = "rgba(148, 163, 184, 0.28)";
      ctx.lineWidth = Math.max(0.4, 0.9 / k);
      ctx.beginPath();
      for (const edge of state.edges) {
        const source = edge.source;
        const target = edge.target;
        if (!source || !target) continue;
        if (source.x === undefined || target.x === undefined) continue;
        // Sisi hanya digambar bila kedua ujungnya lolos filter; sisi ke simpul
        // yang diredupkan akan terbaca sebagai koneksi yang masih hidup.
        if (!_visible(source) || !_visible(target)) continue;
        ctx.moveTo(source.x, source.y);
        ctx.lineTo(target.x, target.y);
      }
      ctx.stroke();
    }

    const radiusScale = Math.min(1, Math.max(0.35, k));
    for (const node of state.nodes) {
      const radius = Math.max(1.5, Math.min(22, (node.node_radius || 6) * radiusScale));
      // Redup, bukan hilang: pembaca masih perlu melihat di mana sisanya berada.
      ctx.globalAlpha = _visible(node) ? 1 : 0.06;
      ctx.beginPath();
      ctx.fillStyle = node.color || "#94A3B8";
      ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    if (k >= LABEL_MIN_ZOOM) {
      ctx.fillStyle = "#E2E8F0";
      ctx.font = `${Math.round(11 / k)}px Inter, system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      for (const node of state.labels) {
        if (!_visible(node)) continue;
        const label = node.display_label || node.label || node.id;
        if (!label) continue;
        ctx.fillText(label, node.x, node.y + ((node.node_radius || 6) * radiusScale) + 3);
      }
    }

    ctx.restore();
  }

  window.HorusCanvas = {
    handles: handles,
    mount: mount,
    setEdges: setEdges,
    setView: setView,
    setActive: setActive,
    setQuery: setQuery,
    fit: fit,
    refresh: refresh,
    coverage: coverage,
    draw: draw,
    get active() {
      return state.active;
    },
    get threshold() {
      return THRESHOLD;
    }
  };
})();
