"""A generator correction never rewrites an existing PostgreSQL board head."""
import asyncio
from pathlib import Path

from app import server_mp as server
from app.engine import maps, rules
from app.persistence.coordinator import Coordinator
from app.persistence.recovery import clone_room
from app.persistence.snapshots import loads_snapshot
from tests.test_auth import connection
from tests.test_base_number_placement import red_edges
from tests.test_persistence_postgres import database_url, runtime, pair, command


def test_legacy_base_board_recovery_receipts_and_new_match(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await pair(names=("Alice", "Bob", "Carol", "Dave"))
            proof = clients[0].ws.latest("reconnect_token")["reconnect_token"]
            old = loads_snapshot(Path(__file__).with_name("fixtures").joinpath(
                "base_standard_seed17_legacy_v4.json").read_text())
            candidate = clone_room(room)
            candidate.game, candidate.seed = old, old.seed
            for player, slot in zip(old.players, candidate.players):
                player.name = slot.name
            candidate.selected_map_data = maps.get_preset_map("base_standard")
            candidate.selected_map_data.pop("number_placement")
            await server._commit(room, candidate, snapshot=True)
            request = command(room, clients[0], {"type": "noop"})
            await server._dispatch(clients[0], request)
            before = await coord.repository.load(room.id)

            def forbidden(*args, **kwargs):
                raise AssertionError("recovery must never regenerate or repair a historical board")

            with monkeypatch.context() as guard:
                guard.setattr(rules, "build_game", forbidden)
                guard.setattr(rules, "apply_cmd", forbidden)
                guard.setattr(maps, "build_board_from_map", forbidden)
                server.manager = server.RoomManager()
                await Coordinator(coord.database).initialize(server.manager)
            restored = server.manager.rooms[room.room_code]
            assert restored.game == old and red_edges(restored.game) == [((21, 31), [9, 10])]
            client = await connection()
            await server._dispatch(client, {"type": "reconnect", "room_code": room.room_code,
                                            "reconnect_token": proof})
            assert client.pid == 0
            await server._dispatch(client, request)  # Durable retry, not re-execution.
            assert client.ws.latest("cmd_ack")["cmd_id"] == request["cmd_id"]
            after = await coord.repository.load(room.id)
            assert after["head"] == before["head"] and after["receipts"] == before["receipts"]
            new_room, _ = await pair(names=("New A", "New B", "New C", "New D"))
            assert maps.get_preset_map(new_room.selected_map_id)["number_placement"] == maps.BASE_NUMBER_PLACEMENT
            assert not red_edges(new_room.game)
            assert (await coord.repository.load(restored.id))["head"] == before["head"]
    asyncio.run(run())
