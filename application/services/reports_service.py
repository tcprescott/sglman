"""
Reports Service - Business Logic Layer

Handles report generation for match schedules and player activity.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import pytz

from application.repositories import MatchRepository
from models import Match


class ReportsService:
    """Service for generating tournament and match reports."""
    
    # Available forecast periods
    FORECAST_PERIODS = [
        'Thursday',
        'Friday',
        'Saturday',
        'Sunday',
        'Whole Event',
    ]
    
    # Default forecast period
    DEFAULT_FORECAST_PERIOD = 'Thursday'
    
    def __init__(self):
        self.match_repository = MatchRepository()
        self.eastern_tz = pytz.timezone('US/Eastern')
    
    def get_forecast_period_dates(self, period: str) -> Tuple[datetime, datetime, int]:
        """
        Get the start and end dates for a forecast period.
        
        Args:
            period: Forecast period ('Thursday', 'Friday', 'Saturday', 'Sunday', 'Whole Event')
            
        Returns:
            Tuple of (start_time, end_time, interval_minutes)
        """
        if period == 'Whole Event':
            # Fixed date range for the whole event with 60-minute intervals
            start_time = self.eastern_tz.localize(datetime(2025, 10, 24, 8, 0, 0))  # Oct 24, 2025 at 8AM ET
            end_time = self.eastern_tz.localize(datetime(2025, 10, 27, 22, 0, 0))  # Oct 27, 2025 at 10PM ET
            interval_min = 60
        else:
            datemap = {
                'Thursday': (datetime(2025, 10, 23, 0, 0, 0, tzinfo=self.eastern_tz), 
                           datetime(2025, 10, 24, 0, 0, 0, tzinfo=self.eastern_tz)),
                'Friday': (datetime(2025, 10, 24, 0, 0, 0, tzinfo=self.eastern_tz), 
                         datetime(2025, 10, 25, 0, 0, 0, tzinfo=self.eastern_tz)),
                'Saturday': (datetime(2025, 10, 25, 0, 0, 0, tzinfo=self.eastern_tz), 
                           datetime(2025, 10, 26, 0, 0, 0, tzinfo=self.eastern_tz)),
                'Sunday': (datetime(2025, 10, 26, 0, 0, 0, tzinfo=self.eastern_tz), 
                         datetime(2025, 10, 27, 0, 0, 0, tzinfo=self.eastern_tz)),
            }
            start_time, end_time = datemap.get(period, (datetime.now(self.eastern_tz), 
                                                        datetime.now(self.eastern_tz) + timedelta(hours=24)))
            interval_min = 15  # 15-minute intervals for single day
        
        return start_time, end_time, interval_min
    
    async def generate_player_activity_forecast(self, period: str) -> Dict:
        """
        Generate a forecast of active players over a time period.
        
        Args:
            period: Forecast period name
            
        Returns:
            Dict with intervals, player_counts, and metadata
        """
        start_time, end_time, interval_min = self.get_forecast_period_dates(period)
        
        # Calculate intervals
        intervals = []
        player_counts = []
        
        current_time = start_time
        while current_time <= end_time:
            intervals.append(current_time)
            active_players = await self._calculate_active_players_at_time(current_time)
            player_counts.append(active_players)
            current_time += timedelta(minutes=interval_min)
        
        return {
            'intervals': intervals,
            'player_counts': player_counts,
            'period': period,
            'start_time': start_time,
            'end_time': end_time,
            'interval_minutes': interval_min
        }
    
    async def _calculate_active_players_at_time(self, check_time: datetime) -> int:
        """
        Calculate the number of active players at a specific time.
        
        Args:
            check_time: The time to check for active matches
            
        Returns:
            Number of active players
        """
        # Convert check_time to US/Eastern timezone
        if check_time.tzinfo is None:
            check_time = self.eastern_tz.localize(check_time)
        else:
            check_time = check_time.astimezone(self.eastern_tz)
        
        # Get all matches without stream rooms (off-stream matches)
        matches = await Match.filter(stream_room=None).prefetch_related('tournament', 'players')
        
        active_players = 0
        
        for match in matches:
            # Skip matches with no scheduled time
            if not match.scheduled_at:
                continue
            
            # Determine the start time (seated_at or scheduled_at - 1 hour)
            if match.seated_at:
                if match.seated_at.tzinfo is None:
                    start_time = self.eastern_tz.localize(match.seated_at)
                else:
                    start_time = match.seated_at.astimezone(self.eastern_tz)
            else:
                # Assume players start 1 hour before scheduled time
                start_time = match.scheduled_at.replace(tzinfo=self.eastern_tz) - timedelta(hours=1)
            
            # Skip matches that haven't started yet
            if start_time > check_time:
                continue
            
            # Determine the end time (finished_at or calculated from tournament duration)
            if match.finished_at:
                if match.finished_at.tzinfo is None:
                    end_time = self.eastern_tz.localize(match.finished_at)
                else:
                    end_time = match.finished_at.astimezone(self.eastern_tz)
            else:
                # Use tournament average duration or default to 90 minutes
                if match.tournament and match.tournament.average_match_duration:
                    end_time = start_time + timedelta(minutes=match.tournament.average_match_duration)
                else:
                    end_time = start_time + timedelta(minutes=90)
            
            # Check if the match is active at the given time
            if start_time <= check_time <= end_time:
                active_players += len(match.players)
        
        return active_players
    
    def get_peak_times(self, intervals: List[datetime], counts: List[int], top_n: int = 5) -> List[Tuple[datetime, int]]:
        """
        Get the peak times from the forecast data.
        
        Args:
            intervals: List of time intervals
            counts: List of player counts corresponding to intervals
            top_n: Number of peaks to return
            
        Returns:
            List of (datetime, count) tuples for peak times
        """
        return sorted(zip(intervals, counts), key=lambda x: x[1], reverse=True)[:top_n]
