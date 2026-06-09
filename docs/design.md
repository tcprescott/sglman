# Original Design Notes (Superseded)

> **Superseded.** This early requirements sketch predates the current implementation and is retained only as a historical record. For an accurate description of the system, see [architecture.md](architecture.md); for the documentation index, see [README.md](README.md); for per-feature implementation notes, see [features/](features/).
>
> The original content is preserved below unchanged. Struck-through items were completed; the page list no longer reflects actual routes (see [reference/frontend.md](reference/frontend.md) for current routes).

---

# This application requires the following, with the higher requirements being the most important.

1. ~~Allow a user to submit a match for a tournament.~~
2. ~~Provide a general information page for all users to view.~~
3. ~~Allow matches to be assigned to a Stage.~~
4. API endpoint with matches scheduled for a Stage, include crew information.
5. ~~Rename "StreamRoom" to "Stage".  There are four stages (Stage 1, Stage 2, Stage 3, and Stage 4)~~
6. ~~Add crew signup system (Commentators and Trackers)~~
7. ~~Discord bot for messaging users via Discord~~

## Pages

`/` - The application's homepage.
`/schedule` - A read-only view of the schedule for everyone.  This is an unauthenticated view.
`/player` - The player dashboard.  Players can view upcoming or in-progress races for themselves, submit matches, and confirm a match submitted to them.
`/crew` - A crew signup view that requires a login.
`/admin` - An admin desk view of the schedule which also allows for rolling, editing of matches, and submitting a match on be behalf of a player.
`/api` - A simple API to allow other applications to retrieve data from sglman.
