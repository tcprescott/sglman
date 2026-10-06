# Matcherino private API

Everything we know about the API matcherino.com's own web app calls, so nobody
has to reverse-engineer it again. Matcherino has no public API. Their staff are
fine with Wizzrobe using these endpoints, but they won't support them, so any of
this can change without notice.

Source: a Chrome HAR of the SpeedGaming Live 2026 badge admin page
(`matcherino.com/events/182105/admin/tickets`), captured 6 October 2026,
plus the endpoint names in the web app's JavaScript bundle. Endpoints marked
**seen** were called in that capture, and their shapes below come from real
responses. **Bundle only** means the name and parameters come from the bundle
and the endpoint has never been called by us.

The consumer is `application/utils/clients/matcherino_client.py`. How check-in
uses it is in [event-check-in.md](../features/event-check-in.md).

## Basics

- Base URL: `https://api.matcherino.com/__api/`. A few calls go to
  `https://matcherino.com/__api/` instead (the same API through the site's own
  host), e.g. `marco/history`.
- Every response is an envelope:
  - Success: `{"status": 200, "body": <payload>}`.
  - Failure: `{"status": 401, "error": {"id": "", "name": "", "message": "..."}, "body": null}`,
    with a matching HTTP status. Example message: `"marco history requires authentication"`.
- **Not-found isn't always an error.** `bounties/participants` for an unknown
  bounty answers `200` with `contents: null`, which looks exactly like an empty
  bounty.
- Paged lists share one shape:
  `{"query": {"filter", "page", "pageSize", "sort"}, "links": {"next"?}, "pageCount", "itemCount", "contents": [...]}`.
  Pages are zero-indexed. `contents` can be `null` rather than `[]`.
- POST bodies are JSON sent as `Content-Type: text/plain;charset=UTF-8`, which is
  what the web app does. We match it rather than find out what else the server
  tolerates.
- Money is integer **cents** (`amount: 8000` is $80). `bounties/findById` is an
  exception: it reports `passPrice` as a decimal string (`"0.00"`).
- Timestamps are ISO 8601 UTC with microseconds and `Z`
  (`2026-02-02T02:26:47.123201Z`). A missing time is `null`.
- Ids are integers in JSON. Wizzrobe stores Matcherino user ids as strings
  (`User.matcherino_user_id`, `CheckInEntrant.matcherino_user_id`).

## Vocabulary

| Matcherino says | Means |
|---|---|
| **bounty** | Any event page. Tournaments, crowdfunds, and venues are all bounties |
| **venue** | A bounty with `kind: "venue"` that sells badges. SG Live 2026 is venue **182105** |
| **pass** | A badge type on a venue (Base, VIP, Day Pass). We call it a *tier* |
| **pass purchase** | One badge someone bought. It has a numeric door `code` |
| **attachment** | A bounty linked to a venue. SG Live 2026's tournaments are bounty **182107**, attached to venue 182105. Buying a badge auto-joins the buyer to it |
| **doorman** | A venue role that scans badges at the door |

Don't mix up the venue and its tournaments bounty. The badge admin page is
`/events/<venue id>/admin/tickets`, and the tournaments bounty has its own id.
`fetch_venue` refuses an id whose `kind` isn't `"venue"`.

## Authentication

The web app keeps a long-lived **refresh token** (a UUID) and uses it to mint
short-lived **access tokens**.

**Minting** (seen):

```
POST https://api.matcherino.com/__api/auth/token
Content-Type: text/plain;charset=UTF-8

{"appName": "WEB", "refreshToken": "<uuid>"}

→ {"status": 200, "body": {"accessToken": "<JWT>", "refreshToken": "<uuid>", "expiresIn": 86400}}
```

- No cookies are sent. The refresh token in the body is the whole credential.
- `expiresIn` is in seconds: access tokens last 24 hours.
- The returned `refreshToken` is the same one that was sent. **It does not
  rotate**, so a stored value keeps working until the account signs out
  everywhere or Matcherino revokes it.
- The access token is a JWT. Its payload holds only `exp` (Unix seconds) and
  `sub` (the Matcherino user id as an integer).

**Using it.** Send `x-mno-auth: Bearer <accessToken>` on every authenticated
request. It's a custom header, not `Authorization`. An unauthenticated call to a
protected endpoint answers HTTP 401 with the error envelope above.

**What Wizzrobe stores.** `MATCHERINO_REFRESH_TOKEN` is the refresh token of an
account that is an admin of every venue we sync. The client mints an access
token on first use and caches it for the whole process until five minutes before
it expires. On a 401 or 403 it mints again once and retries. A second refusal
means the account doesn't administer that venue.

**Getting a refresh token.** Sign in to matcherino.com as that account, open
DevTools → Network, reload any page, and select the `token` request to
`api.matcherino.com/__api/auth/token`. Copy `refreshToken` from its request
payload. Treat the value like a password: anyone holding it is that account.
Don't share a HAR captured while signed in, since it contains this token.

## Venue and badge endpoints (what check-in uses)

### `GET bounties/findById?id=<id>` — seen, no auth needed

Any bounty, venues included. It returns about 90 keys. The ones that matter:

| Key | Notes |
|---|---|
| `id`, `title`, `status` | `status` was `"ready"` for SG Live 2026 |
| `kind` | `"venue"` for a ticketed venue. Check this before treating an id as a venue |
| `passCount`, `passPrice` | 4 and `"0.00"` for SG Live 2026 (`passPrice` is not the badge price) |
| `childCount` | Attached bounties: 1 (the tournaments bounty) |
| `startAt`, `endAt`, `timezone` | |
| `hasLocation`, `address1`, `city`, `state`, `zip`, `country` | Empty for SG Live 2026 |
| `participantIds`, `bracketIds`, `entryFee`, `playerLimit`, … | Tournament fields, meaningless on a venue |

`POST bounties/findByIdList` (seen, authenticated) takes a JSON **array** of ids
(`[182107]`) and returns an array of the same objects.

### `POST venues/pass/listPrivate` — seen, venue admin

Body `{"venueId": 182105}`. Returns an array of badge types, including any not
on sale. The public equivalent is presumably `venues/pass/list` (not confirmed).

| Key | Type | Notes |
|---|---|---|
| `id` | int | The pass id (1988–1991 for SG Live 2026) |
| `title` | str | `"SG Live Base Tier Badge"` |
| `amount` | int | Price in cents |
| `role` | str | `"player"` or `"spectator"` |
| `qtySold` | int | Badges sold. The four add up to the purchase count, which is how the client spots a truncated purchase list |
| `maxTotal` | int | Stock cap. Only on the copy embedded in a purchase or in `session/passes` |
| `precedence` | str | `"primary"` |
| `description`, `thumbnailImg` | str | |
| `availableStart`, `availableEnd`, `validStart`, `validEnd` | str/null | Sale window and validity window |
| `discountsAvailable` | int | |
| `isDeleted` | bool | |
| `venueId`, `createdAt`, `meta` (`{}`), `applicableTaxes`, `availableChildren`, `availableParents` | | `null` in every capture |

### `GET venues/admin/purchaseData?venueId=<id>` — seen, venue admin

Every badge purchase, in one array with no paging. SG Live 2026 returned 172
purchases (about 590 KB). The web app's admin page calls it twice on load.

| Key | Type | Notes |
|---|---|---|
| `id` | int | Purchase id. Other endpoints call it `passPurchaseId` |
| `passId` | int | The badge type |
| `pass` | object | The badge type embedded (keys as above, with `maxTotal`). Still present if the type is later deleted |
| `userId` | int | The buyer |
| `user` | object | The buyer's account, see below |
| `code` | int | Door code, 5–8 digits, unique per purchase. Presumably what the `/events/<id>/checkin` "Scan QR" page reads |
| `purchasedAt` | str | |
| `refundedAt` | str/null | Set when refunded. All `null` in the capture, so the shape of a refunded purchase is unconfirmed |
| `completed` | bool | `false` on all 172, meaning unknown |
| `entries` | null/array | Door scans. `null` in this admin view even though scans exist (see `session/passes`) |
| `transactions` | array | A payment ledger. Two per purchase: `pass_purchase` (the price) and `pass_purchase_fee` (100 cents), each `operation: "gain"` with nested `details` of type `group`/`pass`/`pass_purchase`/`venue`. **We don't store this** |
| `firstName`, `lastName`, `email`, `phone`, `address1`, `address2`, `city`, `state`, `zip`, `country` | str | Contact details, filled only when the venue requires them (`passRequireName`/`Email`/`Phone`/`Shipping`). All empty for SG Live 2026. **We don't store these** |
| `bountyAttachments` | array | `[{id, title, thumbnailImg, joined}]`. Every SG Live 2026 purchase showed `{id: 182107, joined: true}` |
| `venueId`, `sourceId`, `sourceType` (`""`), `revshareTotal`, `meta` (`{}`), `upsells`, `venue` | | `venue` is `null` here |

The embedded `user` object:

| Key | Notes |
|---|---|
| `id`, `displayName`, `userName` | `userName` is Matcherino's own handle, not the sign-in provider's login |
| `authProvider` | `discord`, `twitch`, `gplus` (Google), `facebook`, `youtube`, `battlenet`, `twitter`. SG Live 2026 had 67 Discord, 70 Twitch, 29 Google, 3 Facebook, 1 each of the others |
| `authId` | The provider's account id: the Discord snowflake for `discord`, the numeric Twitch user id for `twitch`. Always numeric in the capture |
| `avatar`, `url`, `createdAt`, `status`, `verified`, `partner`, `banned`, `gameRegion`, `locale` | |
| `email`, `notificationsEmail`, `lastLoginAt` | `null` here |
| about 25 more | Counters, flags and relations (`followers`, `passes`, `transactions`, …), mostly `null`/`0` |

A buyer can appear more than once. In the capture three buyers held two badges
each (Base + Super VIP, Base + VIP, Base + Day Pass), all bought the same day,
probably one each for a friend. Purchases carry no name for whoever holds the
second badge.

### `GET session/passes` — seen, authenticated

The signed-in user's **own** badges across every venue. It returns the same
purchase objects, except `venue` is filled in (tax and revshare settings, the
`passRequire*` flags, `creator`, `title`) and `entries` is populated:
`[{"passPurchaseId", "entryDate", "doormanId"}]`. That's how we know door scans
are recorded per purchase. A `doormanId` of `0` appeared on a scan.

## Other venue endpoints (bundle only)

The names and parameters come from the bundle's request builders. None have been
called, and the response shapes are unknown.

| Call | Parameters | What the web app uses it for |
|---|---|---|
| `GET venues/admin/purchaseDataDownload` | `?venueId=` | CSV export of the purchases |
| `POST venues/admin/sendEmails` | body unknown | Emailing buyers |
| `GET venues/doorman/list` | `?venueId=&page=&pageSize=5` | Latest door check-ins (the app's action is `VENUE_GET_LATEST_CHECKINS`) |
| `POST venues/pass/use` | body unknown, has `venueId` | Records a door scan. Pushes realtime to room `bounty:<venueId>`; the result carries `entries` |
| `POST venues/pass/unuse` | body unknown | Undoes a door scan |
| `POST venues/pass/refund` | body unknown | Refunds a badge |
| `POST venues/pass/create` / `update` | the pass object | Edits badge types |
| `POST venues/pass/delete` | `{"venueId", "passId"}` | |
| `POST venues/pass/buy` | the cart, with `bountiesToJoin` | Checkout. This is why buyers auto-join attached bounties |
| `POST venues/pass/subtotal` | the cart | Price preview |
| `POST venues/inviteTournament` | `{"venueId", "bountyId"}` | Invites a bounty to attach |
| `GET venues/invite/code` | `?bountyId=&inviteId=` | |
| `* venues/invite/response` | `?id=<inviteId>&…` | Accepts or declines an invite |
| `POST venues/invite/cancel` | | |
| `GET venues/listAttachable` | `?foreignId=&foreignType=` | |
| `POST venues/attach` / `detach` | | |
| `POST venues/reorderBounties` | | |

Wizzrobe deliberately calls none of these. Check-in records arrivals in its own
database and never writes to Matcherino.

## Other endpoints seen in the capture

| Call | Auth | Notes |
|---|---|---|
| `GET bounties/participants?bountyId=&page=&pageSize=` | no | A bounty's participant list, paged (we used up to 500 per page). Each item has `userId`, `displayName`, `authProvider`, `authId`, `avatar`, `addedAt`, and `socials` (sometimes a linked Twitch login). **Check-in used this until October 2026** |
| `GET events/activities?bountyId=&pageSize=50&page=0` | no | The activity feed, paged |
| `GET globals` | no | Platform settings: `tosUpdatedAt`, `minimumDeposit`, `minimumWithdrawal`, `maintenanceMode`, and so on |
| `GET games` | no | All games, about 377: `{id, slug, title, image, hero, publisher, gamePublisherId, createdAt}` |
| `GET session/userPrivate` | yes | The signed-in account's private profile |
| `GET organizations/members?orgId=&page=&pageSize=&userId=` | yes | Paged |
| `GET users/games/usernames?userIds=` | yes | `body` can be `null` |
| `GET users/notifications/list?userId=`, `users/discord/status`, `taxidentity/interview/completed` | yes | |
| `GET session/corsPreflightBypass` | no | Returns HTML. A CORS workaround in their app |
| `GET matcherino.com/__api/marco/history?limit=5` | yes | 401 when signed out |
| `wss://ws.matcherino.com/__api/websocket?deflate=true` | — | Realtime updates. The app joins rooms such as `bounty:<id>` |

## When it breaks

- A parse that raises `MatcherinoAPIError` with "the API shape may have
  changed" means a field we rely on moved. Capture a new HAR of the venue's
  Tickets page and compare it with the tables above.
- "Matcherino refused the stored login (`MATCHERINO_REFRESH_TOKEN`)" means the
  refresh token was revoked. Get a new one (see above) and redeploy.
- "must be an admin of this venue" means the account behind the token lost
  admin on that venue. Add it back as an admin on Matcherino.
- "counts N badges sold but listed M" means the purchase list came back
  shorter than the badge counts. Matcherino may have started paging this
  endpoint. Look for `page` parameters on the admin page's request.
