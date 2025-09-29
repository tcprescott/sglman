
from datetime import timedelta, datetime
from typing import Optional
from models import Match, MatchPlayers
from tortoise.expressions import Q
from nicegui import ui

def generate_time_intervals(start_time, end_time, interval_minutes=5):
    """
    Helper to generate a list of datetime objects from start_time to end_time at interval_minutes.
    """
    times = []
    current_time = start_time
    while current_time <= end_time:
        times.append(current_time)
        current_time += timedelta(minutes=interval_minutes)
    return times

def _predict_match_times(match, now):
    """
    Returns (seated_at, finished_at, used_prediction) for a match, using future prediction logic.
    """
    seated_at = match.seated_at
    finished_at = match.finished_at
    used_prediction = False
    if not seated_at:
        used_prediction = True
        if match.scheduled_at:
            seated_at = max(match.scheduled_at, now)
        else:
            seated_at = now
    if not finished_at:
        avg_duration = None
        if hasattr(match, 'tournament') and match.tournament and getattr(match.tournament, 'average_match_duration', None):
            avg_duration = match.tournament.average_match_duration
        if avg_duration:
            used_prediction = True
            finished_at = seated_at + timedelta(minutes=avg_duration)
    return seated_at, finished_at, used_prediction

def _get_active_matches(matches, current_time, now, future_prediction):
    """
    Returns a list of matches active at current_time, and whether any used prediction.
    """
    active_matches = []
    used_prediction = False
    for m in matches:
        if future_prediction:
            seated_at, finished_at, pred = _predict_match_times(m, now)
        else:
            seated_at, finished_at, pred = m.seated_at, m.finished_at, False
        if pred:
            used_prediction = True
        if seated_at and seated_at <= current_time and (finished_at is None or finished_at > current_time):
            active_matches.append((m, pred))
    return active_matches, used_prediction


def _count_players_per_tournament(active_matches, players):
    """
    Returns a dict: tournament_id -> player count for active matches.
    """
    tournament_counts = {}
    match_objs = [m for m, _ in active_matches]
    for m in match_objs:
        tid = m.tournament_id
        if tid not in tournament_counts:
            tournament_counts[tid] = 0
    for p in players:
        match = next((m for m in match_objs if m.id == p.match_id), None)
        if match:
            tid = match.tournament_id
            tournament_counts[tid] += 1
    return tournament_counts

def _count_matches_per_tournament(active_matches):
    """
    Returns a dict: tournament_id -> match count for active matches.
    """
    tournament_counts = {}
    match_objs = [m for m, _ in active_matches]
    for m in match_objs:
        tid = m.tournament_id
        if tid not in tournament_counts:
            tournament_counts[tid] = 0
        tournament_counts[tid] += 1
    return tournament_counts

async def count_active_race_players_over_range(time_intervals: list[datetime], tournament_id: Optional[int]=None, exclude_stage: Optional[bool]=False, future_prediction: Optional[bool]=False):
    """
    Returns a list of active player counts for each time in time_intervals.
    time_intervals: list of datetime objects.
    tournament_id: if provided, filters to that tournament only.
    exclude_stage: if True, excludes matches with a stream_room (stage) assigned.
    future_prediction: if True, predicts future active matches based on scheduled_at and average_match_duration.
    Returns a list of dicts as before.
    Optimized: fetches all relevant matches and players up front, then computes counts in memory.
    """
    if not time_intervals or not isinstance(time_intervals, list):
        raise ValueError('time_intervals must be provided as a list of datetime objects')
    start_time = min(time_intervals)
    end_time = max(time_intervals)
    # Build match filter
    match_filter = Q(seated_at__isnull=False)
    if tournament_id is not None:
        match_filter &= Q(tournament_id=tournament_id)
    if exclude_stage:
        match_filter &= Q(stream_room_id__isnull=True)
    match_filter &= Q(seated_at__lte=end_time) & (Q(finished_at__isnull=True) | Q(finished_at__gte=start_time))
    matches = await Match.filter(match_filter).all()
    if not matches:
        return []
    match_ids = [m.id for m in matches]
    players = await MatchPlayers.filter(match_id__in=match_ids).all()
    results = []
    now = datetime.utcnow()
    for current_time in time_intervals:
        active_matches, used_prediction = _get_active_matches(matches, current_time, now, future_prediction)
        match_objs = [m for m, _ in active_matches]
        active_match_ids = [m.id for m in match_objs]
        player_count = sum(1 for p in players if p.match_id in active_match_ids)
        match_count = len(match_objs)
        has_unfinished = any(m.finished_at is None or m.finished_at > max(time_intervals) for m, _ in active_matches)
        result = {
            'timestamp': current_time,
            'player_count': player_count,
            'match_count': match_count,
            'has_unfinished': has_unfinished,
            'used_prediction': used_prediction
        }
        if tournament_id is None:
            tournament_player_counts = _count_players_per_tournament(active_matches, players)
            tournament_match_counts = _count_matches_per_tournament(active_matches)
            result['count_per_tournament'] = tournament_player_counts
            result['count_matches_per_tournament'] = tournament_match_counts
        results.append(result)
    return results

async def count_active_race_players(tournament_id=None, exclude_stage=False):
    """
    Returns the number of players currently involved in a race where seated_at is set, but finished_at is not.
    If tournament_id is provided, only counts players in that tournament.
    If exclude_stage is True, excludes races where stream_room (stage) is set.
    """
    match_filter = Q(seated_at__isnull=False) & Q(finished_at__isnull=True)
    if tournament_id is not None:
        match_filter &= Q(tournament_id=tournament_id)
    if exclude_stage:
        match_filter &= Q(stream_room_id__isnull=True)
    active_matches = await Match.filter(match_filter).all()
    if not active_matches:
        return 0
    match_ids = [m.id for m in active_matches]
    return await MatchPlayers.filter(match_id__in=match_ids).count()

# Global cache dict: key -> (result, cache_time)
_cache = {}

async def get_cached_active_race_players_over_range(time_intervals, tournament_id=None, exclude_stage=False, future_prediction=False, ttl_seconds=300):
    cache_key = (
        tuple(time_intervals),
        tournament_id,
        exclude_stage,
        future_prediction
    )
    now = datetime.utcnow()
    # Check cache
    if cache_key in _cache:
        result, cache_time = _cache[cache_key]
        if (now - cache_time).total_seconds() < ttl_seconds:
            return result
    # Compute and cache
    result = await count_active_race_players_over_range(
        time_intervals, tournament_id, exclude_stage, future_prediction
    )
    _cache[cache_key] = (result, now)
    return result