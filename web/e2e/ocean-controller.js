// PUBLIC synthetic display adapter only. No backend, private map or rules executor.
(async () => {
  const params = new URLSearchParams(location.search), key = params.get("scene") || "base";
  while (!window.__fogFixture?.snapshot()) await new Promise(resolve => setTimeout(resolve, 20));
  const frame = window.__fogFixture.snapshot(), state = frame.state;
  if (key === "outer-legal") {
    const fixture = await (await fetch("/legal-outer.json")).json();
    Object.assign(state, fixture.state);
  } else if (!["fog-before", "fog-after", "seven", "fifty"].includes(key)) {
    const boards = await (await fetch("/boards.json")).json();
    if (!Object.hasOwn(boards, key)) throw Error("Unknown public ocean scene");
    const board = structuredClone(boards[key]), count = board.display_players; delete board.display_players;
    Object.assign(state, board);
    state.players = Array.from({ length: count }, (_, pid) => ({ pid, name: ["Red", "Blue", "Green", "Amber"][pid],
      color: ["red", "blue", "green", "orange"][pid], vp: 3, resource_count: pid ? 4 : 10, dev_count: 0,
      ...(pid ? {} : { res: { wood: 2, brick: 2, sheep: 2, wheat: 2, ore: 2 }, dev_cards: [] }) }));
    state.scenario = { rules: { starting_islands: null, new_island_vp: 0 }, home_islands: {}, awarded_islands: {} };
    state.legal = { pid: 0, roads: [], ships: [], cities: [], settlements: [], robber_tiles: [], pirate_tiles: [],
      robber_victims: {}, pirate_victims: {}, move_ship: { sources: [], targets: {} } };
    // Display an existing outer playable sea edge, never a decorative cell.
    const outer = state.edges.filter(edge => state.edge_adj_hexes[edge.join(",")].length === 1
      && state.edge_adj_hexes[edge.join(",")].some(i => state.tiles[i].terrain === "sea")
      && !state.edge_adj_hexes[edge.join(",")].includes(state.pirate_tile)
      && !state.ports.some(([port]) => port.join(",") === edge.join(",")));
    if (outer.length) state.occupied_ships[outer.at(-1).join(",")] = 0;
  } else if (key === "fog-after") {
    const examples = [["forest", 6], ["sea", null], ["gold", 8]];
    state.tiles.filter(tile => tile.visibility === "hidden").forEach((tile, index) => {
      tile.visibility = "revealed"; [tile.terrain, tile.number] = examples[index % examples.length];
    });
  }
  state.map_meta = { name: (state.map_meta?.name || key) + " · public ocean study" };
  state.game_events = []; frame.match_id += 100; frame.tick = 1;
  window.__fogFixture.publish(frame);
  const choose = async (label, value) => {
    for (let tries = 0; tries < 200; tries++) {
      const select = document.querySelector('select[aria-label="' + label + '"]');
      if (select) {
        Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(select, value);
        select.dispatchEvent(new Event("change", { bubbles: true })); return;
      }
      if (tries > 12) return;
      await new Promise(resolve => setTimeout(resolve, 20));
    }
  };
  if (params.get("motion") !== "normal") {
    await choose("Fog effects", "still"); await choose("Ship effects", "static");
    await choose("Construction effects", "static"); await choose("Robber & pirate effects", "static");
  }
  if (params.get("model") === "glb") await choose("Ship model", "glb");
  const nav = document.createElement("aside"); nav.dataset.oceanPreviewToolbar = "true";
  nav.style.cssText = "position:fixed;left:12px;bottom:175px;z-index:500;background:#102938ed;color:#eaf5fa;padding:12px;border:1px solid #567180;border-radius:8px;max-width:620px;font:13px system-ui";
  const source = params.get("source") || "after", rings = params.get("rings") || "1", enabled = params.get("frame") !== "0";
  nav.innerHTML = '<strong>5D.2 · actual Board3D / synthetic PUBLIC display</strong><p style="margin:5px 0">No server, gameplay or secret Fog assignments. Outer ship is a synthetic display on an existing playable edge.</p>';
  const select = (label, choices, value) => {
    const element = document.createElement("select"); element.setAttribute("aria-label", label); element.style.margin = "4px";
    for (const [id, text] of choices) { const option = document.createElement("option"); option.value = id; option.textContent = text; element.append(option); }
    element.value = value; nav.append(element); return element;
  };
  const scene = select("Ocean scene", [["base","Base Standard"],["new-shores-3","New Shores3"],["new-shores-4","New Shores4"],
    ["four-islands-3","Four Islands3"],["four-islands-4","Four Islands4"],["fog-before","Fog before"],["fog-after","Fog after"],
    ["seven","7 hexes"],["fifty","50 hexes"],["outer-legal","Legal NS4 outer ship opening"]], key);
  const side = select("Ocean source", [["before","Before · committed"],["after","After · working renderer"]], source);
  const ring = select("Ocean rings", [["0","No decorative hexes"],["1","One ring"],["2","Two rings"]], rings);
  const border = select("Ocean frame", [["1","Frame on"],["0","Frame off"]], enabled ? "1" : "0");
  if (source === "before") { ring.value = "0"; border.value = "0"; ring.disabled = true; border.disabled = true; }
  const reload = () => { const next = new URL(location.href); next.searchParams.set("scene",scene.value); next.searchParams.set("source",side.value);
    next.searchParams.set("rings",ring.value); next.searchParams.set("frame",border.value); next.searchParams.set("fixture",scene.value === "fifty" ? "large" : "partial"); location.href = next; };
  scene.onchange = reload; side.onchange = reload;
  const update = () => { history.replaceState(null,"",'?'+new URLSearchParams({...Object.fromEntries(params),rings:ring.value,frame:border.value}));
    window.dispatchEvent(new CustomEvent("catan-ocean-preview",{detail:{rings:Number(ring.value),frame:border.value === "1"}})); };
  ring.onchange = update; border.onchange = update;
  const close = document.createElement("button"); close.textContent = "Close-up"; close.onclick = () => {
    const canvas = document.querySelector("canvas"); const rect = canvas.getBoundingClientRect();
    canvas.dispatchEvent(new WheelEvent("wheel",{deltaY:-600,clientX:rect.x+rect.width/2,clientY:rect.y+rect.height/2,bubbles:true,cancelable:true}));
  }; nav.append(close);
  const reset = document.createElement("button"); reset.textContent = "Overview / reset";
  reset.onclick = () => document.querySelector('button[aria-label="Reset Camera"]')?.click(); nav.append(reset);
  document.body.append(nav);
  document.querySelector(".fog-preview")?.remove();
  window.__oceanPreview = { ready: true, scene: key, source, synthetic: true };
})().catch(error => { window.__oceanPreview = { error: error.message }; console.error(error); });
