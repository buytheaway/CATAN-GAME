# Maps Schema (v1)

This document describes the data-driven map format used by the engine.

## Top-Level Fields

- `name` (string, optional): map identifier.
- `version` (int, required): schema version. Current = `1`.
- `size` (float, optional): tile size metadata (UI may override).
- `tiles` (list, required): axial coordinates and terrain/number definitions.
- `terrain_deck` (list, optional): terrain deck used when any tile uses `"random"`.
- `number_deck` (list, optional): number deck used when any tile uses `"random"`.
- `ports` (list, optional): explicit ports list (edge + type).
- `ports_auto` (object, optional): auto-port settings.
- `robber_tile` (int, optional): fixed robber tile index. If omitted, desert tile is used.
- `pirate_tile` (int, optional): fixed pirate tile index (sea tile). If omitted and pirate enabled, first sea tile is used.
- `rules` (object, optional): scenario parameters (e.g., `target_vp`, `limits`, `robber_count`, `enable_seafarers`, `max_ships`, `enable_pirate`, `enable_gold`, `enable_move_ship`).

## Tile Entry

Each tile entry uses axial coordinates:

```
{"q": 0, "r": -2, "terrain": "forest", "number": 6}
```

Allowed values:
- `terrain`: `"forest" | "hills" | "pasture" | "fields" | "mountains" | "desert" | "sea" | "gold" | "random"`
- `number`: `2..12 (not 7) | null | "random"`

If `terrain` is `"random"`, the engine draws from `terrain_deck`.
If `number` is `"random"`, the engine draws from `number_deck` for non-desert, non-sea tiles.

## Ports

Explicit ports:

```
"ports": [
  {"edge": [12, 19], "type": "3:1"},
  {"edge": [7, 8], "type": "2:1:wood"}
]
```

Auto ports:

```
"ports_auto": {
  "count": 9,
  "deck": ["3:1", "3:1", "3:1", "3:1", "2:1:wood", "2:1:brick", "2:1:sheep", "2:1:wheat", "2:1:ore"]
}
```

If `ports` is provided, `ports_auto` is ignored.
If neither is provided, a default 9-port deck is used.

## Notes

- Graph data (vertices/edges/adjacency) is derived from tile geometry in v1.
- For scenario rules, add fields inside `rules`:
  - `target_vp` (int, default 10)
  - `limits` (object): `{ "roads": 15, "settlements": 5, "cities": 4 }`
  - `robber_count` (int, default 1)
  - `enable_seafarers` (bool, default false)
  - `max_ships` (int, default 15)
  - `enable_pirate` (bool, default false)
  - `enable_gold` (bool, default false)
  - `enable_move_ship` (bool, default false)
- Base map preset is located at `app/assets/maps/base_standard.json`.
