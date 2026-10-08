// Zelda 3 multi-layer map viewer.
// Loads the extracted map_data.json (via data.js) and the rendered PNGs and
// builds an interactive overworld map + dungeon floor browser.

(function () {
  "use strict";

  const DATA = window.MAP_DATA;
  const IMG_BASE = "../extracted_assets/images/";
  const ROOM_TILES = 64; // logical room grid

  const state = {
    world: "light_world",
    dungeonKey: null,
    floor: null,
    roomId: null,
    filters: { chests: true, connections: true, doors: true, bosses: true },
  };

  // room_id -> {dungeonKey, room}
  const roomIndex = {};
  const dungeonKeys = Object.keys(DATA.dungeons);
  dungeonKeys.forEach((k) => {
    DATA.dungeons[k].rooms.forEach((r) => {
      roomIndex[r.room_id] = { dungeonKey: k, room: r };
    });
  });

  // ---------------------------------------------------------------- helpers
  function floorSortValue(f) {
    if (!f) return 999;
    if (f[0] === "B") return -parseInt(f.slice(1), 10);
    return parseInt(f, 10);
  }

  function floorsOf(dungeon) {
    const set = new Set();
    dungeon.rooms.forEach((r) => r.floor_level && set.add(r.floor_level));
    return Array.from(set).sort((a, b) => floorSortValue(a) - floorSortValue(b));
  }

  function isBossRoom(room) {
    return room.interactive_elements.some((e) => e.type === "chest" && e.big_chest);
  }


  // ----------------------------------------------------------- overworld map
  const canvas = document.getElementById("world-canvas");
  const ctx = canvas.getContext("2d");
  const view = { scale: 1, x: 0, y: 0, img: null, dragging: false, lx: 0, ly: 0 };

  function loadWorldImage() {
    const img = new Image();
    img.onload = () => { view.img = img; fitWorld(); drawWorld(); };
    img.src = IMG_BASE + "overworld_" + (state.world === "light_world" ? "light" : "dark") + ".png";
  }

  function fitWorld() {
    const rect = canvas.getBoundingClientRect();
    const s = Math.min(rect.width / 4096, rect.height / 4096) * 0.95;
    view.scale = s;
    view.x = (rect.width - 4096 * s) / 2;
    view.y = (rect.height - 4096 * s) / 2;
  }

  function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function entrancesOfWorld() {
    return DATA.overworld[state.world].entrances || [];
  }

  function drawWorld() {
    const rect = canvas.getBoundingClientRect();
    ctx.clearRect(0, 0, rect.width, rect.height);
    ctx.fillStyle = "#05070d";
    ctx.fillRect(0, 0, rect.width, rect.height);
    if (!view.img) return;
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(view.img, view.x, view.y, 4096 * view.scale, 4096 * view.scale);
    entrancesOfWorld().forEach((e) => {
      const px = view.x + e.x * view.scale;
      const py = view.y + e.y * view.scale;
      const isDungeon = !!roomIndex[e.leads_to_room_id];
      ctx.beginPath();
      ctx.arc(px, py, isDungeon ? 6 : 3.5, 0, Math.PI * 2);
      ctx.fillStyle = isDungeon ? "#e0b64a" : "rgba(120,200,255,0.6)";
      ctx.fill();
      if (isDungeon) { ctx.lineWidth = 2; ctx.strokeStyle = "#0b0f1a"; ctx.stroke(); }
    });
  }

  function screenToWorld(sx, sy) {
    return { x: (sx - view.x) / view.scale, y: (sy - view.y) / view.scale };
  }

  function nearestEntrance(wx, wy, maxD) {
    let best = null, bestD = maxD;
    entrancesOfWorld().forEach((e) => {
      const d = Math.hypot(e.x - wx, e.y - wy);
      if (d < bestD) { bestD = d; best = e; }
    });
    return best;
  }


  canvas.addEventListener("mousedown", (ev) => {
    view.dragging = true; view.lx = ev.clientX; view.ly = ev.clientY;
    canvas.classList.add("dragging");
  });
  window.addEventListener("mouseup", () => { view.dragging = false; canvas.classList.remove("dragging"); });
  canvas.addEventListener("mousemove", (ev) => {
    const rect = canvas.getBoundingClientRect();
    if (view.dragging) {
      view.x += ev.clientX - view.lx;
      view.y += ev.clientY - view.ly;
      view.lx = ev.clientX; view.ly = ev.clientY;
      drawWorld();
    } else {
      const w = screenToWorld(ev.clientX - rect.left, ev.clientY - rect.top);
      const best = nearestEntrance(w.x, w.y, 40 / view.scale);
      document.getElementById("world-hint").textContent = best
        ? (best.name || "Eingang") + " \u2192 Raum " + (best.leads_to_room_id ?? "?")
        : "";
    }
  });
  canvas.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
    const before = screenToWorld(mx, my);
    const factor = ev.deltaY < 0 ? 1.15 : 1 / 1.15;
    view.scale *= factor;
    view.x = mx - before.x * view.scale;
    view.y = my - before.y * view.scale;
    drawWorld();
  }, { passive: false });
  canvas.addEventListener("click", (ev) => {
    const rect = canvas.getBoundingClientRect();
    const w = screenToWorld(ev.clientX - rect.left, ev.clientY - rect.top);
    const best = nearestEntrance(w.x, w.y, 60 / view.scale);
    if (best && roomIndex[best.leads_to_room_id]) {
      openDungeon(roomIndex[best.leads_to_room_id].dungeonKey, best.leads_to_room_id);
    }
  });

  // -------------------------------------------------------------- dungeon UI
  const dungeonSelect = document.getElementById("dungeon-select");
  dungeonKeys.forEach((k) => {
    const o = document.createElement("option");
    o.value = k;
    o.textContent = DATA.dungeons[k].name + " (" + DATA.dungeons[k].rooms.length + " R\u00e4ume)";
    dungeonSelect.appendChild(o);
  });
  dungeonSelect.addEventListener("change", () => openDungeon(dungeonSelect.value, null));

  function openDungeon(key, roomId) {
    if (!key) return;
    state.dungeonKey = key;
    dungeonSelect.value = key;
    const dungeon = DATA.dungeons[key];
    const floors = floorsOf(dungeon);
    state.floor = roomId != null && roomIndex[roomId]
      ? roomIndex[roomId].room.floor_level
      : (floors.length ? floors[0] : null);
    state.roomId = roomId != null ? roomId : null;
    renderFloors();
    renderRoomStrip();
    renderRoom(state.roomId);
    document.getElementById("dungeon-meta").textContent =
      dungeon.name + " \u00b7 " + dungeon.rooms.length + " R\u00e4ume \u00b7 " + floors.length + " Stockwerke";
  }

  function renderFloors() {
    const slider = document.getElementById("floor-slider");
    slider.innerHTML = "";
    const dungeon = DATA.dungeons[state.dungeonKey];
    if (!dungeon) return;
    floorsOf(dungeon).slice().reverse().forEach((f) => {
      const btn = document.createElement("button");
      btn.className = "floor-btn px-2 py-2 rounded text-sm font-semibold bg-zelda-bg border border-zelda-edge";
      if (f === state.floor) btn.classList.add("active");
      btn.textContent = f;
      btn.dataset.floor = f;
      btn.addEventListener("click", () => {
        state.floor = f;
        state.roomId = null;
        renderFloors(); renderRoomStrip(); renderRoom(null);
      });
      slider.appendChild(btn);
    });
  }

  function roomsOnFloor() {
    const dungeon = DATA.dungeons[state.dungeonKey];
    if (!dungeon) return [];
    return dungeon.rooms.filter((r) => r.floor_level === state.floor);
  }

  function renderRoomStrip() {
    const strip = document.getElementById("room-strip");
    strip.innerHTML = "";
    roomsOnFloor().forEach((r) => {
      const wrap = document.createElement("div");
      wrap.className = "room-thumb relative shrink-0 cursor-pointer rounded overflow-hidden border border-zelda-edge";
      wrap.dataset.room = r.room_id;
      if (r.room_id === state.roomId) wrap.classList.add("selected");
      const img = document.createElement("img");
      img.src = IMG_BASE + "room_" + String(r.room_id).padStart(3, "0") + ".png";
      img.className = "w-20 h-20 object-cover block";
      wrap.appendChild(img);
      if (state.filters.bosses && isBossRoom(r)) {
        const badge = document.createElement("div");
        badge.className = "absolute top-0 right-0 text-[10px] bg-red-600 px-1 rounded-bl";
        badge.textContent = "BOSS";
        wrap.appendChild(badge);
      }
      const label = document.createElement("div");
      label.className = "absolute bottom-0 left-0 right-0 text-[10px] bg-black/60 text-center";
      label.textContent = "0x" + r.room_id.toString(16).toUpperCase().padStart(2, "0");
      wrap.appendChild(label);
      wrap.addEventListener("click", () => {
        state.roomId = r.room_id;
        renderRoomStrip();
        renderRoom(r.room_id);
      });
      strip.appendChild(wrap);
    });
    if (!roomsOnFloor().length) {
      strip.innerHTML = '<div class="text-slate-500 text-xs p-2">Keine R\u00e4ume auf diesem Stockwerk.</div>';
    }
  }


  // ------------------------------------------------------------- room viewer
  const roomView = document.getElementById("room-view");

  function renderRoom(roomId) {
    if (roomId == null || !roomIndex[roomId]) {
      roomView.innerHTML = '<div class="text-slate-500 text-sm mt-10">Kein Raum ausgew\u00e4hlt.</div>';
      return;
    }
    const entry = roomIndex[roomId];
    const room = entry.room;
    roomView.innerHTML = "";

    const container = document.createElement("div");
    container.className = "w-full max-w-[512px]";

    const wrap = document.createElement("div");
    wrap.className = "relative";
    wrap.style.width = "100%";
    wrap.style.aspectRatio = "1 / 1";

    const img = document.createElement("img");
    img.src = IMG_BASE + "room_" + String(roomId).padStart(3, "0") + ".png";
    img.className = "w-full h-full block rounded border border-zelda-edge";
    img.style.imageRendering = "pixelated";
    wrap.appendChild(img);

    const overlay = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    overlay.setAttribute("viewBox", "0 0 512 512");
    overlay.classList.add("absolute", "inset-0", "w-full", "h-full");
    wrap.appendChild(overlay);

    const markers = [];
    if (state.filters.connections) {
      (room.connections.staircases || []).forEach((c) => markers.push({ kind: "stair", c }));
      (room.connections.pit_falls || []).forEach((c) => markers.push({ kind: "pit", c }));
    }
    if (state.filters.chests) {
      (room.interactive_elements || []).filter((e) => e.type === "chest").forEach((c) => markers.push({ kind: "chest", c }));
    }
    if (state.filters.doors) {
      (room.interactive_elements || []).filter((e) => e.type === "locked_door").forEach((c) => markers.push({ kind: "door", c }));
    }

    markers.forEach((m) => {
      const x = (m.c.tile_x != null ? m.c.tile_x : 0) * 8;
      const y = (m.c.tile_y != null ? m.c.tile_y : 0) * 8;
      const color = m.kind === "stair" ? "#e0b64a" : m.kind === "pit" ? "#8b5cf6" : m.kind === "door" ? "#4ade80" : "#f2c442";
      const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("cx", x + 4);
      dot.setAttribute("cy", y + 4);
      dot.setAttribute("r", 7);
      dot.setAttribute("fill", color);
      dot.setAttribute("stroke", "#0b0f1a");
      dot.setAttribute("stroke-width", "2");
      dot.style.cursor = "pointer";
      dot.style.pointerEvents = "all";
      dot.addEventListener("mouseenter", () => {
        dot.setAttribute("r", 10);
        const target = m.c.target_room_id;
        const el = target != null ? findTargetElement(target) : null;
        if (el) drawLink(dot, el, color);
      });
      dot.addEventListener("mouseleave", () => { dot.setAttribute("r", 7); clearLinks(); });
      overlay.appendChild(dot);

      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      if (m.kind === "chest") {
        title.textContent = "Truhe" + (m.c.big_chest ? " (gro\u00df)" : "") + " \u2013 Item " + m.c.item_id;
      } else if (m.kind === "door") {
        title.textContent = "T\u00fcr (" + m.c.direction + ", " + m.c.kind + ")";
      } else {
        title.textContent = (m.kind === "stair" ? "Treppe" : "Fallloch") + " \u2192 Raum " + m.c.target_room_id +
          (m.c.target_floor ? " (" + m.c.target_floor + ")" : "");
      }
      dot.appendChild(title);
    });

    container.appendChild(wrap);

    const info = document.createElement("div");
    info.className = "text-xs text-slate-400 mt-3";
    info.innerHTML =
      "<div class='font-semibold text-slate-200'>" + room.name + "</div>" +
      "<div>ID 0x" + roomId.toString(16).toUpperCase().padStart(2, "0") +
      " \u00b7 Stockwerk " + (room.floor_level || "?") +
      " \u00b7 " + entry.dungeonKey.replace(/_/g, " ") + "</div>";
    container.appendChild(info);

    roomView.appendChild(container);
  }

  function findTargetElement(roomId) {
    const thumb = document.querySelector('.room-thumb[data-room="' + roomId + '"]');
    if (thumb) return thumb;
    const info = roomIndex[roomId];
    if (info) {
      const fb = document.querySelector('.floor-btn[data-floor="' + info.room.floor_level + '"]');
      if (fb) return fb;
    }
    return null;
  }

  // cross-panel connection lines
  const linkSvg = document.getElementById("link-overlay");
  function drawLink(fromEl, toEl, color) {
    clearLinks();
    const a = fromEl.getBoundingClientRect();
    const b = toEl.getBoundingClientRect();
    const x1 = a.left + a.width / 2, y1 = a.top + a.height / 2;
    const x2 = b.left + b.width / 2, y2 = b.top + b.height / 2;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const mx = (x1 + x2) / 2;
    path.setAttribute("d", "M " + x1 + " " + y1 + " C " + mx + " " + y1 + ", " + mx + " " + y2 + ", " + x2 + " " + y2);
    path.setAttribute("stroke", color);
    path.setAttribute("stroke-width", "3");
    path.setAttribute("fill", "none");
    path.setAttribute("opacity", "0.9");
    path.setAttribute("stroke-dasharray", "6 4");
    linkSvg.appendChild(path);
  }
  function clearLinks() { linkSvg.innerHTML = ""; }



  // --------------------------------------------------------------- filters
  function bindFilter(id, key) {
    const el = document.getElementById(id);
    el.addEventListener("change", () => {
      state.filters[key] = el.checked;
      renderRoomStrip();
      if (state.roomId != null) renderRoom(state.roomId);
    });
  }
  bindFilter("f-chests", "chests");
  bindFilter("f-connections", "connections");
  bindFilter("f-doors", "doors");
  bindFilter("f-bosses", "bosses");

  // ----------------------------------------------------------- world toggle
  function switchWorld(w) {
    state.world = w;
    document.getElementById("world-light").className =
      "px-3 py-1 rounded font-semibold text-sm " + (w === "light_world" ? "bg-zelda-accent text-black" : "bg-zelda-edge text-slate-300");
    document.getElementById("world-dark").className =
      "px-3 py-1 rounded font-semibold text-sm " + (w === "dark_world" ? "bg-zelda-accent text-black" : "bg-zelda-edge text-slate-300");
    loadWorldImage();
  }
  document.getElementById("world-light").addEventListener("click", () => switchWorld("light_world"));
  document.getElementById("world-dark").addEventListener("click", () => switchWorld("dark_world"));

  window.addEventListener("resize", () => { resizeCanvas(); fitWorld(); drawWorld(); });

  // ------------------------------------------------------------------ start
  resizeCanvas();
  loadWorldImage();
  const startKey = DATA.dungeons["tower_of_hera"] ? "tower_of_hera" : dungeonKeys[0];
  if (startKey) {
    const firstRoom = DATA.dungeons[startKey].rooms[0];
    openDungeon(startKey, firstRoom ? firstRoom.room_id : null);
  }
})();
