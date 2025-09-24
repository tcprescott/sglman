from models import AuditLog, User
import typing

async def write_audit_log(user: typing.Union[User, int], action: str, details: str = None):
	"""
	Write an audit log entry for the given user.
	user: User instance or user id
	action: Description of the action performed
	details: Optional details (string)
	"""
	if isinstance(user, int):
		user_obj = await User.get(id=user)
	else:
		user_obj = user
	await AuditLog.create(user=user_obj, action=action, details=details)
