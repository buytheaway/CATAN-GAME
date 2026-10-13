"""Independent transcription of 2021 printed pp.9/10; funded command replays.

Frame spaces are printed on cardboard, not counted in the loose-hex inventory.
Funding is explicit test setup, not a claim of a full natural competitive match.
"""
from collections import Counter, deque
from copy import deepcopy

import pytest

from app.engine import maps, rules, serialize
from app.engine.board_geom import hex_corners, quant_key
from app.engine.legal import board_legal_moves
from app.engine.scenario import vertex_islands
from app.engine.state import COST
from app.engine.topology import land_components
from app.match_rulesets import (CURRENT_RULESET, LEGACY_S1_RULESET,
    LEGACY_S2B1_RULESET, OFFICIAL_S3A_RULESET, compatibility)
from app.persistence import snapshots
from tests.test_seafarers_maps import setup, fund


# Source columns left-to-right, top-to-bottom. Codes: F=fields,H=hills,
# P=pasture,W=forest,M=mountains,G=gold,D=desert,S=sea. No production deck.
COLUMNS = {
    3: [(3, "F6 W5 S H10"), (2, "F11 M3 H11 S M8"),
        (1, "H8 P10 P9 W8 S S"), (2, "P2 M5 W10 S G4"),
        (1, "S F4 P6 S F3 S"), (2, "S S S P4 M9"), (3, "H12 G5 S S")],
    4: [(3, "F8 W2 M10 S F6"), (2, "M3 P4 H9 P8 S H3"),
        (1, "H6 W10 D F11 W5 S S"), (2, "F12 H11 F3 P9 S G10"),
        (1, "S P5 W6 M4 S W9 S"), (2, "S S S S H5 M2"), (3, "M8 P11 S G4 S")],
}
TERRAINS = dict(F="fields", H="hills", P="pasture", W="forest", M="mountains", G="gold", D="desert", S="sea")
PORT_ANCHORS = {
    3: [(2,-3,5,0), (1,-3,4,5), (1,-3,2,3), (2,-1,4,5),
        (2,-1,0,1), (0,1,5,0), (-1,1,2,3), (-1,-1,1,2)],
    4: [(2,-3,4,5), (1,-3,3,4), (2,-2,5,0), (-1,-2,3,4),
        (-2,-1,2,3), (1,0,5,0), (-2,0,1,2), (0,1,0,1), (-1,1,1,2)],
}


def official(count=3, seed=17):
    return rules.build_game(seed, count, map_id=f"seafarers_official_new_shores_{count}")


@pytest.mark.parametrize("count,component_count,island_sizes", [(3,35,[2,2,4,14]), (4,42,[2,2,5,19])])
def test_exact_source_positions_tokens_islands_frame_and_ports(count, component_count, island_sizes):
    g = official(count)
    expected = []
    for c, (first_k, column) in enumerate(COLUMNS[count]):
        for row, code in enumerate(column.split()):
            k = first_k + 2 * row
            expected.append((3 - (k + c - 1)//2, c - 3,
                             TERRAINS[code[0]], int(code[1:]) if len(code)>1 else None))
    actual = [(t.q,t.r,t.terrain,t.number) for t in g.tiles]
    assert actual[:component_count] == expected
    assert actual[component_count:] == [(2,0,"sea",None), (-4 if count==3 else -5,0,"sea",None)]
    assert sorted(map(len, land_components(g.board).values())) == island_sizes
    assert len(land_components(g.board)[0]) == (14 if count==3 else 19)
    assert Counter(t.terrain for t in g.tiles[:component_count])["sea"] == (13 if count==3 else 14)
    assert sum(t.terrain == "gold" for t in g.tiles) == 2
    assert len(g.ports) == count + 5
    points = {quant_key(p):v for v,p in g.vertices.items()}
    expected_ports = set()
    for q,r,a,b in PORT_ANCHORS[count]:
        tile = next(t for t in g.tiles if (t.q,t.r)==(q,r))
        corners = hex_corners(tile.center,g.size)
        expected_ports.add(tuple(sorted((points[quant_key(corners[a])], points[quant_key(corners[b])]))))
    assert {edge for edge,_ in g.ports} == expected_ports
    assert Counter(kind for _,kind in g.ports) == Counter(["3:1"]*count + ["2:1:"+r for r in COST["settlement"]] + ["2:1:ore"])
    assert (g.tiles[g.robber_tile].terrain,g.tiles[g.robber_tile].number) == (("hills",12) if count==3 else ("desert",None))
    assert g.pirate_tile == component_count+1
    assert g.rules_config.target_vp == 14
    assert g.scenario.rules.starting_islands == (0,) and g.scenario.rules.new_island_vp == 2
    assert snapshots.decode_snapshot(snapshots.encode_snapshot(g)) == g


@pytest.mark.parametrize("count", [3,4])
def test_terrain_tokens_fixed_across_seeds_harbor_types_shuffle_only(count):
    games = [official(count,seed) for seed in range(6)]
    first = games[0]
    assert all(g.tiles==first.tiles and g.edges==first.edges for g in games)
    assert all([edge for edge,_ in g.ports]==[edge for edge,_ in first.ports] for g in games)
    assert len({tuple(kind for _,kind in g.ports) for g in games}) > 1


@pytest.mark.parametrize("count", [3,4])
def test_setup_only_main_island_and_printed_inner_frame_accepts_ship(count):
    g = official(count)
    legal = board_legal_moves(g,g.turn)["settlements"]
    assert legal and all(vertex_islands(g.board,v)=={0} for v in legal)
    # This coastline meets a partial sea-frame piece, not an added halo hex.
    edge = next(e for e,adj in sorted(g.edge_adj_hexes.items())
                if len(adj)==1 and adj[0] in land_components(g.board)[0]
                and any(v in legal for v in e))
    vid = next(v for v in edge if v in legal)
    rules.apply_cmd(g,g.turn,{"type":"place_settlement","vid":vid})
    assert edge in [tuple(e) for e in board_legal_moves(g,g.turn)["ships"]]
    rules.apply_cmd(g,g.turn,{"type":"build_ship","eid":edge})
    assert g.occupied_ships[edge]==0
    assert snapshots.decode_snapshot(snapshots.encode_snapshot(g)) == g
    # Disabling the explicit new-map frame opt-in restores the old edge policy.
    old = deepcopy(g)
    old.rules.pop("sea_frame")
    assert not rules._edge_has_sea(old,edge)


def next_island(g,pid,only_island=None):
    eligible = set(land_components(g.board)) - g.scenario.home_islands[pid] - g.scenario.awarded_islands.get(pid,set())
    if only_island is not None:
        eligible &= {only_island}
    starts = sorted(v for v,(owner,_) in g.occupied_v.items() if owner==pid)
    queue, seen = deque((v,[]) for v in starts), set(starts)
    while queue:
        v,path = queue.popleft()
        if path and vertex_islands(g.board,v) & eligible and rules.can_place_settlement(g,pid,v,False):
            return v,path
        for e in sorted(g.edges):
            if v not in e or not rules._edge_has_sea(g,e) or rules._edge_blocked_by_pirate(g,e):
                continue
            if e in g.occupied_e or g.occupied_ships.get(e,pid)!=pid:
                continue
            other = e[0] if e[1]==v else e[1]
            if other in seen or g.occupied_v.get(other,(pid,))[0]!=pid:
                continue
            seen.add(other)
            queue.append((other,path+[e]))
    raise AssertionError("No route to an unawarded smaller island")


def arrive(g,only_island=None):
    v,path = next_island(g,g.turn,only_island)
    for e in path:
        if e not in g.occupied_ships:
            fund(g,COST["ship"])
            rules.apply_cmd(g,g.turn,{"type":"build_ship","eid":e})
    fund(g,COST["settlement"])
    before = g.players[g.turn].vp
    rules.apply_cmd(g,g.turn,{"type":"place_settlement","vid":v})
    assert g.players[g.turn].vp == before + 3
    return v


@pytest.mark.parametrize("count", [3,4])
def test_funded_deterministic_paid_ship_replay_reaches_exact_fourteen(count):
    g = official(count)
    setup(g,0,prefer_ship=True)
    assert all(p.vp==2 for p in g.players) and not g.scenario.awarded_islands
    assert all(home=={0} for home in g.scenario.home_islands.values())
    rules.apply_cmd(g,0,{"type":"roll","roll":2})
    for v,(owner,_) in list(g.occupied_v.items()):
        if owner==0:
            fund(g,COST["city"])
            rules.apply_cmd(g,0,{"type":"upgrade_city","vid":v})
    for _ in range(2):
        v = arrive(g)
        ledger = deepcopy(g.scenario)
        fund(g,COST["city"])
        rules.apply_cmd(g,0,{"type":"upgrade_city","vid":v})
        assert g.scenario==ledger
        assert snapshots.decode_snapshot(snapshots.encode_snapshot(g))==g
    # Depending on setup geometry, the two shipping branches may not yet form
    # a continuous length-five route. Extend an actual legal branch to qualify.
    while not g.game_over:
        def route_length(edge):
            probe = deepcopy(g)
            probe.occupied_ships[tuple(edge)] = 0
            rules.update_longest_road(probe)
            return probe.longest_road_len
        fund(g,COST["ship"])
        ships = board_legal_moves(g,0)["ships"]
        assert ships, "replay must reach victory within the ordinary ship supply"
        edge = max(ships,key=route_length)
        rules.apply_cmd(g,0,{"type":"build_ship","eid":edge})
    assert g.players[0].vp==14 and g.game_over and g.winner_pid==0
    assert len(g.scenario.awarded_islands[0])==2
    assert serialize.to_player_dict(g,1)["players"][0]["vp"]==14


@pytest.mark.parametrize("count", [3,4])
def test_rejected_duplicate_settlement_is_atomic_and_city_cannot_farm_bonus(count):
    g = official(count)
    setup(g,0,prefer_ship=True)
    rules.apply_cmd(g,0,{"type":"roll","roll":2})
    v = arrive(g)
    before = snapshots.encode_snapshot(g)
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(g,0,{"type":"place_settlement","vid":v})
    assert snapshots.encode_snapshot(g)==before
    ledger = deepcopy(g.scenario)
    fund(g,COST["city"])
    rules.apply_cmd(g,0,{"type":"upgrade_city","vid":v})
    assert g.scenario==ledger


@pytest.mark.parametrize("count", [3,4])
def test_opponent_arrival_does_not_take_away_individual_island_bonus(count):
    g = official(count)
    setup(g,0,prefer_ship=True)
    rules.apply_cmd(g,0,{"type":"roll","roll":2})
    first = arrive(g)
    island = next(iter(vertex_islands(g.board,first)))
    rules.apply_cmd(g,0,{"type":"end_turn"})
    assert g.turn==1
    rules.apply_cmd(g,1,{"type":"roll","roll":2})
    arrive(g,island)
    assert g.scenario.awarded_islands[0]==g.scenario.awarded_islands[1]=={island}
    assert serialize.to_player_dict(g,2)["players"][0]["special_vp"]==2
    assert serialize.to_player_dict(g,2)["players"][1]["special_vp"]==2


@pytest.mark.parametrize("marker", [None,"unknown",LEGACY_S1_RULESET,LEGACY_S2B1_RULESET,CURRENT_RULESET])
def test_older_provenance_cannot_silently_execute_new_frame_rules(marker):
    g = official()
    assert compatibility(marker,g)["status"]=="compatibility_required"
    assert compatibility(OFFICIAL_S3A_RULESET,g)["status"]=="compatible"


@pytest.mark.parametrize("count", [3.0,True,None,4,"3"])
def test_official_marker_requires_exact_recorded_player_metadata(count):
    g = official()
    g.map_meta["required_players"] = count
    assert compatibility(OFFICIAL_S3A_RULESET,g)["status"]=="compatibility_required"


def test_official_marker_requires_consistent_recorded_map_identity():
    g = official()
    g.map_meta["id"] = "seafarers_official_new_shores_4"
    assert compatibility(OFFICIAL_S3A_RULESET,g)["status"]=="compatibility_required"


def test_original_four_custom_presets_and_base_do_not_acquire_official_rules():
    for preset in ("base_standard","seafarers_simple_1","seafarers_simple_2",
                   "seafarers_gold_haven","seafarers_pirate_lanes"):
        g=rules.build_game(17,2,map_id=preset)
        assert not g.rules.get("sea_frame") and g.scenario.rules.new_island_vp==0
        assert g.scenario.rules.starting_islands is None and g.rules_config.target_vp==10
        assert compatibility(CURRENT_RULESET,g)["status"]=="compatible"
