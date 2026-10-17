"""In-process access to ONE native Fog fixture, never a client credential.

Normal startup installs no capabilities. Only guarded test launchers use this
integration seam; neither snapshot decoding nor a known marker grants access.
"""
from dataclasses import dataclass
from uuid import UUID

from app.engine.exploration import has_fog
from app.match_rulesets import CURRENT_RULESET


@dataclass(frozen=True)
class FogMatchAccess:
    room_id: UUID
    match_uuid: UUID

    def permits(self, room) -> bool:
        return bool(room is not None and type(self.room_id) is UUID and type(self.match_uuid) is UUID
                    and room.id == self.room_id and room.match_uuid == self.match_uuid
                    and room.status == "in_match" and not room.test_mode
                    and room.ruleset_id == CURRENT_RULESET and has_fog(room.game)
                    and not room.game.rules.get("sea_frame"))
