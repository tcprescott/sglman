---
title: Being a player at the event
slug: player
icon: videogame_asset
order: 40
summary: My Schedule, acknowledging, getting a match booked, seeds and race rooms, asking for a different time, and your result.
---

This is how the app works for a player. What happens **on the floor**, meaning
check-in and stations, what you can have at your station, stage matches, and
what to do when something breaks, is set by the event rather than by the app.
Where your community publishes that information, it lives under **Event
Information** in the sidebar.

## My Schedule

**My Schedule** is everything you've personally signed up for, on one page. Your
matches come first, then any crew slots, then when you can't play, then any
equipment you've borrowed. (If you aren't entered in any tournament, your crew
slots move to the top.) The **Event** tab shows everybody's matches; this one
shows only yours. The **?** at the end of each section's heading opens help for
that section without leaving the page.

:::snippet player-schedule
**My Schedule** lists the matches you're playing in, in your local time. The
**Event** tab shows every match in the event; this one shows only yours.

Anything waiting on you sits above the list: an open race room, an opponent's
request to move your match, or a bracket matchup that still needs a time.
:::

![My Schedule on a phone: the Your matches panel with an open race room and an opponent's reschedule request above the list](/static/help/player/my-schedule-phone.webp "Anything waiting on you comes first.")

The **Your matches** panel puts things in the order you need to deal with them:

1. **Your race room is open**, when you have an online match about to start.
2. **Your opponent asked to reschedule**, when they've asked staff to move a
   match you're both in.
3. **Waiting on you to pick a time**, for bracket matchups with no time yet.
4. Your matches themselves, with a **Request Match** button where your
   tournaments take requests.
5. **Your change requests**, when you've asked staff to move something.

Your matches are laid out like the schedule board, one line each, grouped
into *Live now* and *Up next*. **Acknowledge** sits under the status and the
bell watches the match. Everything else you can do to a match is in its **⋮**
menu: **Ask to change**, **Harder settings** where the tournament offers them,
and **Offer for stream**. Tap the match's name for its details: your seed once
it's rolled, your station, and who's on crew.

A link from a Discord DM can narrow the list to one match. The chip at the top
says *Showing one match only*, and **Show all my matches** puts the rest back.

## Acknowledging a match

When you're scheduled into a match, the bot DMs you with an **Acknowledge**
button. You can also tap **Acknowledge** on the match's line on My Schedule.
Either way it tells staff you've seen the time and intend to be there, and the
match's details count you under *Players confirmed*.

It isn't a requirement, and nobody is stopped from playing for not
acknowledging. It is useful to staff and your proctor, though: each match's
*Ready to play?* checklist names who hasn't confirmed, and that's who they
chase, so acknowledging is the difference between being left alone and being
tracked down. It isn't check-in
either. You still check in at the event on the day.

If you booked the match yourself, you're acknowledged automatically, and staff
see it marked *(auto)*.

## Getting a match scheduled

How a match gets on the board depends on the tournament, and My Schedule only
offers the route your tournament uses.

### Request Match

Some tournaments let players book their own matches. Tap **Request Match**,
pick the tournament, your opponent, a date and a time, and tap **Submit**. The
match goes straight onto the board as {state:Scheduled}, and your opponent is
DMed.

:::snippet match-request
**Request Match** books a match: a tournament, your opponent and a time.

You must be signed up for the tournament to pick it, and so must your opponent.
If the dropdown is empty, either you haven't signed up for anything, or your
tournaments are run from a bracket, in which case you schedule your matchup from
**My Schedule** instead.

The time has to be in the future and inside the tournament's hours.
:::

### From a bracket

In a bracket-run tournament (on Wizzrobe or on Challonge) you don't request
matches. Your next matchup appears on My Schedule under **Waiting on you to pick
a time**, and the bot DMs you a button that opens the time picker directly.

:::snippet bracket-schedule
Tap **Schedule** (or **Schedule game 2**, in a best-of series), pick a time you
can both play, and tap **Schedule**. There's no confirm step: picking a time
books it, and your opponent gets a message. If the tournament takes change
requests, they can ask staff to move it.

Either of you can book it, so talk to your opponent first. If they get there
before you, the matchup leaves your list.

In a Challonge bracket, **Schedule** is greyed out until your opponent has linked
their Challonge account to Wizzrobe. Hover or long-press it to see why; staff can
also link them by hand.
:::

![The Waiting on you to pick a time card, listing three bracket matchups each with a Schedule button, the first one marked 1](/static/help/player/bracket-schedule-phone.webp "Bracket matchups that still need a time: tap **Schedule** (1) to pick one.")

### Suggest a time

:::snippet suggest-time
**Suggest a time** fills in a slot for you. It looks for a time neither player
has blocked out, falls within the event's operating hours, and avoids a moment
the venue is already busy. A time either of you marked *Prefer* wins ties.

It fills the fields in but doesn't book anything. Review what it picked and
change it if it doesn't suit.

If neither of you has blocked anything out, every hour of the event is fair
game, so block out what doesn't work for you under **When you can't play**.
:::

## When you can't play

:::snippet player-availability
You count as available for every hour the event is running. **When you can't
play**, on My Schedule, is where you carve out the hours you aren't: a shift, a
flight, a night you want off. Everything you leave alone stays open.

It feeds one thing: **Suggest a time**. When you or your opponent are picking a
slot for a match, that button skips anything either of you has blocked out and
leans towards anything either of you marked *Prefer*.

Blocking a time out is a signal, not a lock. Staff can still schedule you into
it, and your opponent can still propose it. It's also not a roster: nobody is
reading your windows and placing you into the hours you left open.

This is separate from the availability editor on the Volunteer tab, which works
the other way round: there you say when you *can* work, and a shift is only
offered to you inside a window you entered.
:::

## Your seed

For a randomizer tournament, the seed is the game you're about to play. Staff or
the proctor roll it shortly before the match. When it lands, the bot DMs you a
**🎲 Seed ready** message with an **Open your seed** button. The same seed is
under **Seed** in the match's details on My Schedule (tap the match), with a
**Copy** button.

Some randomizers take a few minutes to generate a seed. While that happens the
details say *Rolling…*, and you can leave the page: the DM still arrives.

Some randomizers don't give you a link. Wind Waker gives you a **permalink** and
Zelda 1 a seed and flags, which you paste into your own copy of the randomizer.
The DM shows it in a box you can long-press to copy, and the match's details
have a **Copy** button beside it. A Wind Waker permalink only works in the build the DM
names, so check you've got that one before you paste.

### Harder settings

:::snippet harder-settings
Some tournaments offer a harder preset beside the standard one. **Harder
settings** in a match's **⋮** menu lets you opt in for one match, and the match only
plays harder if **every** player opts in.

Your answer is private. Nobody is told you opted in unless all of you did, and
nobody is told if you decide against it. Once everyone is in, the menu item
reads *Playing* and the preset's name.

You can change your mind until the seed is rolled. After that, or if staff have
set the match's settings themselves, there's nothing left to choose.
:::

## Your race room

If your match is played online, it happens in a racetime.gg room. When the room
opens, the bot DMs you a **🏁 Your race room is open** message, and the top of My
Schedule shows **Your race room is open** with a **Join the room** button. The
room opens in a new tab.

Linking your racetime.gg account under **Connected accounts** on your Profile
means your results are credited to you.

## Offering your match for stream

:::snippet stream-volunteer
**Offer for stream**, in a match's **⋮** menu on My Schedule, is where you say
you'd be happy for your match to go out on stream. Pick it once to offer, and
**Withdraw stream offer** in the same place takes it back.

It's a hint to staff, nothing more. They build the stream schedule around
stages, crew and what the bracket needs, and they won't read your offer as a
claim on any of it. Offering doesn't book a stage, doesn't guarantee your match
is streamed, and doesn't change anything about how it's run.

If both players offer, staff see both names. Either of you can withdraw at any
time, including after the match has started.
:::

## Asking for a different time

You can't move or cancel your own match, but you can ask, and you don't have to
find a staff member to do it.

:::snippet reschedule-request
**Ask to change**, in a match's **⋮** menu on My Schedule, asks staff to move your
match or call it off. It's a request, not a booking: nothing changes until staff
answer, so keep playing to the current time until you hear back.

Say why. Staff read the reason and nothing else, so it's what they decide on.
You can name a time you'd prefer, or leave it blank if all you know is that the
current slot doesn't work, and staff will pick one.

Your opponent gets a DM with an **Agree** button. Their agreement isn't a veto
and isn't a requirement; it just saves staff asking whether you're both happy.

You'll hear the outcome either way. If staff approve, the match moves and
everyone involved gets the usual reschedule notice. If they decline, you get
their reason and an **Ask again** button.

The button isn't there when the tournament doesn't take requests, when the
match is already checked in (find your proctor instead), or when its schedule
comes from SpeedGaming, which has to change at the source. Once you've asked,
the **⋮** menu shows *Change requested* until staff answer.
:::

![The Ask staff to change this match form: what you're asking for, a preferred date and time, and a required reason](/static/help/player/ask-to-change-phone.webp "The request form behind Ask to change.")

**Your change requests**, below your matches, is where your requests and their
answers live: what you asked for, whether your opponent agreed, and what staff
said. **Withdraw** takes back one that's still waiting.

### When your opponent asks

If your opponent asks to move a match you're both in, **Your opponent asked to
reschedule** appears at the top of My Schedule with their reason. **Agree**
tells staff the change works for you; staff still make the call. You don't have
to answer, and not answering doesn't block anything.

## If something changes

Rescheduled and cancelled matches DM everyone involved. If your match moves,
you'll hear about it, so you don't need to keep refreshing the board.

## Your result

The proctor records the winner when the match ends, and the board goes to
{state:Finished}. That isn't the official result yet: a staff member reviews it
and confirms it, which moves the match to {state:Confirmed}.

If the two of you disagree about what happened, tell the proctor before you
leave. They record their best call and flag the match for a staff member to look
at, with a note about what was in dispute. Staff settle it when they confirm the
result.

## Needing an accommodation

If you need something arranged to play, such as step-free access or extra time
between matches, ask from your Profile. See
[Asking for an accommodation](/help/accessibility).
