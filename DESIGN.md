# This application requires the following, with the higher requirements being the most important.

1. ~~Allow a user to submit a match for a tournament.~~
4. Provide a general information page for all users to view.
5. ~~Allow matches to be assigned to a stream room.~~
6. Allow crew to sign up, and for privledged users to be able to able to approve crew.

## Pages

`/` - The application's homepage.
`/schedule` - A read-only view of the schedule for everyone.  This is an unauthenticated view.
`/player` - The player dashboard.  Players can view upcoming or in-progress races for themselves, submit matches, and confirm a match submitted to them.
`/crew` - A crew signup view that requires a login.
`/admin` - An admin desk view of the schedule which also allows for rolling, editing of matches, and submitting a match on be behalf of a player.
`/api` - A simple API to allow other applications to retrieve data from sglman.