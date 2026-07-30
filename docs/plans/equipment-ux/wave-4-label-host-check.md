# Wave 4 — A label batch can't be printed against the wrong host unnoticed (F6)

**Read [README.md](README.md) first.** This is the smallest and least valuable
wave; stopping after wave 3 is a legitimate outcome.

**Goal:** a sheet of QR labels printed against a stale `BASE_URL` is caught at the
printer, not at the venue by someone holding a phone and a cable.

Presentation, plus one pure helper. No service, no model.

---

## The gap

Both the asset page and the label sheet encode a **tenant-qualified absolute** link
(`tenant_url(tenant, f'/equipment/{id}')` → the tenant's custom domain when set,
else `{BASE_URL}/t/<slug>/…`). The asset page prints that link as a caption under
the QR, so a misconfiguration is *visible* if someone reads it — the audit measured
`http://localhost:8000/t/default/equipment/3` in dev. Nothing compares it to the
host the operator is actually browsing, and the label sheet shows no link at all.
Thirty labels later, the mismatch surfaces as an unscannable sticker.

Note the subtlety that makes a naïve check wrong: on a custom-domain tenant the
encoded host is *supposed* to differ from `BASE_URL`. The comparison must be
against the tenant's **canonical** base
(`tenant_base_url(tenant)` in
[`application/utils/tenant_urls.py`](../../../application/utils/tenant_urls.py)),
and the warning fires only when that canonical host is not the host in the address
bar.

---

## Task 4.1 — A pure host-mismatch check

**Where:** [`application/utils/tenant_urls.py`](../../../application/utils/tenant_urls.py)
(or `hostname.py` if it fits better beside `scheme_for_host`).

Add a pure function — `encoded_host_mismatch(canonical_url, browsing_host)` →
`str | None`, returning the canonical host when it differs from the browsing host
and `None` otherwise. Pure: no NiceGUI, no request, no DB, so it unit-tests in
isolation like its neighbours.

Normalize before comparing: case, a default port (`:80` / `:443`), and a trailing
dot. `localhost:8000` vs `localhost:8000` must match; `localhost:8000` vs
`wizzrobe.example` must not.

**Tests:** [`tests/tenancy/test_tenant_urls.py`](../../../tests/tenancy/test_tenant_urls.py)
— match, mismatch, port-normalization, case-insensitivity, and empty/None inputs
returning `None` (a missing host must never produce a spurious warning).

---

## Task 4.2 — Warn on the label sheet, before printing

**Where:** [`pages/equipment_labels.py`](../../../pages/equipment_labels.py) — the
screen-only toolbar (currently lines 178-193).

The browsing host comes from the page's request
(`context.client.request.headers.get('host')`); the canonical one from the tenant
the page already resolved. On a mismatch, render a `no-print` warning line beside
the existing Avery instruction — same treatment (`text-warning`, `text-caption`):

> These labels encode **{canonical_host}** — you are browsing **{browsing_host}**.
> Check `BASE_URL` before printing.

Requirements:

- `no-print`, so it never lands on a sticker.
- Placed **above** the Print button in reading order — a warning below the action is
  a warning after the fact.
- Never render when the hosts match; this page must stay quiet in the normal case.
- Do not block printing. The operator may have a good reason (printing at home for
  a venue on another host); the fix is information, not a gate.

While here, show the encoded link (or at least its host) once in the toolbar, the
way the asset page shows it under the QR — the sheet is currently the only surface
that encodes links without displaying any.

**Tests:** [`tests/test_equipment_labels_page.py`](../../../tests/test_equipment_labels_page.py)
— the file already unit-tests this page's pure helpers, so test the helper there
too if it is not covered by 4.1; the rendered warning is proved by task 4.4.

---

## Task 4.3 — Same warning on the asset page

**Where:** [`pages/equipment.py`](../../../pages/equipment.py) — beside the existing
`ui.label(asset_link)` caption under the QR (line 99).

Manager-only (`can_manage`) — a volunteer scanning a label cannot act on a
`BASE_URL` misconfiguration and does not need the noise. Same copy, shortened to
fit the caption column.

---

## Task 4.4 — Verify with a deliberately wrong host

Run the app with `BASE_URL` pointing somewhere it is not served from
(`BASE_URL=https://wrong.example ./start.sh dev`), then:

| Surface | Expected |
|---|---|
| `/t/default/equipment/qr-labels?ids=1,2,3` as manager | warning above Print, naming both hosts; not present in the print preview |
| `/t/default/equipment/1` as manager | short warning under the QR caption |
| the same page as a volunteer | no warning |
| both with `BASE_URL` correct | no warning anywhere |

Screenshot the sheet at 1500 px and the asset page at 390×844, and confirm the
warning is absent from the browser's print preview.

**Docs:** the `/equipment/qr-labels` and `/equipment/{asset_id}` rows in
[`docs/reference/frontend.md`](../../reference/frontend.md), and the `BASE_URL` row
in [`docs/deployment.md`](../../deployment.md)'s environment table — it is the
variable this whole finding is about, and the label sheet is now the surface that
tells you it is wrong.
