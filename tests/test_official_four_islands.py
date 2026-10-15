"""Independent transcription of printed 2021 pp.11-13; funded engine fixtures.

These component/rule tests are separate from the grant-free TCP full match.
"""
from collections import Counter
from copy import deepcopy
import heapq
from random import Random

import pytest

from app.engine import maps, rules, serialize
from app.engine.board_geom import hex_corners, quant_key
from app.engine.legal import board_legal_moves
from app.engine.scenario import vertex_islands
from app.engine.state import COST
from app.engine.topology import land_components, coastal_edges
from app.match_rulesets import (CURRENT_RULESET, LEGACY_S1_RULESET, LEGACY_S2B1_RULESET,
    OFFICIAL_S3A_RULESET, OFFICIAL_S3B_RULESET, compatibility)
from app.persistence.snapshots import encode_snapshot, decode_snapshot
from tests.test_seafarers_maps import fund


# Source columns, left to right, top to bottom. Full cardboard-frame sea spaces
# are separate from the printed loose-hex inventory of 35 in both variants.
COLUMNS = {
    3: [(3, "P12 S S S"), (2, "W5 P9 S M2 F5"), (1, "F11 M8 W3 S H10 H6"),
        (2, "S S S S S"), (1, "P6 M10 S W8 H11 S"), (2, "M4 W9 S F9 H5"), (3, "S S F4 P3")],
    4: [(3, "P10 F11 S F4"), (2, "F6 M4 H2 S M8"), (1, "H4 P9 S S W9 P11"),
        (2, "S S W6 S S"), (1, "F5 W3 S H5 M10 S"), (2, "H10 S M3 F12 P5"), (3, "P8 S W9 W11")],
}
TERRAIN = dict(P="pasture", W="forest", M="mountains", H="hills", F="fields", S="sea")
PORT_ANCHORS = {
    3: [(2,-1,4,5), (1,1,0,1), (-1,2,3,4), (-4,2,1,2), (-3,1,4,5),
        (-3,-1,3,4), (-1,-2,0,1), (1,-2,3,4), (2,-1,1,2)],
    4: [(2,-3,5,0), (2,-1,4,5), (0,2,5,0), (1,1,3,4), (-1,0,0,1),
        (-4,2,3,4), (-3,-1,0,1), (-3,-1,3,4), (1,-2,1,2)],
}


def official(players=3, seed=17):
    return rules.build_game(seed, players, map_id=f"seafarers_official_four_islands_{players}")


def finish_setup(game, homes=1):
    """P0 chooses one/two actual home islands; opponents use other coasts."""
    fixture_rng = Random(0)
    while game.phase == "setup":
        rules.apply_cmd(game,game.turn,setup_choice(game,fixture_rng,homes))
    assert len(game.scenario.home_islands[0]) == homes


def setup_choice(game, fixture_rng, homes=1):
    """A deterministic legal opening, shared with durable dispatch tests."""
    roots = sorted(land_components(game.board))
    pid = game.turn
    legal = board_legal_moves(game, pid)
    if game.setup_need == "settlement":
        candidates = legal["settlements"]
        if pid == 0:
            target = roots[0] if homes == 1 or not game.scenario.home_islands[0] else roots[1]
            candidates = [v for v in candidates if vertex_islands(game.board, v) == {target}]
        else:
            preferred = [v for v in candidates if vertex_islands(game.board, v).intersection(roots[2:])]
            candidates = preferred or candidates
        assert candidates
        coastal = [v for v in candidates if any(rules._edge_has_sea(game, e) and not rules._edge_blocked_by_pirate(game, e)
                                               for e in game.edges if v in e)]
        return {"type":"place_settlement","vid":fixture_rng.choice(coastal or candidates)}
    ships = legal["ships"]
    return {"type":"build_ship" if ships else "place_road","eid":fixture_rng.choice(ships or legal["roads"])}


def next_island(game, pid, island=None):
    """Minimize NEW paid ships, reusing existing shipping branches at zero cost."""
    eligible = set(land_components(game.board)) - game.scenario.home_islands[pid] - game.scenario.awarded_islands.get(pid, set())
    if island is not None:
        eligible &= {island}
    queue = [(0, v, []) for v, (owner, _) in game.occupied_v.items() if owner == pid]
    heapq.heapify(queue)
    visited = set()
    while queue:
        cost, vertex, path = heapq.heappop(queue)
        if vertex in visited:
            continue
        visited.add(vertex)
        if path and vertex_islands(game.board, vertex) & eligible and rules.can_place_settlement(game, pid, vertex, False):
            return vertex, path
        for edge in sorted(game.edges):
            if vertex not in edge or not rules._edge_has_sea(game, edge) or rules._edge_blocked_by_pirate(game, edge):
                continue
            if edge in game.occupied_e or game.occupied_ships.get(edge, pid) != pid:
                continue
            other = edge[0] if edge[1] == vertex else edge[1]
            if game.occupied_v.get(other, (pid,))[0] == pid:
                heapq.heappush(queue, (cost + (edge not in game.occupied_ships), other, path + [edge]))
    raise AssertionError("No legal shipping route to an unawarded foreign island")


def arrive(game, island=None):
    vertex, path = next_island(game, game.turn, island)
    for edge in path:
        if edge not in game.occupied_ships:
            fund(game, COST["ship"])
            rules.apply_cmd(game, game.turn, {"type": "build_ship", "eid": edge})
    fund(game, COST["settlement"])
    before = game.players[game.turn].vp
    rules.apply_cmd(game, game.turn, {"type": "place_settlement", "vid": vertex})
    assert game.players[game.turn].vp == before + 3
    return vertex


@pytest.mark.parametrize("players,islands", [(3,{0:6,7:4,20:4,23:6}), (4,{0:7,3:4,17:8,20:4})])
def test_exact_printed_layout_inventory_tokens_ports_and_initial_figures(players, islands):
    game = official(players)
    expected = []
    for column, (first, codes) in enumerate(COLUMNS[players]):
        for row, code in enumerate(codes.split()):
            expected.append((3 - (first + row*2 + column - 1)//2, column-3,
                             TERRAIN[code[0]], int(code[1:]) if len(code)>1 else None))
    assert [(t.q,t.r,t.terrain,t.number) for t in game.tiles] == expected + [(2,0,"sea",None),(-4,0,"sea",None)]
    assert {root:len(tiles) for root,tiles in land_components(game.board).items()} == islands
    assert Counter(t.terrain for t in game.tiles[:35]) == Counter({
        "sea":15 if players==3 else 12, "fields":4 if players==3 else 5,
        "forest":4 if players==3 else 5, "pasture":4 if players==3 else 5, "hills":4, "mountains":4})
    assert Counter(t.number for t in game.tiles if t.number) == Counter({
        2:1,3:2,4:2 if players==3 else 3,5:3,6:2,8:2,9:3,
        10:2 if players==3 else 3,11:2 if players==3 else 3,12:1})
    points = {quant_key(point):vid for vid,point in game.vertices.items()}
    ports = set()
    for q,r,a,b in PORT_ANCHORS[players]:
        tile = next(t for t in game.tiles if (t.q,t.r)==(q,r))
        corners = hex_corners(tile.center,game.size)
        ports.add(tuple(sorted((points[quant_key(corners[a])],points[quant_key(corners[b])]))))
    assert {edge for edge,_ in game.ports} == ports <= set(coastal_edges(game.board))
    assert len({v for edge,_ in game.ports for v in edge}) == 18
    assert Counter(kind for _,kind in game.ports) == Counter(["3:1"]*4+["2:1:"+r for r in ("wood","brick","sheep","wheat","ore")])
    assert game.robber_tile == (0 if players==3 else 29)
    assert game.tiles[game.robber_tile].number == 12
    assert game.pirate_tile == (17 if players==3 else 36) and game.tiles[game.pirate_tile].terrain=="sea"
    assert game.rules_config.target_vp==13 and not game.rules_config.enable_gold
    assert game.scenario.rules.starting_islands is None and game.scenario.rules.new_island_vp==2
    assert (encode_snapshot(game)["snapshot_version"],encode_snapshot(game)["engine_compatibility"]) == (4,3)
    assert decode_snapshot(encode_snapshot(game))==game


@pytest.mark.parametrize("players", [3,4])
def test_fixed_diagram_and_harbor_positions_with_only_types_randomized(players):
    games = [official(players,seed) for seed in range(5)]
    assert all(g.tiles==games[0].tiles and g.edges==games[0].edges for g in games)
    assert all([e for e,_ in g.ports]==[e for e,_ in games[0].ports] for g in games)
    assert len({tuple(kind for _,kind in g.ports) for g in games})>1


@pytest.mark.parametrize("players", [3,4])
@pytest.mark.parametrize("homes", [1,2])
def test_setup_choice_records_only_real_home_islands_without_bonus(players, homes):
    game=official(players)
    roots=set(land_components(game.board))
    legal=board_legal_moves(game,0)["settlements"]
    assert set.union(*(vertex_islands(game.board,v) for v in legal))==roots
    finish_setup(game,homes)
    assert all(p.vp==2 for p in game.players) and not game.scenario.awarded_islands
    assert len(game.scenario.home_islands[0])==homes
    assert decode_snapshot(encode_snapshot(game))==game


@pytest.mark.parametrize("players", [3,4])
@pytest.mark.parametrize("homes", [1,2])
def test_funded_exploration_awards_exactly_six_or_four_special_vp_and_wins_at_thirteen(players, homes):
    game=official(players)
    finish_setup(game,homes)
    rules.apply_cmd(game,0,{"type":"roll","roll":2})
    for _ in range(4-homes):
        assert not game.game_over and game.players[0].vp<13
        arrive(game)
        assert decode_snapshot(encode_snapshot(game))==game
    assert len(game.scenario.awarded_islands[0])==4-homes
    assert serialize.to_player_dict(game,1)["players"][0]["special_vp"]==2*(4-homes)
    # Distinct shipping branches need not already form one length-five route.
    # Qualify through paid legal extensions before the last city upgrades.
    while not game.game_over and game.longest_road_owner!=0:
        fund(game,COST["ship"])
        def route_length(edge):
            probe=deepcopy(game)
            rules.apply_cmd(probe,0,{"type":"build_ship","eid":edge})
            return probe.longest_road_len
        ships=board_legal_moves(game,0)["ships"]
        assert ships, "fixture must qualify within the normal fifteen-ship supply"
        rules.apply_cmd(game,0,{"type":"build_ship","eid":max(ships,key=route_length)})
    # Reach the remaining ordinary points through actual paid upgrades/routes.
    for vertex,(owner,level) in list(game.occupied_v.items()):
        if game.game_over: break
        if owner==0 and level==1 and sum(p==0 and l==2 for p,l in game.occupied_v.values())<4:
            assert game.players[0].vp<13
            fund(game,COST["city"])
            rules.apply_cmd(game,0,{"type":"upgrade_city","vid":vertex})
    assert game.game_over and game.winner_pid==0 and game.players[0].vp==13


@pytest.mark.parametrize("players", [3,4])
def test_city_duplicate_rejection_and_opponents_home_do_not_remove_personal_bonus(players):
    game=official(players)
    finish_setup(game,1)
    rules.apply_cmd(game,0,{"type":"roll","roll":2})
    opponent_home=min(set.union(*(islands for pid,islands in game.scenario.home_islands.items() if pid!=0)) - game.scenario.home_islands[0])
    vertex=arrive(game,opponent_home)
    foreign,=vertex_islands(game.board,vertex)
    assert any(foreign in islands for pid,islands in game.scenario.home_islands.items() if pid!=0)
    ledger=deepcopy(game.scenario)
    before=encode_snapshot(game)
    with pytest.raises(rules.RuleError): rules.apply_cmd(game,0,{"type":"place_settlement","vid":vertex})
    assert encode_snapshot(game)==before
    fund(game,COST["city"])
    rules.apply_cmd(game,0,{"type":"upgrade_city","vid":vertex})
    assert game.scenario==ledger
    assert serialize.to_player_dict(game,1)["players"][0]["special_vp"]==2


@pytest.mark.parametrize("players", [3,4])
def test_actual_setup_ship_movement_remains_free_and_once_per_turn(players):
    game=official(players)
    finish_setup(game)
    rules.apply_cmd(game,0,{"type":"roll","roll":2})
    # A setup can form a closed shipping line: add a genuinely paid open end,
    # verify that its age restriction survives the codec, then age it legally.
    fund(game,COST["ship"])
    edge=board_legal_moves(game,0)["ships"][0]
    rules.apply_cmd(game,0,{"type":"build_ship","eid":edge})
    game=decode_snapshot(encode_snapshot(game))
    before=encode_snapshot(game)
    with pytest.raises(rules.RuleError,match="built this turn"):
        rules.apply_cmd(game,0,{"type":"move_ship","from_eid":edge,"to_eid":edge})
    assert encode_snapshot(game)==before
    rules.apply_cmd(game,0,{"type":"end_turn"})
    while game.turn!=0:
        rules.apply_cmd(game,game.turn,{"type":"roll","roll":2})
        rules.apply_cmd(game,game.turn,{"type":"end_turn"})
    rules.apply_cmd(game,0,{"type":"roll","roll":2})
    # Obtain a valid source/destination by probing the unchanged executor.
    moved=False
    for source,owner in list(game.occupied_ships.items()):
        if owner!=0: continue
        for target in sorted(game.edges):
            if target==source: continue
            probe=deepcopy(game)
            try: rules.apply_cmd(probe,0,{"type":"move_ship","from_eid":source,"to_eid":target})
            except rules.RuleError: continue
            hand=deepcopy(game.players[0].res)
            rules.apply_cmd(game,0,{"type":"move_ship","from_eid":source,"to_eid":target})
            assert game.players[0].res==hand and source not in game.occupied_ships
            before=encode_snapshot(game)
            with pytest.raises(rules.RuleError,match="already moved"):
                rules.apply_cmd(game,0,{"type":"move_ship","from_eid":target,"to_eid":source})
            assert encode_snapshot(game)==before
            moved=True
            break
        if moved: break
    assert moved


@pytest.mark.parametrize("marker", [None,"unknown",CURRENT_RULESET,LEGACY_S1_RULESET,LEGACY_S2B1_RULESET,OFFICIAL_S3A_RULESET])
def test_other_rulesets_cannot_silently_claim_four_islands(marker):
    game=official()
    assert compatibility(marker,game)["status"]=="compatibility_required"
    assert compatibility(OFFICIAL_S3B_RULESET,game)["status"]=="compatible"


def test_new_marker_cannot_reclassify_new_shores_or_base():
    for preset,players in [("base_standard",2),("seafarers_official_new_shores_3",3)]:
        game=rules.build_game(17,players,map_id=preset)
        assert compatibility(OFFICIAL_S3B_RULESET,game)["status"]=="compatibility_required"
