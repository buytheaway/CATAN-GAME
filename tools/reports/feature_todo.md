# Feature TODO

## Blockers (breaks gameplay)
- Implement starting resources from 2nd settlement during setup.
- Wire main menu Multiplayer button to real lobby_ui.LobbyWindow (current placeholder).

## Multiplayer correctness
- Add reconnect token/session handling (avoid name-based collisions).
- Add explicit tests for seq/duplicate command handling and rematch flow.
- Validate max_players rendering for >4 players in UI.

## UX / Visual polish
- Replace port text badges with ship + ratio + resource icon visuals.
- Replace road/settlement/city shapes with SVG/tinted piece assets.
- Add water/coastline shading to board for clearer map boundaries.

## Nice-to-have
- Player-to-player trade mechanics.
- Expansion rules (Seafarers) and 5-6 player extension rules.