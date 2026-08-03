# Home UX — cutting the player surface to four tabs

Home carried ten tabs for a signed-in member on a fully-featured community, and
between five and ten depending on which feature flags that community had on. The
phone bottom bar holds four, so the count decided — by list order — which tabs a
player could reach with a thumb. **Player**, holding their own matches and every
deep link a Discord DM sends, was not one of them.

The work splits in two. PR 1 is the nav restructure and has shipped; PR 2 is the
anonymous-facing half plus the tournament-room seeds view, and is **not started**.

| PR | Scope | Status |
|---|---|---|
| 1 | Four tabs, slug aliases, bottom-bar rule | done — see [pr1-four-tabs.md](pr1-four-tabs.md) |
| 2 | Join page, room seeds view, `RoomToken` | planned — see [pr2-join-page-and-room-seeds.md](pr2-join-page-and-room-seeds.md) |

## The decisions behind both

Recorded because they were argued through and the reasoning is not obvious from
the diff.

**Four tabs on every community, whatever its flags.** A flag now removes a *view*
inside the Event switcher, a *section* of My Schedule, or a *button* on a
Tournaments card. It never adds or removes a tab. Before this, no two communities'
phone nav looked alike.

**Aliases, not redirects.** Discord DMs outlive the app version that sent them,
and four of the six link targets in [discord.md](../../features/discord.md)
address `/home/player`. A tab absorbs the retired slugs it replaced and resolves
them on read-in only, so the URL normalizes on the first tab switch.

**The bottom bar renders only where the whole nav fits it.** It used to show
`tabs[:4]` everywhere with a **More** button for the rest, which on Admin meant
72px of phone screen offering four of twenty-seven tabs picked by list order,
plus a button that is the drawer with an extra tap. Home qualifies; Admin and
Volunteer navigate by drawer.

**Home is members-only, and always was.** `enforce_membership` renders the join
page for anyone who is not a member, anonymous included, before a single tab is
built. The "you must be logged in" bodies in the tab modules were unreachable and
came out. This is why PR 2's anonymous work lands on the join page rather than on
a new landing page.

**Seeds for unplayed matches are not published by default.** PR 2's room view is
reachable only by an unlisted token, because `GeneratedSeed.seed_url` is playable
and a player who finds it can study their own upcoming seed. Inside the app that
exposure is already wide — the member schedule board shows the seed column to
every member — but the open internet is a different blast radius.
