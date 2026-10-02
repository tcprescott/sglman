# Membership and ADA accommodations UX — evaluation

**Scope:** the flows shipped in PRs #250–#253 (`840531f`..`3fc3de3`):

1. the membership gate's join door, join requests, staff approving and declining
   them on Admin → Users, and the **Take join requests** switch on Admin → Settings;
2. Discord auto-join (a linked-server member walks straight in) and account
   provisioning for server members holding a mapped role;
3. ADA accommodation requests: the member's profile card, the staff queue
   (Admin → Users → ADA requests), and the accessibility icon on the admin
   Schedule and Proctor Station boards;
4. the Users-tab filters on phones.

**Method:** built the capability matrix from `TenantMembershipService`,
`AccommodationService` and `AuthService` against every control the surfaces
offer, grepped every public method in both services for a caller (all wired),
then drove the running app (MOCK_DISCORD, seeded `default` / `second` /
`fledgling`) with Playwright at 1440×900 and 390×844, using two browser
contexts for each two-sided transition and bracketing `/tmp/app.log` around
each click. Fresh accounts were minted from the mock login for every requester
(`aud_join_*`, `aud_auto_*`, `aud_addm_*`), so seeded fixtures were read, not
changed. Screenshots, CSVs and the scripts are in
`/tmp/claude-0/-home-user-sglman/21037563-847e-55a4-bd9a-303508d481a4/scratchpad/membership/`
(`sN-*.png`, `sN_*.js`; below, `scratch/`). Claims tagged `code-read` were not
driven.

**Headline:** the ADA feature's privacy rule is "no free text leaves the app",
and the Export CSV button on both boards that show the ADA icon writes every
arranged player's staff notes into the file, next to their Discord id. The
membership half works on the happy path, but every decision a staff member
makes on the Users tab ends in an unhandled exception, and the request queue
doesn't know about any way into the community other than itself.

---

## Capability matrix

| Capability | Service gate | Surface | Mismatch |
|---|---|---|---|
| Ask to join | non-member, `join_requests_enabled` | Join door form | none — a stale door is refused by the service (`code-read`, `tenant_membership_service.py:136`) |
| Approve / decline | `can_grant_roles` (STAFF, super-admin) | Users → join queue | the queue also lists people already admitted another way (F3) |
| Add / remove member | `can_grant_roles` | Users: Add Member, row Remove | Remove has no confirm and tells nobody (F6) |
| Auto-join | switch + linked guild + guild member | the gate itself | silent on both sides (F7) |
| Provision mapped-role holders | `can_grant_roles` | Discord Roles → Sync All Users | count-only toast (F11, `code-read`) |
| Request ADA accommodation | member, flag on | Profile card | — |
| Review ADA requests | `is_staff` | Users → ADA requests | the list includes non-members (F6) |
| See arranged notes | `is_staff` or PROCTOR | ADA icon on Schedule, Proctor Station | PROCTOR is outside what both disclaimers promise (F4); CSV export carries them (F1) |

Icon visibility, measured on `/t/default` at both widths:

| Viewer | Board | Icons | Should see? |
|---|---|---:|---|
| `staff_user` | admin Schedule | 14 | yes |
| `staff_user` | Proctor Station | 11 | yes |
| `proctor_only` | Proctor Station | 11 | yes |
| `player_four` (TA) | admin Schedule | 0 | no |
| `sm_only` | admin Schedule | 0 | no |
| `cc_user` | admin Schedule | 0 | no |

The per-viewer gate holds. What leaks is the export, not the render.

---

## Findings

### F1 — Critical: Export CSV on the Schedule and Proctor Station boards writes staff ADA notes and Discord ids into the file

**Fixed in #254.** `_stringify` now exports a structured cell as its display name only; the proctor export re-driven after the fix reads `Player One; Player Two` with no note or id on any line.

**Route/role/viewport:** `/t/default/volunteer/proctor-station` as `proctor_only`,
and `/t/default/admin/schedule` as `staff_user`, at 1440.
**Evidence:** `scratch/s10-proctor_only-proctor-station.csv`,
`scratch/s10-staff_user-schedule.csv`. The Players column is the Python `repr`
of the row's player list:

```
2026-10-02 08:07,Scheduled,"[{'name': 'Player One', 'user_id': 5, ..., 'discord_id': '100000000022537938'},
 {'name': 'Player Two', 'user_id': 6, ..., 'discord_id': '100000000027392325', 'ada': True,
  'ada_note': 'Venue confirmed a chair for station 3.'}]",,Wizzrobe Cup,18
```

13 of 35 lines in the proctor export and 18 of 43 in the staff one carry an
`ada_note`. Every line carries Discord ids.

**Cause:** `_apply_accommodations` (`theme/tables/match.py:503-521`) writes
`ada`/`ada_note` onto the same player dicts the export reads (`match.py:240-244`
passes `self.table.rows`), and `_stringify` (`application/utils/csv_export.py:72`)
renders a list as `str(value)`. The repr-in-a-cell problem predates this work.
The ADA icon is what turned it into a disclosure. `docs/features/ada-accommodations.md`
says "No free text leaves the app", and the commit made the notes reach a file
any PROCTOR can save and forward.

**Fix shape:** the export needs a formatter for the players column (names
only), and ADA data shouldn't sit on a row field the export can reach. Keep it
in a side map keyed by user id, or strip it in the export callback.

### F2 — High: every Approve or Decline click ends in an unhandled exception, and the member table doesn't pick up the new member

**Route/role/viewport:** `/t/default/admin/users` as `staff_user`, both widths, 5 of 5 decisions.
**Evidence:** after each click the log shows

```
File "pages/admin_tabs/admin_users.py", line 103, in decide
    await table_view.refresh()
File "pages/admin_tabs/admin_users.py", line 165, in get_query
    tid = require_tenant_id()
RuntimeError: No tenant in context.
...
ERROR wizzrobe.ui: Unhandled exception in a UI event handler
```

The decision commits, the DM goes out and the toast reads "Approved." But the
approved person is missing from the member table (`scratch/s1-desk-approve-04-staff-after.png`:
`aud_join_desk_approve_*` should sort above `cc_user` and doesn't) until staff
press Refresh. `decide` (`admin_users.py:92-103`) calls `join_queue.refresh()`
first. That deletes the button whose handler is running, and the table refresh
that follows has lost the tenant. The other handlers on this page go through
`table_view._bg(...)` (`admin_users.py:325`, `theme/tables/user.py:41`) for
exactly this reason. This one doesn't.

### F3 — High: the join queue only closes requests it decided itself, so a person let in another way is told they weren't approved

**Route/role:** `/t/default/admin/users` as `staff_user`, a fresh requester `aud_addm_79401`, 1440.
**Evidence:** the requester files a request. Staff use **Add Member** on them.
The log shows no DM. The queue still lists them after the add and after a
reload (`scratch/s9-desk-01-after-add-member.png`, `s9-desk-02-after-reload.png`).
Pressing Decline on that stale row then sends someone who is already a member

```
[MOCK Discord DM] -> 90281286683555740: Your request to join **Default** wasn't approved this time.
```

and they stay a member. That's three problems with one cause:

- **Add Member** (`tenant_membership_service.py:69-83`) and the role-grant path
  (`TenantMembershipService.ensure_member`, called from `user_service.py:371,457`
  and the Discord role sync at `discord_role_mapping_service.py:369,445`) never
  close a pending request. Only `join_via_discord` does (`:203-208`).
- The door promises "You will get a message either way" (`theme/join_page.py:307`).
  Someone admitted by Add Member, a role grant or auto-join gets no message at
  all. For auto-join this is `code-read`: it closes the request as approved with
  no decider and sends nothing.
- `_decidable` (`:319-332`) doesn't check whether the requester is already a
  member, so a decline goes ahead and DMs them.

### F4 — High: both privacy disclaimers say only staff can read the notes, and every PROCTOR can read them

**Route/role:** staff Update dialog on Users → ADA requests; the icon popup as `proctor_only`, both widths.
**Evidence:** the staff panel shows "Only Default staff can see these notes…"
(`privacy_disclaimer`, `theme/accommodation_copy.py:316-323`, rendered at
`admin_accommodations.py:83`). The dialog adds "The member never sees staff
notes." (`:107`), and the intro calls them "notes only staff can see" (`:66`).
As `proctor_only`, tapping the icon on Player Two opens "ADA accommodation:
Player Two / Staff notes / Venue confirmed a chair for station 3."
(`scratch/s6-phone-proctor_only-proctor-station-popup.png`). The staff member
writing the note is told one audience and the note reaches a wider one: every
PROCTOR in the community, plus anyone they forward the F1 CSV to. The feature
doc names the PROCTOR exception in a sentence, but the UI copy never does.

**Fix shape:** the staff-notes field should say who reads it ("Staff and
proctors see these notes on the match boards").

### F5 — High: any edit by the member after a request is Arranged drops it to New and takes the icon off every board, and nobody is told

**Route/role/viewport:** `/t/default/home/profile` as a fresh member, then the staff queue, both widths.
**Evidence:** staff set `aud_join_desk_approve_22732`'s request to Arranged with
notes. The member reloads and sees "Staff status: ARRANGED". They type " Thanks!"
at the end of their details. 1.2 s later the autosave fires, the DB row reads
`new`, and one more audit row lands. In the staff queue the row now reads NEW
with the old staff notes still attached (`scratch/s5-phone-03-staff-queue.png`,
"Audit desk approve"). Nothing marks it as previously arranged or shows what
changed.

`set_my_request` resets on any change to the details
(`accommodation_service.py:100-104`), and `arranged_notes_for` returns only
`ARRANGED` rows (`:145`), so the icon disappears from the admin Schedule and
Proctor Station at the same moment. That last step is `code-read`: my fresh
member isn't in a match, so I didn't mutate seeded `player_two` to watch it go.
A typo fixed on the morning of the event removes the accommodation from the
proctor's view, and no DM, event or badge reaches staff. The ADA doc's "staff
watch the sub-tab count" doesn't catch it either, because the count (F8)
doesn't change.

### F6 — Medium: removing a member is one unconfirmed click that tells nobody, and their ADA request stays in the queue

**Route/role:** `/t/default/admin/users` as `staff_user` at 1440, the removed member at 390.
**Evidence:** clicking **Remove** on `aud_join_phone_approve_36027`'s row
removes them at once: 0 confirm dialogs, no DM in the log
(`scratch/s8-desk-01-after-remove.png`). This is the reverse of Approve, which
does DM. The removed person's next page load is the door, reading "You aren't a
member of this community **yet**" (`scratch/s8-phone-03-removed-member-reload.png`).
Their accommodation request and its details stay in **ADA requests (5)**
(`scratch/s8-desk-02-ada-queue-after-remove.png`). `list_by_status`
(`accommodation_repository.py:31-35`) scopes by tenant, not by membership, so
staff keep reading a non-member's disability details. On the boards, the icon
keeps following them into any match they're still listed in (`code-read`).

### F7 — Medium: Discord auto-join is silent on both sides

**Route/role/viewport:** `/t/second/` as fresh `aud_auto_desk_*` / `aud_auto_phone_*`, both widths.
**Evidence:** a signed-in non-member who opens the community lands straight on
its Schedule (`scratch/s3-desk-01-autojoined-landing.png`). There's no notice
that they just joined, which server let them in, or that leaving the server
won't undo it. The log shows no DM to staff, and nothing on the Users tab marks
the new row. The only trace is a `tenant.member_added` audit row with
`source: discord_auto_join` (`tenant_membership_service.py:209-213`). Someone
who followed a shared link is now a member of a community they never asked to
join, and staff can't tell auto-joined members from hand-added ones.

### F8 — Medium: staff get no notification of a new ADA request, and the sub-tab count never reaches zero

**Evidence:** ticking the box and saving details produced no `MOCK Discord DM`
line on either viewport (s5 logs), and setting Arranged told the member nothing
until they reloaded (status read NEW before the reload, ARRANGED after). The doc
says "staff watch the sub-tab count", but the count is `requesting_user_ids`,
which covers NEW, ACKNOWLEDGED and ARRANGED (`accommodation_service.py:31-35,
119-122`). On the seed it reads **ADA requests (3)** with one New request. After
my run it reads (5) with three. A request that's been handled still counts, so
the number can't tell staff whether anything is waiting. The count also only
shows once Admin → Users is open. The drawer carries no badge for it or for
pending join requests.

### F9 — Medium: a declined requester can ask again at once, and each ask DMs every staff member

**Route/role:** fresh `aud_join_phone_*` at 390, `staff_user` at 390.
**Evidence:** three request → decline cycles in about 30 s produced three
"has asked to join **Default**" staff DMs (s2 log: `total staff DMs from one
person: 3`). After a decline the door forgets the history and shows the full
form again (`scratch/s2-phone-05-door-after-3-denials.png`). The seeded outsider
reads the same on `default` despite a prior decline. The queue row shows no
count of earlier attempts and no request time. The decline DM ends "Reach out to
the community if you'd like to know more" (`discord_messages_tenant.py:41`) and
carries no button. The community's Discord invite is configured
(`discord_invite_url`), and that's the obvious link to hand over.

### F10 — Medium: the join switches sit 2,215 px above the button that saves them

**Route/role/viewport:** `/t/default/admin/settings` as `staff_user`.
**Evidence:** **Take join requests** renders at y=1086 and the page's only
**Save** at y=3301 on desktop. On phone they're at y=1207 and y=4919, a 3,712 px
gap across Station Pool, Room Screens and Tournament Hours
(`scratch/s4-desk-settings-full.png`, `s4-phone-settings-full.png`). Flipping
the switch and leaving the page drops the change without a warning. One Save
also writes every other setting on the page (`admin_system_config.py:404-435`),
so closing the door can fail on an unrelated hours validation error. Not driven,
to avoid rewriting a shared tenant's config. The switch's help text says "Staff
approve or deny on the Users tab" without linking it.

### F11 — Low: provisioning reports a count and names nobody (`code-read`)

`sync_all_users` toasts "Synced N users: … , K new accounts"
(`admin_discord_roles.py`, from `discord_role_mapping_service.py:149-190`).
`users_processed` is `UserRepository.get_all(has_discord=True)`, which counts
every account on the platform (37 here) rather than this community's members
(31). The K provisioned accounts aren't named, get no DM, and look the same as
signed-in members on the Users tab. Not driven: under the mock guild, Sync All
Users would grant and revoke roles across the shared `default` tenant.

### F12 — Low: the ADA icon is a 19×19 px target on desktop

Measured at 1440 on both boards: the `accessible` button is 19.2×19.2 px, below
WCAG 2.5.8's 24×24 minimum (`theme/tables/match_slots.py`, `size="xs" dense`).
At 390 it's 44×44. On the seeded data the popup tells the proctor "chair for
station 3" while Player Two sits at stations 5 and 7
(`scratch/s6-desk-proctor_only-proctor-station-board.png`). The note is free
text with no tie to the station assignment, and the popup offers no action
beyond Close.

### F13 — Low: Users-tab phone layout

The phone Filters toggle works. It opens the card, filters apply, and the badge
counts 1 then 2 (`scratch/s7-phone-02-ada-filtered.png`, log clean). Around it:

- the toggle sits at y=698, under six stacked toolbar rows;
- the **Filter by Role** select is a 54 px empty box with no placeholder, on desktop too;
- each mobile card ends with an empty `:` row (the unlabelled actions column) and an empty `Roles:` with no dash;
- long usernames run past the card edge;
- the ADA column reads "Requested" for New and Arranged alike, and its icon doesn't link to the request.

---

## What holds

- The door's copy changes correctly across all four switch combinations
  (`scratch/s3-*-door.png`). The signed-out variant names only the ways in that
  are still open.
- A door left open after requests are switched off is refused by the service
  with a readable warning (`code-read`, `tenant_membership_service.py:136-137`).
- The staff join DM carries a **Review the request** button to
  `/t/default/admin/users`, where the queue is the first card at both widths
  (y=329 desktop, y=402 phone). The approval DM's **Open the community** lands on
  the tenant home.
- The ADA icon's per-viewer gate holds for every role in the matrix above, and
  the popup never shows the member's own details.

## Not driven

- Discord **Sync All Users** and the live `GUILD_MEMBER_UPDATE` provisioning: the
  mock would rewrite roles in the shared `default` tenant.
- The **Take join requests** switch itself and the stale-door refusal: saving
  Settings rewrites every setting on a shared tenant.
- Auto-join closing a pending request: `second` takes no requests, and
  `default` would need its config flipped.
- The ADA icon disappearing from a live board after an edit (F5): it would mean
  editing seeded `player_two`'s request.
- Real Discord rendering of the DMs: mock-log text only, which includes the
  embed title and button target.
