"""
Audit Service - Business Logic Layer

Handles audit logging for tracking user actions and system events.
"""

from typing import Optional, Union

from models import AuditLog, User


class AuditService:
    """Service for audit logging operations."""
    
    async def write_log(
        self,
        user: Union[User, int],
        action: str,
        details: Optional[str] = None
    ) -> AuditLog:
        """
        Write an audit log entry for the given user.
        
        Args:
            user: User instance or user ID
            action: Description of the action performed
            details: Optional additional details about the action
            
        Returns:
            The created AuditLog instance
        """
        if isinstance(user, int):
            user_obj = await User.get(id=user)
        else:
            user_obj = user
        
        return await AuditLog.create(
            user=user_obj,
            action=action,
            details=details
        )
    
    async def get_logs_for_user(
        self,
        user: Union[User, int],
        limit: Optional[int] = None
    ) -> list[AuditLog]:
        """
        Get audit logs for a specific user.
        
        Args:
            user: User instance or user ID
            limit: Optional limit on number of logs to return
            
        Returns:
            List of AuditLog instances
        """
        if isinstance(user, int):
            query = AuditLog.filter(user_id=user)
        else:
            query = AuditLog.filter(user=user)
        
        query = query.order_by('-created_at')
        
        if limit:
            query = query.limit(limit)
        
        return await query
    
    async def get_recent_logs(self, limit: int = 100) -> list[AuditLog]:
        """
        Get recent audit logs across all users.
        
        Args:
            limit: Maximum number of logs to return (default 100)
            
        Returns:
            List of AuditLog instances
        """
        return await AuditLog.all().order_by('-created_at').limit(limit).prefetch_related('user')
