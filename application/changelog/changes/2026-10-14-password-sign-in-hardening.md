### Security

- Password sign-in now counts every try before checking it, so firing many tries at once no longer gets around the limit.
- On a community's own domain, the password sign-in page sends you to the main site's sign-in page for that community, so the domain's operator never sees the password.
- Platform admins sign in with Discord only. Their accounts can't be given a password.
- Each password sign-in is recorded in the audit log.
