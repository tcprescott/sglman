# ADA accommodations

Members can ask a community for an ADA accommodation from their profile, and
that community's STAFF track each request with a status and private notes.
Behind `FeatureFlag.ADA_ACCOMMODATIONS` (ships dark).

## Key files

| File | Role |
|---|---|
| [`models/accommodation.py`](../../models/accommodation.py) | `AccommodationRequest` |
| [`models/enums.py`](../../models/enums.py) | `AccommodationStatus` |
| [`application/repositories/accommodation_repository.py`](../../application/repositories/accommodation_repository.py) | `AccommodationRepository` |
| [`application/services/accommodation_service.py`](../../application/services/accommodation_service.py) | `AccommodationService` — lifecycle rules, STAFF gate, audit |
| [`pages/home_tabs/accommodation_section.py`](../../pages/home_tabs/accommodation_section.py) | The profile card |
| [`pages/admin_tabs/admin_accommodations.py`](../../pages/admin_tabs/admin_accommodations.py) | The staff queue (a sub-tab of Admin → Users) |
| [`pages/admin_tabs/admin_users.py`](../../pages/admin_tabs/admin_users.py) | Sub-tabs, the "Needs ADA accommodation" filter, the ADA column |
| [`theme/accommodation_copy.py`](../../theme/accommodation_copy.py) | Status labels/chips and the privacy disclaimer, shared by both sides |

## Scope and visibility

- **Per community.** One `AccommodationRequest` per `(tenant, user)`. A person
  who belongs to two communities has two independent requests; neither
  community's staff can see the other's.
- **STAFF only** on the admin side (`AuthService.is_staff`, so super-admins
  too). The Users tab is already STAFF-only; the service checks again on every
  read and write.
- **The requester** sees their own checkbox, details and status, never the staff
  notes.
- **No free text leaves the app.** Audit rows carry `request_id`, `user_id`,
  `status` (and `previous_status` on a status change) only. Nothing is
  published on the event bus, so webhooks never see it, and there is no REST
  or MCP surface.
- Both surfaces show the same disclaimer (`privacy_disclaimer(community)`):
  only that community's staff can see the notes, but privacy can't be
  guaranteed, so don't write anything sensitive or personal; contact staff
  directly instead.

## Lifecycle

| From | Action | To |
|---|---|---|
| (none) | member ticks the box | `NEW` |
| `NEW` / `ACKNOWLEDGED` / `ARRANGED` | member unticks | `WITHDRAWN` (details cleared, staff notes kept) |
| `WITHDRAWN` | member ticks again | `NEW` (same row) |
| `ACKNOWLEDGED` / `ARRANGED` | member changes details | `NEW` |
| any open status | staff Update | `NEW` / `ACKNOWLEDGED` / `ARRANGED` |

Staff cannot withdraw on a member's behalf or move a withdrawn request back
out; they can still edit its notes. Re-saving identical details is a no-op.
Details are capped at 2000 characters, staff notes at 4000. Creating a
request requires community membership.

## Surfaces

- **Profile** (`/home/profile`): an "ADA accommodation" card. The checkbox
  saves at once; details save on blur and after a pause in typing. Shows the
  staff status chip while the request is open.
- **Admin → Users**: with the flag live the tab gains **Members** and **ADA
  requests (n)** sub-tabs, where *n* counts open requests. The member table
  gains an ADA column (an icon for open requests) and a "Needs ADA
  accommodation" filter. The ADA requests sub-tab lists open requests oldest
  first, with "Show withdrawn", CSV export and an Update dialog for status and
  staff notes.

No notifications are sent: staff watch the sub-tab count.
