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
- `robber_tile` (int, optional): fixed land tile index, or `-1` for an offboard Seafarers start. If omitted, desert is used; no-desert Seafarers uses `-1`. The historical Base no-desert fallback remains index 0. Values below -1 and offboard Base positions reject.
- `pirate_tile` (int, optional): fixed pirate tile index (sea tile). If omitted and pirate enabled, first sea tile is used.
- `rules` (object, optional): scenario parameters (e.g., `target_vp`, `limits`, `robber_count`, `enable_seafarers`, `max_ships`, `enable_pirate`, `enable_gold`, `enable_move_ship`).

## Tile Entry

Each tile entry uses axial coordinates:

```
{"q": 0, "r": -2, "terrain": "forest", "number": 6}
```

Allowed values:
- `q`/`r`: integers (not booleans); coordinate pairs must be unique.
- `terrain`: `"forest" | "hills" | "pasture" | "fields" | "mountains" | "desert" | "sea" | "gold" | "random"`
- `number`: `2..12 (not 7) | null | "random"`

If `terrain` is `"random"`, the engine draws from `terrain_deck`.
If `number` is `"random"`, the engine draws from `number_deck` for non-desert, non-sea tiles.
Random decks must contain valid terrain/number values and enough entries for the
materialized slots. Extra deck entries are permitted for custom maps. Sea/desert
cannot have an explicit number; random numbers on those tiles become null.

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

At new-map construction, each port must reference an existing land coast edge
(one land side, sea or the outer frame on the other side). Ports cannot share
endpoints; allowed kinds are `3:1` and `2:1:<wood|brick|sheep|wheat|ore>`.
Authored edges/kinds/order are retained without shuffle. Auto placement is
deterministic for the materialized geometry/terrain, with shuffled deck kinds;
count must be nonnegative and is limited by the supplied deck and coast capacity.
Tiny custom coasts can yield fewer ports than requested. Historical saved boards
are restored directly, without re-running these creation checks or repairing ports.

## Notes

- Graph data (vertices/edges/adjacency) is derived from tile geometry in v1.
- Island IDs are derived from the stored shared-edge land graph, not extra JSON
  fields. IDs use the smallest original tile index in each connected component.
- The map schema version remains 1. Trusted engine snapshots are separate codec
  v2; S2A extends its Seafarers robber value domain to -1, while frozen v1 remains
  readable for historical on-board states. Old S1 binaries cannot read new
  offboard heads. Snapshot format and match ruleset compatibility are separate.
- Validation does not certify custom-map balance, all setup choices, no adjacent
  6/8, or unimplemented scenario bonuses/fog/start regions.
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
