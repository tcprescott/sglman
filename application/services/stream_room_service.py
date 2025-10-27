"""
Stream Room Service - Business Logic Layer

Handles stream room-related operations including creation, updates, and validation.
"""

from typing import Optional

from application.repositories import StreamRoomRepository
from models import StreamRoom


class StreamRoomService:
    """Service for stream room-related business operations."""
    
    def __init__(self):
        self.repository = StreamRoomRepository()
    
    async def create_stream_room(
        self,
        name: str,
        stream_url: Optional[str] = None,
        is_active: bool = True
    ) -> StreamRoom:
        """
        Create a new stream room with validation.
        
        Args:
            name: Stream room name (required)
            stream_url: URL to the stream
            is_active: Whether the stream room is active
            
        Returns:
            The created StreamRoom instance
            
        Raises:
            ValueError: If validation fails
        """
        # Validation
        if not name or not name.strip():
            raise ValueError("Room name is required")
        
        return await self.repository.create(
            name=name.strip(),
            stream_url=stream_url.strip() if stream_url else None,
            is_active=is_active
        )
    
    async def update_stream_room(
        self,
        stream_room: StreamRoom,
        name: Optional[str] = None,
        stream_url: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> StreamRoom:
        """
        Update an existing stream room with validation.
        
        Args:
            stream_room: StreamRoom instance to update
            name: New stream room name
            stream_url: New stream URL
            is_active: New active status
            
        Returns:
            The updated StreamRoom instance
            
        Raises:
            ValueError: If validation fails
        """
        # Validation
        if name is not None and (not name or not name.strip()):
            raise ValueError("Room name cannot be empty")
        
        # Build update dict with only provided values
        update_data = {}
        if name is not None:
            update_data['name'] = name.strip()
        if stream_url is not None:
            update_data['stream_url'] = stream_url.strip() if stream_url else None
        if is_active is not None:
            update_data['is_active'] = is_active
        
        return await self.repository.update(stream_room, **update_data)
    
    async def get_all_stream_rooms(self, active_only: bool = False) -> list[StreamRoom]:
        """
        Get all stream rooms.
        
        Args:
            active_only: If True, only return active stream rooms
            
        Returns:
            List of StreamRoom instances
        """
        if active_only:
            return await StreamRoom.filter(is_active=True)
        return await StreamRoom.all()
    
    async def get_stream_room_by_id(self, stream_room_id: int) -> Optional[StreamRoom]:
        """
        Get a stream room by ID.
        
        Args:
            stream_room_id: Stream room ID
            
        Returns:
            StreamRoom instance or None if not found
        """
        return await self.repository.get_by_id(stream_room_id)
