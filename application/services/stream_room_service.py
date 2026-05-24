"""
Stream Room Service - Business Logic Layer

Handles stream room-related operations including creation, updates, and validation.
"""

from typing import Optional

from application.repositories import StreamRoomRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import StreamRoom, User


class StreamRoomService:
    """Service for stream room-related business operations."""

    def __init__(self):
        self.repository = StreamRoomRepository()
        self.audit_service = AuditService()

    async def create_stream_room(
        self,
        name: str,
        stream_url: Optional[str] = None,
        is_active: bool = True,
        actor: Optional[User] = None,
    ) -> StreamRoom:
        await AuthService.ensure(
            await AuthService.can_manage_stream_rooms(actor),
            "User cannot manage stream rooms",
        )

        if not name or not name.strip():
            raise ValueError("Room name is required")

        room = await self.repository.create(
            name=name.strip(),
            stream_url=stream_url.strip() if stream_url else None,
            is_active=is_active,
        )

        await self.audit_service.write_log(
            actor,
            AuditActions.STREAM_ROOM_CREATED,
            {'stream_room_id': room.id, 'name': room.name},
        )

        return room

    async def update_stream_room(
        self,
        stream_room: StreamRoom,
        name: Optional[str] = None,
        stream_url: Optional[str] = None,
        is_active: Optional[bool] = None,
        actor: Optional[User] = None,
    ) -> StreamRoom:
        await AuthService.ensure(
            await AuthService.can_manage_stream_rooms(actor),
            "User cannot manage stream rooms",
        )

        if name is not None and (not name or not name.strip()):
            raise ValueError("Room name cannot be empty")

        update_data = {}
        if name is not None:
            update_data['name'] = name.strip()
        if stream_url is not None:
            update_data['stream_url'] = stream_url.strip() if stream_url else None
        if is_active is not None:
            update_data['is_active'] = is_active

        result = await self.repository.update(stream_room, **update_data)

        await self.audit_service.write_log(
            actor,
            AuditActions.STREAM_ROOM_UPDATED,
            {'stream_room_id': stream_room.id, 'changed_fields': list(update_data.keys())},
        )

        return result

    async def delete_stream_room(self, stream_room: StreamRoom, actor: Optional[User] = None) -> None:
        await AuthService.ensure(
            await AuthService.can_manage_stream_rooms(actor),
            "User cannot manage stream rooms",
        )
        room_id = stream_room.id
        await stream_room.delete()
        await self.audit_service.write_log(
            actor,
            AuditActions.STREAM_ROOM_DELETED,
            {'stream_room_id': room_id},
        )

    async def get_all_stream_rooms(self, active_only: bool = False) -> list[StreamRoom]:
        if active_only:
            return await StreamRoom.filter(is_active=True)
        return await StreamRoom.all()

    async def get_stream_room_by_id(self, stream_room_id: int) -> Optional[StreamRoom]:
        return await self.repository.get_by_id(stream_room_id)
