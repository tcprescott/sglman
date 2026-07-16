"""
StreamRoom Repository - Data Access Layer

Handles database operations for stream rooms.
"""

from typing import List, Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id, scoped
from models import StreamRoom


class StreamRoomRepository(TenantScopedRepository[StreamRoom]):
    """Repository for stream room data access."""

    model = StreamRoom

    @staticmethod
    async def get_all() -> List[StreamRoom]:
        """
        Get all stream rooms.
        
        Returns:
            List of StreamRoom objects
        """
        return await scoped(StreamRoom.all()).order_by('name')
    
    @staticmethod
    async def get_all_as_dict() -> dict[int, str]:
        """
        Get all stream rooms as a dict mapping ID to name.
        Useful for dropdown/select options.
        
        Returns:
            Dict mapping stream room ID to name
        """
        stream_rooms = await scoped(StreamRoom.all())
        return {sr.id: sr.name for sr in stream_rooms}
    
    @staticmethod
    async def create(
        name: str,
        stream_url: Optional[str] = None,
        is_active: bool = True
    ) -> StreamRoom:
        """
        Create a new stream room.
        
        Args:
            name: Stream room name
            stream_url: Optional stream URL
            is_active: Whether the room is active (default: True)
            
        Returns:
            Created StreamRoom object
        """
        return await StreamRoom.create(
            tenant_id=current_tenant_id(),
            name=name,
            stream_url=stream_url,
            is_active=is_active
        )
    
    @staticmethod
    async def count_matches(stream_room: StreamRoom) -> int:
        """Return how many matches reference this stream room."""
        return await stream_room.matches.all().count()
