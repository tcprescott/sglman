# Wave 3 — Column widths

Drag the divider between two headers to resize; the width persists like every
other preference. Quasar's `QTable` has **no** built-in column resizing, so this
is ours.

Adopted on Admin → Users (from wave 2) and Admin → Schedule — the board with the
120px cap on every cell that finding F4 is about.

---

## 1. The client — `static/js/table-columns.js` (new)

Loaded once from `BaseLayout.render_chrome()` via `ui.add_body_html`, beside
`install_connection_watch()`.

**One delegated `pointerdown` listener on `document`. No injected handle
elements.** Injected nodes are destroyed on every Vue re-render, and these tables
re-render on every row refresh — the match board does so constantly. A delegated
listener plus a CSS `::after` affordance survives all of it for free.

```
pointerdown → is the target a <th> inside .wiz-table/.match-table/… ?
            → is the pointer within RESIZE_ZONE (6px) of its right edge?
            → is matchMedia('(min-width: 1024px)').matches?     // desktop only
            → is document.body without .wiz-offline?            // writes need a socket
   yes → setPointerCapture, record startX + startWidth, add .wiz-resizing to <body>
pointermove → width = clamp(startWidth + dx, 40, 1200); write it to the <col>
              (or the th's style) directly. No server traffic during the drag.
pointerup   → emitEvent('wiz_table_width', {key, column, width}); release capture
dblclick    → emitEvent('wiz_table_width', {key, column, width: null})  // auto-fit
Escape      → restore startWidth, no emit
```

Three details worth writing down in the file's own comment block:

- **`pointercapture`, not a document-level `mousemove`.** A fast drag that leaves the window otherwise strands the table mid-resize.
- **The table's key must be readable from the DOM.** `customize_table` sets `data-wiz-table-key` on the table element; the JS reads it off the nearest ancestor. Nothing else identifies which table a `<th>` belongs to.
- **`user-select: none` on `<body>` while dragging** (`.wiz-resizing`), or the drag selects header text on every table it crosses.

## 2. The CSS — `static/css/styles.css`

Add to the existing data-tables section:

```css
/* Only a table that has at least one stored width switches to fixed layout;
   an unresized table keeps today's content-driven sizing exactly. */
.wiz-table--sized table.q-table { table-layout: fixed; }

/* The 6px affordance the JS hit-tests. Pseudo-element, so nothing is inserted
   into the DOM Vue owns. */
.wiz-table thead th::after,        /* + the four family table classes */
… { content: ''; position: absolute; top: 0; right: 0; width: 6px; height: 100%;
    cursor: col-resize; }
.wiz-resizing, .wiz-resizing * { user-select: none !important; cursor: col-resize !important; }

@media (max-width: 1023px) { .wiz-table thead th::after { display: none; } }
```

The `thead th` rules need `position: relative` added — check the existing block
first; the family tables already set padding there and must not shift.

**Wrap lines interacts with this.** With `table-layout: fixed`, the `.wrap`
max-widths from finding F4 become dead weight — a fixed column already bounds its
content. Gate them: `.wiz-table:not(.wiz-table--sized) td .wrap { max-width: … }`,
so an unresized table keeps today's behaviour and a resized one obeys the user.

## 3. The server handler — `theme/tables/preferences.py`

`customize_table` registers, once per table:

```python
table.on('wiz_table_width', lambda e: background_tasks.create(
    _persist_width(e.args, key, context.client)))
```

`context.client` is captured **at build time** and passed in — reading it inside
the coroutine raises (`check_slot_context.py`'s second check catches this). Inside:
`with client:` → `await TablePreferenceService().set_width(user, key, column, width)`
→ on `ValueError`, `ui.notify(..., color='warning')`. `width=None` clears the
stored width (the double-click auto-fit).

No optimistic UI to reconcile: the browser has already painted the new width, and
the server is only recording it.

## 4. Width steppers in the modal

The `ui.number` per column from wave 2 becomes live in this wave: it writes the
same `width` field, is the keyboard path to resizing, and shows the current value
after a drag. Blank clears the width.

## 5. Adopt on Admin → Schedule

`theme/tables/match.py` — `MatchTableView` gains `table_key`, and calls
`customize_table` **after** `render_grid_slot(...)` (ground rule 1; the match
table's bespoke card is the one most worth protecting).

`pages/admin_tabs/admin_schedule.py` passes `TableKeys.ADMIN_SCHEDULE` and renders
the gear in the strip above the board.

**Do not** wire the proctor board (`TableKeys.PROCTOR_STATION`), the home Schedule
tab or the Player tab in this wave even though they share `MatchTableView` — they
are four different tables through one class and each needs its own key. They come
in wave 4, together, so the key-per-surface decision is reviewed once.

---

## 6. Tests

`tests/theme/test_table_widths.py`:

| Test | Pins |
|---|---|
| `test_a_stored_width_becomes_style_and_header_style` | already in wave 1; assert it reaches `table.columns` here |
| `test_a_table_with_no_widths_does_not_get_fixed_layout` | the `--sized` class is conditional |
| `test_set_width_null_clears_the_column` | double-click auto-fit |
| `test_width_out_of_range_is_rejected` | a hand-crafted `emitEvent` is untrusted input |
| `test_the_handler_captures_the_client_at_build_time` | source scan, mirroring `check_slot_context`'s rule |

`tests/theme/test_table_resize_js.py` — a text assertion over
`static/js/table-columns.js` (the same shape as `test_connection_watch.py`): the
file contains the `matchMedia` desktop guard, the `wiz-offline` guard, and emits
on `pointerup` rather than `pointermove`. Cheap, and it catches the two guards
being dropped in a refactor.

## 7. Browser pass — `/ui-validation`

1. Admin → Users: drag the **Username** divider wider; release; reload; the width held.
2. Double-click the same divider; the column auto-fits; reload; it stayed auto.
3. Admin → Schedule: widen **Players**; confirm the three-name commentator stacking from finding F4 is gone; screenshot before/after.
4. Kill the network (DevTools offline) and attempt a drag: the offline banner shows and no width is written; restore and confirm the pre-drag width.
5. At 390px: no resize cursor, no handles, cards unchanged.

---

## Acceptance

- Widths drag, persist, reset, and clamp on both adopted tables.
- No table without a stored width changes its layout in any way — diff the wave against `main` in a browser on a third table to prove it.
- `check_slot_context.py` and the rest of `scripts/guardrails.py` clean.
- Screenshots for finding F4's before/after in the PR.
