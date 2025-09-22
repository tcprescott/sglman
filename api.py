
from fastapi import APIRouter
from tortoise import Tortoise
from tortoise.contrib.pydantic import pydantic_model_creator
from models import (
    User, UserTeams, TestModel, Tournament, Match, MatchPlayers, TournamentPlayers,
    StreamRoom, Commentator, Tracker, Team, AuditLog, GeneratedSeeds
)

router = APIRouter()

# Utility: create Pydantic schemas for each model
User_Pydantic = pydantic_model_creator(User, name="User")
UserTeams_Pydantic = pydantic_model_creator(UserTeams, name="UserTeams")
TestModel_Pydantic = pydantic_model_creator(TestModel, name="TestModel")
Tournament_Pydantic = pydantic_model_creator(Tournament, name="Tournament")
Match_Pydantic = pydantic_model_creator(Match, name="Match")
MatchPlayers_Pydantic = pydantic_model_creator(MatchPlayers, name="MatchPlayers")
TournamentPlayers_Pydantic = pydantic_model_creator(TournamentPlayers, name="TournamentPlayers")
StreamRoom_Pydantic = pydantic_model_creator(StreamRoom, name="StreamRoom")
Commentator_Pydantic = pydantic_model_creator(Commentator, name="Commentator")
Tracker_Pydantic = pydantic_model_creator(Tracker, name="Tracker")
Team_Pydantic = pydantic_model_creator(Team, name="Team")
AuditLog_Pydantic = pydantic_model_creator(AuditLog, name="AuditLog")
GeneratedSeeds_Pydantic = pydantic_model_creator(GeneratedSeeds, name="GeneratedSeeds")


# Generic list/read endpoints for each model
@router.get("/users", response_model=list[User_Pydantic])
async def get_users():
    return await User_Pydantic.from_queryset(User.all())

@router.get("/users/{id}", response_model=User_Pydantic)
async def get_user(id: int):
    return await User_Pydantic.from_queryset_single(User.get(id=id))

@router.get("/userteams", response_model=list[UserTeams_Pydantic])
async def get_userteams():
    return await UserTeams_Pydantic.from_queryset(UserTeams.all())

@router.get("/userteams/{id}", response_model=UserTeams_Pydantic)
async def get_userteam(id: int):
    return await UserTeams_Pydantic.from_queryset_single(UserTeams.get(id=id))

@router.get("/testmodels", response_model=list[TestModel_Pydantic])
async def get_testmodels():
    return await TestModel_Pydantic.from_queryset(TestModel.all())

@router.get("/testmodels/{id}", response_model=TestModel_Pydantic)
async def get_testmodel(id: int):
    return await TestModel_Pydantic.from_queryset_single(TestModel.get(id=id))

@router.get("/tournaments", response_model=list[Tournament_Pydantic])
async def get_tournaments():
    return await Tournament_Pydantic.from_queryset(Tournament.all())

@router.get("/tournaments/{id}", response_model=Tournament_Pydantic)
async def get_tournament(id: int):
    return await Tournament_Pydantic.from_queryset_single(Tournament.get(id=id))

@router.get("/matches", response_model=list[Match_Pydantic])
async def get_matches():
    return await Match_Pydantic.from_queryset(Match.all())

@router.get("/matches/{id}", response_model=Match_Pydantic)
async def get_match(id: int):
    return await Match_Pydantic.from_queryset_single(Match.get(id=id))

@router.get("/matchplayers", response_model=list[MatchPlayers_Pydantic])
async def get_matchplayers():
    return await MatchPlayers_Pydantic.from_queryset(MatchPlayers.all())

@router.get("/matchplayers/{id}", response_model=MatchPlayers_Pydantic)
async def get_matchplayer(id: int):
    return await MatchPlayers_Pydantic.from_queryset_single(MatchPlayers.get(id=id))

@router.get("/tournamentplayers", response_model=list[TournamentPlayers_Pydantic])
async def get_tournamentplayers():
    return await TournamentPlayers_Pydantic.from_queryset(TournamentPlayers.all())

@router.get("/tournamentplayers/{id}", response_model=TournamentPlayers_Pydantic)
async def get_tournamentplayer(id: int):
    return await TournamentPlayers_Pydantic.from_queryset_single(TournamentPlayers.get(id=id))

@router.get("/streamrooms", response_model=list[StreamRoom_Pydantic])
async def get_streamrooms():
    return await StreamRoom_Pydantic.from_queryset(StreamRoom.all())

@router.get("/streamrooms/{id}", response_model=StreamRoom_Pydantic)
async def get_streamroom(id: int):
    return await StreamRoom_Pydantic.from_queryset_single(StreamRoom.get(id=id))

@router.get("/commentators", response_model=list[Commentator_Pydantic])
async def get_commentators():
    return await Commentator_Pydantic.from_queryset(Commentator.all())

@router.get("/commentators/{id}", response_model=Commentator_Pydantic)
async def get_commentator(id: int):
    return await Commentator_Pydantic.from_queryset_single(Commentator.get(id=id))

@router.get("/trackers", response_model=list[Tracker_Pydantic])
async def get_trackers():
    return await Tracker_Pydantic.from_queryset(Tracker.all())

@router.get("/trackers/{id}", response_model=Tracker_Pydantic)
async def get_tracker(id: int):
    return await Tracker_Pydantic.from_queryset_single(Tracker.get(id=id))

@router.get("/teams", response_model=list[Team_Pydantic])
async def get_teams():
    return await Team_Pydantic.from_queryset(Team.all())

@router.get("/teams/{id}", response_model=Team_Pydantic)
async def get_team(id: int):
    return await Team_Pydantic.from_queryset_single(Team.get(id=id))

@router.get("/auditlogs", response_model=list[AuditLog_Pydantic])
async def get_auditlogs():
    return await AuditLog_Pydantic.from_queryset(AuditLog.all())

@router.get("/auditlogs/{id}", response_model=AuditLog_Pydantic)
async def get_auditlog(id: int):
    return await AuditLog_Pydantic.from_queryset_single(AuditLog.get(id=id))

@router.get("/generatedseeds", response_model=list[GeneratedSeeds_Pydantic])
async def get_generatedseeds():
    return await GeneratedSeeds_Pydantic.from_queryset(GeneratedSeeds.all())

@router.get("/generatedseeds/{id}", response_model=GeneratedSeeds_Pydantic)
async def get_generatedseed(id: int):
    return await GeneratedSeeds_Pydantic.from_queryset_single(GeneratedSeeds.get(id=id))