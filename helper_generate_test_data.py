# helper_generate_test_data.py
"""
Helper script to generate test data for all models using Tortoise ORM.
Run this script after initializing Tortoise with your database.
"""
import argparse
import os
from random import randint, choice
from datetime import datetime, timedelta
from faker import Faker
from tortoise import Tortoise, run_async
from models import User, Tournament, StreamRoom, Match, MatchConfirmations, Commentator, Tracker, AuditLog, TestModel, Permissions

fake = Faker()

async def generate_test_data(
    num_users=3,
    num_tournaments=2,
    num_streamrooms=2,
    num_matches=2,
    num_confirmations=2,
    num_commentators=1,
    num_trackers=1,
    num_auditlogs=2,
    num_testmodels=2
):
    # Users
    users = []
    for i in range(num_users):
        user = await User.create(
            discord_id=randint(100000000000000000, 999999999999999999),
            access_token=fake.sha1(),
            username=fake.user_name(),
            is_active=True,
            permission=0
        )
        users.append(user)

    # Tournaments
    tournaments = []
    for i in range(num_tournaments):
        tournament = await Tournament.create(name=fake.company())
        tournaments.append(tournament)

    # StreamRooms
    streamrooms = []
    for i in range(num_streamrooms):
        streamroom = await StreamRoom.create(
            name=fake.word().capitalize() + ' Room',
            stream_url=f'https://twitch.tv/{fake.user_name()}',
            is_active=True
        )
        streamrooms.append(streamroom)

    # Matches
    matches = []
    for i in range(num_matches):
        match = await Match.create(
            tournament=choice(tournaments),
            stream_room=choice(streamrooms),
            player_count=randint(2,4),
            player1=choice(users),
            player2=choice(users),
            player3=choice(users) if num_users > 2 else None,
            player4=choice(users) if num_users > 3 else None,
            score1=randint(0,5),
            score2=randint(0,5),
            scheduled_at=(datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d %H:%M:%S'),
        )
        matches.append(match)

    # MatchConfirmations
    for i in range(num_confirmations):
        await MatchConfirmations.create(
            match=choice(matches),
            user=choice(users),
            confirmed=choice([True, False])
        )

    # Commentators
    for i in range(num_commentators):
        await Commentator.create(
            user=choice(users),
            match=choice(matches),
            approved=choice([True, False]),
            approved_by=choice(users)
        )

    # Trackers
    for i in range(num_trackers):
        await Tracker.create(
            user=choice(users),
            match=choice(matches),
            approved=choice([True, False]),
            approved_by=choice(users)
        )

    # AuditLogs
    for i in range(num_auditlogs):
        await AuditLog.create(
            user=choice(users),
            action=fake.sentence(nb_words=3),
            details=fake.text(max_nb_chars=50)
        )

    # TestModel
    for i in range(num_testmodels):
        await TestModel.create(
            name=fake.word().capitalize(),
            description=fake.sentence(),
            value=randint(1,100),
            somethingelse=fake.word().capitalize()
        )

def parse_args():
    parser = argparse.ArgumentParser(description='Generate test data for models.')
    parser.add_argument('--users', type=int, default=3)
    parser.add_argument('--tournaments', type=int, default=2)
    parser.add_argument('--streamrooms', type=int, default=2)
    parser.add_argument('--matches', type=int, default=2)
    parser.add_argument('--confirmations', type=int, default=2)
    parser.add_argument('--commentators', type=int, default=1)
    parser.add_argument('--trackers', type=int, default=1)
    parser.add_argument('--auditlogs', type=int, default=2)
    parser.add_argument('--testmodels', type=int, default=2)
    return parser.parse_args()

async def main():
    args = parse_args()
    from dotenv import load_dotenv
    load_dotenv()
    username = os.environ.get("DB_USERNAME", 'sglman')
    password = os.environ.get("DB_PASSWORD", '283u21893812j3')
    host = os.environ.get("DB_HOST", 'localhost')
    port = os.environ.get("DB_PORT", '3306')
    dbname = os.environ.get("DB_NAME", 'sglman')
    await Tortoise.init(
        db_url=f'mysql://{username}:{password}@{host}:{port}/{dbname}',
        modules={'models': ['models']}
    )
    # await Tortoise.generate_schemas()
    await generate_test_data(
        num_users=args.users,
        num_tournaments=args.tournaments,
        num_streamrooms=args.streamrooms,
        num_matches=args.matches,
        num_confirmations=args.confirmations,
        num_commentators=args.commentators,
        num_trackers=args.trackers,
        num_auditlogs=args.auditlogs,
        num_testmodels=args.testmodels
    )
    await Tortoise.close_connections()

if __name__ == '__main__':
    run_async(main())
