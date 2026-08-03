"""Async-qualifier DM text.

Split out of :mod:`application.utils.discord_messages`, which had grown past the
800-line budget. The same rule applies here: no message text inline in service or
handler code. Sent by ``application/services/async_qualifier/``.
"""

def qualifier_run_reviewed_dm(
    qualifier_name: str,
    *,
    approved: bool,
    reason: str = '',
    qualifier_url: str = '',
) -> str:
    """The verdict on a submitted run, the reason behind it, and a way back.

    A rejection always carries a reason (the service refuses one without), and
    that reason is the whole message: told only "your run was rejected", a runner
    has nothing to act on and nothing to appeal. An approval keeps it short and
    includes the reviewer's note only when one was left.
    """
    verb = 'approved' if approved else 'rejected'
    blocks = [f"Your **{qualifier_name}** qualifier run was {verb}."]
    if reason:
        blocks.append(f"Reason: {reason}")
    if qualifier_url:
        blocks.append(f"[Your runs and the leaderboard]({qualifier_url})")
    return "\n\n".join(blocks)


def qualifier_run_expiring_dm(
    qualifier_name: str,
    *,
    deadline_display: str,
    qualifier_url: str = '',
) -> str:
    """One warning that an in-progress run is about to be forfeited automatically.

    The runner drew a seed and has not submitted. Usually they finished and
    forgot; occasionally they abandoned it. Either way the only thing that
    salvages the attempt is submitting or forfeiting *before* the deadline, so the
    message leads with the deadline and says what happens if it passes.
    """
    blocks = [
        f"Your **{qualifier_name}** run is still open, and will be forfeited "
        f"automatically {deadline_display}.",
        "Submit your finish time before then to have it count — or forfeit it "
        "yourself if you are not going to finish.",
    ]
    if qualifier_url:
        blocks.append(f"[Submit or forfeit your run]({qualifier_url})")
    return "\n\n".join(blocks)


def qualifier_run_expired_dm(
    qualifier_name: str,
    *,
    hours: int,
    qualifier_url: str = '',
) -> str:
    """A run was forfeited automatically after sitting open past its limit.

    Names the limit rather than just the outcome: the runner needs to know this
    was a time rule and not a decision anyone made about them, and an organiser
    can grant a reattempt if it was wrong.
    """
    blocks = [
        f"Your **{qualifier_name}** run was open for more than {hours} hours "
        f"without a finish time, so it has been forfeited.",
        "If that is not right, ask an organiser — they can grant you another "
        "attempt without spending your own.",
    ]
    if qualifier_url:
        blocks.append(f"[Your runs and the leaderboard]({qualifier_url})")
    return "\n\n".join(blocks)


def qualifier_reattempt_granted_dm(
    qualifier_name: str,
    pool_name: str,
    *,
    reason: str = '',
    qualifier_url: str = '',
) -> str:
    """A reviewer voided a run on the runner's behalf, freeing its pool slot.

    Sent because the runner's own pool availability just changed under them
    without their doing anything — the one state change on this surface they
    could not have initiated.
    """
    where = f" in **{pool_name}**" if pool_name else ''
    blocks = [f"A reviewer granted you another attempt{where} in **{qualifier_name}**."]
    if reason:
        blocks.append(f"Reason: {reason}")
    blocks.append("Your previous run no longer counts, and the pool slot is free again.")
    if qualifier_url:
        blocks.append(f"[Start your next run]({qualifier_url})")
    return "\n\n".join(blocks)
