"""Feature-flag registry — the catalog of per-tenant feature flags.

A feature flag exists only when a feature is deliberately gated behind one; this
is **not** a per-feature switch for everything the app does. Flags default OFF
and are governed two-tier:

* a **super-admin** makes a flag *available* to a tenant on ``/platform``; then
* that tenant's **STAFF** *enable* it for their community (Admin → Features).

Effective state = ``available AND enabled`` (see ``FeatureFlagService``).

This module is pure metadata — a peer of ``application/events`` and
``application/tenant_context`` (import-safe from every layer, including
repositories and pages). The stable enum keys live in
:class:`models.enums.FeatureFlag`; the human copy and grouping live here so the
UI and the migration/seed have one source of truth.

**Adding a flag:** add a member to :class:`~models.enums.FeatureFlag` and a
:class:`FeatureFlagSpec` here. Mark ``established=True`` only for a feature that
is *already in live use* when you gate it — the migration backfills such flags
as available+enabled for existing tenants so gating them does not make them
vanish. New/unreleased features leave it False and ship dark.
"""

from dataclasses import dataclass
from typing import Dict, List

from models import FeatureFlag


@dataclass(frozen=True)
class FeatureFlagSpec:
    flag: FeatureFlag
    label: str
    description: str
    category: str
    established: bool = False


# Declaration order is preserved (dict is ordered) and drives UI ordering.
FEATURE_FLAG_REGISTRY: Dict[FeatureFlag, FeatureFlagSpec] = {
    spec.flag: spec
    for spec in (
        FeatureFlagSpec(
            FeatureFlag.ASYNC_QUALIFIERS,
            'Async Qualifiers',
            'Self-paced permalink-pool qualifiers with their own leaderboard, '
            'run review, and optional live races.',
            'Online tournaments',
        ),
        FeatureFlagSpec(
            FeatureFlag.RACETIME_ROOMS,
            'Racetime Rooms',
            'Automated racetime.gg race rooms driven from scheduled matches '
            '(open, attach seed, finish, record results).',
            'Online tournaments',
        ),
        FeatureFlagSpec(
            FeatureFlag.SPEEDGAMING_ETL,
            'SpeedGaming Schedule Sync',
            "One-way import of the SpeedGaming schedule into this community's "
            'matches.',
            'Online tournaments',
        ),
        FeatureFlagSpec(
            FeatureFlag.DK64_RANDOMIZER,
            'DK64 Randomizer',
            'Roll Donkey Kong 64 Randomizer seeds via the api.dk64rando.com '
            'service. Requires an API key issued by the DK64 Randomizer team; '
            'availability records that this community is authorized to use it '
            'under that key\'s usage terms.',
            'Online tournaments',
        ),
        FeatureFlagSpec(
            FeatureFlag.CHALLONGE,
            'Challonge Integration',
            'Connect a Challonge account to mirror brackets, schedule from '
            'bracket matches, and push results.',
            'Community',
            established=True,
        ),
        FeatureFlagSpec(
            FeatureFlag.EQUIPMENT,
            'Equipment Lending',
            'Track lending assets with checkout/check-in, loan history, and QR '
            'codes.',
            'Community',
            established=True,
        ),
        FeatureFlagSpec(
            FeatureFlag.VOLUNTEERS,
            'Volunteer Scheduling',
            'Volunteer opt-in, positions, shifts, availability, the '
            'auto-scheduler, and reminders.',
            'Community',
            established=True,
        ),
        FeatureFlagSpec(
            FeatureFlag.TRIFORCE_TEXTS,
            'Triforce Texts',
            'Player-submitted triforce texts with admin moderation '
            '(ALTTPR-specific).',
            'Community',
            established=True,
        ),
        FeatureFlagSpec(
            FeatureFlag.BRACKETS,
            'Native Brackets',
            'Generate and run tournament brackets natively (single/double '
            'elimination, Swiss, round robin, and multi-stage chains) without '
            'the Challonge API.',
            'Online tournaments',
        ),
    )
}


def all_specs() -> List[FeatureFlagSpec]:
    """Every known flag spec, in declaration order."""
    return list(FEATURE_FLAG_REGISTRY.values())


def spec_for(flag: FeatureFlag) -> FeatureFlagSpec:
    return FEATURE_FLAG_REGISTRY[flag]


def established_flags() -> List[FeatureFlag]:
    """Flags for features already in live use — backfilled on existing tenants."""
    return [spec.flag for spec in all_specs() if spec.established]
