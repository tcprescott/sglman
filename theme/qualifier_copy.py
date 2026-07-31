"""Shared explanatory copy for the async-qualifier surfaces.

Both the player's own qualifier page and the admin leaderboard show `Score` and
`Estimate`, and neither defined either. The wording lives here because the two
surfaces must not explain the same column differently — a reviewer answering
"what does Estimate mean?" should be reading the same sentence the competitor is.

Presentation-only: strings, no logic.
"""

__all__ = ['BOARD_EXPLAINER', 'SCORE_EXPLAINER']

# The two anchors a competitor reasons with (100 = par, 105 = the cap), not the
# formula. Par moves because it is the mean of the fastest approved runs on a
# seed, so a stranger's approval legitimately moves your score — which nothing on
# the page said before.
SCORE_EXPLAINER = (
    "Scores are relative to each seed's par — the average of the fastest approved runs "
    "on it. Approving someone else's run on a seed you played can move your score. "
    "100 is par; the cap is 105."
)

BOARD_EXPLAINER = (
    "Score is your realised total — unrun slots count zero. Estimate projects your unrun "
    "slots at your own average, so a partial entrant isn't understated. Ranking is by Score."
)
