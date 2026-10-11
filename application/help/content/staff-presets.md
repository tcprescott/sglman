---
title: Seed presets and test rolls
slug: staff-presets
icon: tune
order: 244
roles: STAFF, PRESET_MANAGER
summary: Adding and importing seed presets, checking them with a test roll, and attaching them to a tournament.
---

A preset is a named set of randomizer settings. Pick one on a tournament and every
seed rolled for its matches uses it. Presets live on **Admin → Presets**, under
Online play. Staff and anyone with the Preset Manager role can change them.

## Getting presets in

There are three ways to add one:

- **Import Built-ins** adds the presets that ship with Wizzrobe. Running it again
  only adds ones you don't have yet.
- **Import from Randomizer** fetches the presets a randomizer publishes on its own
  site. Pick the randomizer, fetch its catalogue, type to filter, and tick the
  ones you want. An imported preset is your copy: later changes on the
  randomizer's site don't follow it.
- **Add Preset** takes a name, a randomizer, a description, and the settings as
  JSON. Use it when you have the exact settings from a randomizer's own tools.

Some randomizers need your community's own API key before they appear in the
randomizer list or can roll anything. Set those under **Settings → Integrations →
Randomizer Keys**. A stored key is never shown again, only whether it's set.

## Test roll before the event

:::snippet admin-preset-test-roll
Every preset has a **Test roll** button (the flask icon on its row). It rolls one
seed the way a match would and shows you the link, or the randomizer's error if
the roll failed. The seed isn't attached to any match and nobody is sent it.
:::

Test every preset your tournaments will use before the doors open, and again if
you change its settings. A failure here is one you would otherwise find with two
players sitting at a station.

Most rolls take seconds. Donkey Kong 64 can take a few minutes, so leave the
dialog open.

Some randomizers roll their own bundled settings and ignore a preset's. For those,
the dialog says so: the test proves the randomizer works, not that this row's
settings are right.

## Attaching a preset to a tournament

Open the tournament on **Admin → Tournaments** and choose it under **Seeds &
randomizer → Seed Preset**. The preset decides which randomizer the tournament
rolls with, so there is nothing else to set. Choose **None** and the tournament
rolls no seeds.

A tournament set up before presets existed may say it's still rolling with an
older generator and no preset. Pick a preset to replace it. Saving with None turns
seed rolling off.

## The harder preset

**Harder Preset (opt-in)** is a second preset players can ask for, privately, one
match at a time. A match rolls it only when every player in that match opted in.
Nobody learns whether their opponent opted in unless they both did, so nobody
feels dared into it.

Both presets have to use the same randomizer. Test roll the harder one as well.

## Rolling a match's seed

Once a tournament has a preset, the Seed column on the Schedule and on the Proctor
Station board offers **Generate** for any match that has players and no seed yet,
unless it runs in a racetime.gg room. Rolling DMs the seed to the players. Staff, proctors and the tournament's admins
can roll.
