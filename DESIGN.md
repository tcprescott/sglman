# This application requires the following

1. Pull a copy of the SG schedule for all events covered under SGL.  This can be stored in the database.
2. Each match in the schedule has one of the following states: NEW, CHECKED_IN, AWAITING_SEAT, SEATED, IN_PROGRESS, COMPLETE
    1. NEW = Match was scheduled on SG's system and was imported into SGLiveMan
    2. CHECKED_IN = Match participants have both initially visited the admin desk and checked in with the admin
    3. AWAITING_SEAT = There is no available seating and the match has been placed on a waitlist.
    4. SEATED = Runners have been given a seed (if applicable to tournament) and have been given seats in the tournament room (or are on stage)
    5. IN_PROGRESS = Race is in progress and results are still pending
    6. COMPLETE = Race has been complete and results have been recorded.  No further action is required.
3. The following pages should be present:
    1. A public page that contains the list of upcoming races, their status, and seed information.  This can be a table.
    2. A manager page, protected by authentication, that contains upcoming races and a way to advance the workflow, including rolling the seed.
4. A simple API so tsigma can retrieve data from this system if required.  tsigma should be contacted to identify these requirements

# Challenges
1. ETL process for importing matches needs to be able to figure out the players.  The data is NOT normalized in SG's database so that's going to be an issue.