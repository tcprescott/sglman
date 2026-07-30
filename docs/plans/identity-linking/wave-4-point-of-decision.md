# Wave 4 — say what the link buys

**Read [README.md](README.md) first. Wave 1 must be merged** — this wave is
entirely about a card that does not render in dev without it. Waves 2 and 3 are
not prerequisites; this wave touches only
[`pages/home_tabs/_link_section.py`](../../../pages/home_tabs/_link_section.py)
and the three provider configs.

The audit praised this surface for explaining what each link buys, quoting *"Link
your racetime.gg account so we can attribute your race results and check
auto-open eligibility."* That sentence is real, it is in the source, and it has
never been on a screen. `LinkSectionConfig` declares `description` and
`link_button_label`; `_render_provider_row` reads neither, and the button is the
literal string `'Link'`.

This is the audit's own cross-cutting theme — *"capabilities nobody wired are
invisible"* — landing on the audit. It is also the smallest wave here: three
config fields, one row renderer.

| Task | Touches | Size |
|---|---|---|
| T4.1 | render `description`, and either use or delete `link_button_label` | small |
| T4.2 | say when a link was made | small |
| T4.3 | the custom-domain dead end: *"Main site only"* with no way to the main site | small |

One commit for T4.1+T4.2, one for T4.3.

---

## T4.1 — Render the copy the config already carries

**Every field on a dataclass must be read or deleted.** Two are not read; decide
each way and do not leave a third state.

**`description` — render it.** It is the one sentence that answers *why would I
do this*, it differs meaningfully per provider (attribution and auto-open
eligibility for racetime; bracket-match discovery and self-scheduling for
Challonge; identity association for Twitch), and the card-level blurb above it —
*"Link external accounts to verify your identity and let us find your bracket and
race matches for scheduling."* — is a generic smear of all three.

**Render it for unlinked rows only.** A linked provider does not need the pitch,
and three descriptions plus three statuses in one card is a scroll on a phone.
Unlinked is where the decision is being made, which is the whole point of the
copy. Put it under the title in the same column, `text-caption text-muted`,
replacing nothing — the "Not linked" line still needs to be there or the status
disappears.

**`link_button_label` — use it as the accessible label, not the visible one.**
*"Link racetime.gg account"* on a dense row button is too wide at 430px and
redundant beside a row already titled "racetime.gg". But `'Link'` × 3 with no
context is exactly what a screen reader announces today. So: keep the visible text
short and set `link_button_label` as the button's `aria-label` and tooltip. The
config field is then genuinely read, the visual density is unchanged, and the row
stops being three identically-named buttons to anyone not looking at it. Do the
same for **Unlink**, which has the same problem and no config field at all — add
one, or derive it from `title`.

If you conclude a field should not be rendered, **delete it from the dataclass and
all three configs in the same commit.** Dead config that reads like shipped
behaviour is the bug this wave exists to fix; leaving one behind reproduces it.

**Mobile is the constraint, not an afterthought.** Measure the card's height at
430px before and after, for a user with three unlinked providers (the worst case)
and one with three linked. Quote both numbers. The card is not a `ui.table`, so
the mobile-grid rule does not apply — but "three rows became three paragraphs" is
the failure mode, and a number is the only defence against it.

---

## T4.2 — Say when the link was made

`User.<provider>_linked_at` is written on every link (all three services set it)
and displayed nowhere. The linked row says *"Linked as MockRacerOne"* and stops.

Add the date to that line — `format_eastern_date` from
`application/utils/timezone.py`, never the raw UTC value and never
`str(dt)`; see [docs/timezone-handling.md](../../timezone-handling.md). A
`linked_at` may be `NULL` on a row linked before the column existed, so the date
is additive: no date, no change to the line.

Why it earns its space: the only question a *linked* row raises is *"is this still
the account I think it is?"*, and a date is what lets someone recognise a link
they made years ago under a name they have since changed at the provider. It costs
one field on a line that already exists, and it is the reason the description can
be dropped from linked rows in T4.1 without the row going mute.

---

## T4.3 — The custom-domain dead end

On a custom domain with `HOST_OAUTH_MODE` unset, `_render_provider_row` renders,
in place of the button:

```python
ui.label('Main site only').classes('text-caption text-grey') \
    .tooltip('Account linking is available on the main site.')
```

That is the right *decision* — the callback lands on the platform host, which
cannot see this domain's cookie, so a button here would fail silently — and the
wrong *affordance*: it names a place and does not go there. The user is told the
thing they want exists somewhere else and left to find it.

Make it a link to the platform-host equivalent of this page. The server already
knows how to build that URL — `platform_link_redirect` in
[`pages/_oauth_link.py`](../../../pages/_oauth_link.py) computes exactly it from
`get_base_url()` and the tenant slug, for the redirect the button would have
taken. Reuse that rather than reassembling a host from parts in the presentation
layer; if it needs to be callable from a section renderer, that is a small,
honest extraction.

Keep the explanation. *"Main site only"* as a bare link is worse than the label —
say where it goes and why, in the tooltip, in a sentence that does not mention
cookies or redirect URIs.

**Reachability, stated plainly:** this branch requires host mode with handoff
off, so it is measurable only with wave 1's two-host recipe (T1.4). If that was
dropped, tag this task `code-read` and say so — do not describe it as verified.
It is also the branch that *disappears* when `HOST_OAUTH_MODE=handoff` is
switched on (the button works in place then), so a test asserting the label under
handoff-off and the button under handoff-on is what keeps both halves honest.

---

## Tests

`tests/theme/` is the home; the section is a presentation unit with a service
factory, so a stubbed config is enough for most of it.

```python
def test_every_link_section_config_field_is_rendered()
def test_an_unlinked_row_shows_the_providers_description()
def test_a_linked_row_does_not_repeat_the_description()
def test_the_link_button_carries_the_configured_accessible_label()
def test_a_linked_row_shows_the_link_date_in_eastern()
def test_a_linked_row_with_no_date_omits_it()
def test_custom_domain_without_handoff_links_to_the_platform_host()
def test_custom_domain_with_handoff_renders_the_link_button()
```

The first is the one that matters and the one to write first: introspect
`LinkSectionConfig`'s fields and assert each appears in the rendered row (or in
the row's props) for at least one of the linked/unlinked states. That is the
mechanical guard against a fourth field being added, configured three times, and
never shown — which is precisely how this wave came to exist.

---

## Verify

At 1500px **and** 430px, tagging every claim, as three users:

| User | Expect |
|---|---|
| `player_three` (nothing linked) | three rows, each with its own description, each button carrying the provider's accessible label |
| `player_one` (all three linked, after wave 1 T1.2) | three rows naming each account and its link date, no descriptions |
| a mixed user (link one of `player_three`'s, leave two) | descriptions on the two unlinked rows only, no layout jump |

Quote the card height at 430px for the all-unlinked case against the 844px
viewport, and screenshot each. Read the screenshots back: a description rendered
into the wrong column or an `aria-label` set on the wrong element both look
approximately fine and are both wrong.

Then run `scripts/ui_flag_sweep.sh` — the Challonge row is flag-gated, and a
description is a new place for a flags-off tenant to leak a mention of a feature
it does not have.

Docs: identity linking has no feature doc, and after this wave the Connected
accounts card has behaviour worth one short paragraph in
[`docs/reference/authentication.md`](../../reference/authentication.md) — what each
provider link is for, and that a provider with no credentials is hidden rather
than offered (the thing this surface got right, and the reason the audit opened by
praising it).

Commit T4.1+T4.2 as *"Show what each account link is for, and when it was made"*
and T4.3 as *"Send a custom-domain user to the site where linking works"*.
