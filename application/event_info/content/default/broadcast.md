---
title: Broadcast tech info
slug: broadcast
icon: videocam
order: 50
roles: STREAM_MANAGER, STAFF
summary: Dev fixture, a second role-gated article, so a viewer with only STREAM_MANAGER (not PROCTOR) is exercised too.
---

Development fixture content for the `default` tenant. Its purpose is to be
**invisible** to a signed-out visitor and to a signed-in user holding neither
`STREAM_MANAGER` nor `STAFF`; if you can see this without one of those roles,
the role filter is broken. Unlike `proctoring`, this article does not grant
`VOLUNTEER` or `PROCTOR`, so it exercises a viewer who holds one gated role but
not the other.

## Your room, and where it ends

:::snippet broadcast-boundary
You are responsible for the stream room or stage you are producing, and
nothing outside it. A proctored tournament room is not yours to run.
:::

## Before you go live

:::snippet broadcast-checklist
Confirm the match with the proctor or admin before you roll anything, and
check audio, camera and capture are working before a match is called in.
:::
