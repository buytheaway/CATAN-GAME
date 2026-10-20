// Browser-only PUBLIC fixture adapter. Never included in App or production build.
// No rules, commands, account data, hidden assignments or live server connection.
(async () => {
  const params = new URLSearchParams(location.search);
  const key = params.get("scene") || "base";
  const model = params.get("model") === "glb" ? "glb" : "procedural";
  while (!window.__fogFixture?.snapshot()) await new Promise(resolve => setTimeout(resolve, 30));
  const frame = window.__fogFixture.snapshot(), state = frame.state;
  if (!["fog-before", "fog-after", "pieces", "threats"].includes(key)) {
    const boards = await (await fetch("/boards.json")).json();
    if (!Object.hasOwn(boards, key)) throw Error("Unknown public review scene");
    const board = structuredClone(boards[key]);
    const count = board.display_players; delete board.display_players;
    Object.assign(state, board);
    state.players = Array.from({ length: count }, (_, pid) => ({
      pid, name: ["Red", "Blue", "Green", "Amber"][pid], color: ["red", "blue", "green", "orange"][pid],
      vp: 3, resource_count: pid === 0 ? 10 : 4, dev_count: 0,
      ...(pid === 0 ? { res: { wood: 2, brick: 2, sheep: 2, wheat: 2, ore: 2 }, dev_cards: [] } : {}),
    }));
    state.scenario = { rules: { starting_islands: null, new_island_vp: 0 }, home_islands: {}, awarded_islands: {} };
    state.legal = { pid: 0, roads: [], ships: [], cities: [], settlements: [], robber_tiles: [], pirate_tiles: [],
      robber_victims: {}, pirate_victims: {}, move_ship: { sources: [], targets: {} } };
  } else if (key === "fog-after") {
    // A new synthetic PUBLIC view, not a secret recipe or future assignment.
    const revealed = [["forest", 6], ["sea", null], ["gold", 8]];
    state.tiles.filter(tile => tile.visibility === "hidden").forEach((tile, index) => {
      tile.visibility = "revealed"; [tile.terrain, tile.number] = revealed[index % revealed.length];
    });
  } else if (key === "threats") {
    // Public component study: retain the actual robber, show the pirate on the
    // already-public Sea tile, remove owned ships from this small display area.
    state.pirate_tile = 1; state.occupied_ships = {};
    state.legal = { pid: 0, roads: [], ships: [], cities: [], settlements: [], robber_tiles: [], pirate_tiles: [] };
  }
  if (params.get("palette") === "light") {
    state.players[2].color = "white"; state.players[2].name = "White";
    state.players[3].color = "purple"; state.players[3].name = "Purple";
  }
  state.map_meta = { name: (state.map_meta?.name || key) + " · public visual study" };
  state.game_events = [];
  frame.match_id += 100; frame.tick = 1;
  window.__fogFixture.publish(frame);
  // Existing real controls; fixture adapter never changes a camera/material/mesh.
  const choose = async (label, value) => {
    let select;
    for (let tries = 0; tries < 200; tries++) {
      select = document.querySelector('select[aria-label="' + label + '"]');
      if (select) break;
      await new Promise(resolve => setTimeout(resolve, 30));
    }
    if (!select) return;
    const native = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set;
    native.call(select, value); select.dispatchEvent(new Event("change", { bubbles: true }));
  };
  // A non-Fog map intentionally has no Fog/Ship effects select when absent.
  if (state.tiles.some(tile => tile.visibility === "hidden")) await choose("Fog effects", "still");
  if (Object.keys(state.occupied_ships).length) await choose("Ship effects", "static");
  await choose("Construction effects", "static");
  await choose("Robber & pirate effects", "static");
  await choose("Ship model", model);
  window.__artReview = { ready: true, scene: key, model, synthetic: true };
})().catch(error => { window.__artReview = { error: error.message }; console.error(error); });
