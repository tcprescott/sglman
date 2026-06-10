import random

COASTER_FACTS = [
    # Speed & records
    "The world's fastest roller coaster hits 149.1 mph — Formula Rossa, Abu Dhabi.",
    "Formula Rossa goes from 0 to 149 mph in just 4.9 seconds.",
    "Kingda Ka in New Jersey stands 456 feet tall — taller than the Statue of Liberty.",
    "Steel Dragon 2000 in Japan is the longest roller coaster in the world at 8,133 feet.",
    "The Smiler at Alton Towers holds the record for most inversions: 14 loops.",

    # History
    "The first looping coaster opened at Coney Island in 1895. It closed after one day.",
    "'Roller coaster' likely derives from 18th-century Russian ice slides called Gorka.",
    "The oldest operating roller coaster, Leap-the-Dips in Pennsylvania, was built in 1902.",
    "The world's first roller coaster patent was granted to LaMarcus Adna Thompson in 1885.",
    "The Coney Island Cyclone, built in 1927, was declared a New York City landmark in 1988.",
    "The first modern steel coaster was the Matterhorn Bobsleds at Disneyland, opening in 1959.",

    # Physics & engineering
    "Roller coasters don't have engines — after the lift hill, they run entirely on gravity.",
    "At the top of a loop, riders briefly experience 0g — the same as free fall.",
    "Wooden coasters lose roughly 1/16 inch of height per year from wood settlement.",
    "Magnetic (eddy current) brakes on modern coasters require no physical contact to slow the train.",

    # Culture & trivia
    "Enthusiasts who ride every seat on every train call it 'riding all positions.'",
    "The world record for most coasters ridden in 24 hours is 74, set in 2013.",
    "El Toro at Six Flags Great Adventure has the steepest drop on any wooden coaster: 76 degrees.",
    "Son of Beast at Kings Island was the world's only wooden looping coaster — the loop was later removed.",
    "The term 'airtime' refers to the sensation of weightlessness when a coaster crests a hill quickly.",
]

CAT_FACTS = [
    # Biology
    "A group of cats is called a clowder.",
    "Cats have 32 muscles in each ear and can rotate them 180 degrees.",
    "Cats cannot taste sweetness — they lack the gene for sweet receptors.",
    "A cat's purr vibrates at 25–150 Hz, a frequency shown to aid bone healing.",
    "A cat's nose print is as unique as a human fingerprint.",
    "Cats have a third eyelid (nictitating membrane) rarely visible in healthy cats.",
    "A cat's field of vision is about 200 degrees — wider than a human's 180.",
    "Cats have a free-floating clavicle, letting them squeeze through any gap their head fits through.",
    "A cat's heart beats 140–220 bpm — roughly twice as fast as a human's.",
    "The technical term for a cat's hairball is a 'trichobezoar.'",
    "Domestic cats share 95.6% of their DNA with tigers.",
    "Cats can make around 100 distinct vocalizations; dogs manage about 10.",

    # Behavior
    "Cats sleep 12–16 hours a day, among the sleepiest mammals on Earth.",
    "The world's oldest cat, Creme Puff, lived to be 38 years and 3 days old.",
    "A cat's 'slow blink' signals trust and affection — blinking back is recognized as friendly.",
    "When cats head-butt you they're marking you with scent glands on their cheeks and forehead.",
    "A cat can jump up to six times its own body length in a single leap.",

    # History & culture
    "The first cat in space was Félicette, a French cat launched in 1963 — she survived.",
    "Ancient Egyptians worshipped the cat goddess Bastet; harming a cat was punishable by death.",
    "Sir Isaac Newton is credited with inventing the cat flap after his cat kept interrupting his light experiments.",
]


BALATRO_FACTS = [
    # Development
    "Balatro was made almost entirely by a single anonymous developer who goes by LocalThunk.",
    "LocalThunk spent more than two years building Balatro as a hobby project.",
    "LocalThunk has said he isn't much of a poker player — the game just uses the deck.",
    "Balatro was inspired by the deckbuilder Luck Be a Landlord and a poker-based mini-game.",
    "The game was published by Playstack and released on February 20, 2024.",

    # Design & details
    "Balatro is a roguelike deckbuilder built around scoring poker hands, not playing real poker.",
    "Its grinning joker mascot is named Jimbo.",
    "The name 'Balatro' comes from a Latin word for a jester, babbler, or buffoon.",
    "Every run is powered by Jokers — stacking their effects is the heart of the game.",
    "Balatro uses a deliberately lo-fi, CRT-style visual filter for its retro look.",

    # Reception & impact
    "Balatro was nominated for Game of the Year at The Game Awards 2024.",
    "It swept multiple BAFTA Games Awards in 2025, including Best Game.",
    "Balatro sold over a million copies within its first two weeks.",
    "By the end of 2024 Balatro had sold more than five million copies.",
    "Balatro briefly received an adults-only rating in Europe over its card-and-chip imagery, which was later overturned.",
    "Despite using poker chips, Balatro involves no real money or gambling whatsoever.",
    "Balatro launched on PC and consoles before arriving on mobile, where it topped paid-app charts.",
]


DIABLO_FACTS = [
    # Series & lore
    "The Diablo series began in 1996 and is set in the dark fantasy world of Sanctuary.",
    "Diablo, the 'Lord of Terror,' is one of the three Prime Evils alongside Mephisto and Baal.",
    "Sanctuary was created by the renegade angel Inarius and the demon Lilith.",
    "Nephalem — the powerful offspring of angels and demons — are the ancestors of humanity.",

    # Diablo II
    "Diablo II launched on June 29, 2000 and was one of the fastest-selling PC games of its era.",
    "Diablo II's base classes were the Amazon, Necromancer, Barbarian, Sorceress, and Paladin.",
    "The Lord of Destruction expansion (2001) added Act V plus the Assassin and Druid classes.",
    "The Horadric Cube let players transmute items and combine runes into powerful runewords.",
    "Diablo II's Secret Cow Level is reached using Wirt's Leg and a Tome of Town Portal in the Cube.",
    "Diablo II: Resurrected, a full remaster, arrived in September 2021.",

    # Diablo IV
    "Diablo IV released on June 6, 2023 as the series' first fully open-world entry.",
    "Its main antagonist is Lilith, the 'Daughter of Hatred' and daughter of Mephisto.",
    "Diablo IV launched with the Barbarian, Sorcerer, Druid, Rogue, and Necromancer classes.",
    "Diablo IV grossed $666 million in its first five days — a figure Blizzard happily leaned into.",
    "It was the fastest-selling game in Blizzard's history.",
    "The Vessel of Hatred expansion (2024) added the Spiritborn class and the jungle region of Nahantu.",
]


WOW_FACTS = [
    # History
    "World of Warcraft launched on November 23, 2004 and is set on the world of Azeroth.",
    "At its 2010 peak, WoW had more than 12 million subscribers.",
    "WoW holds a Guinness World Record as the most popular subscription-based MMORPG.",
    "WoW's original level cap was 60.",
    "WoW Classic, a re-release of the original 2004 game, launched in 2019.",

    # Expansions & story
    "Wrath of the Lich King (2008) pitted players against Arthas Menethil, the Lich King.",
    "The War Within (2024) kicked off WoW's multi-expansion Worldsoul Saga.",
    "WoW's expansions include The Burning Crusade, Cataclysm, Legion, Shadowlands, and Dragonflight.",
    "The game is split between two warring factions: the Alliance and the Horde.",
    "Major capital cities include the Alliance's Ironforge and the Horde's Orgrimmar.",

    # Culture & trivia
    "The 2005 'Corrupted Blood' plague accidentally escaped its raid and was later studied by epidemiologists.",
    "The 'Leeroy Jenkins' battle cry became an internet legend after a 2005 WoW guild video.",
    "Murlocs — the burbling fish-people — are among WoW's most iconic creatures.",
    "Blizzard's annual BlizzCon convention grew largely out of WoW's popularity.",
    "Azeroth's two original continents at launch were the Eastern Kingdoms and Kalimdor.",
    "WoW was developed and published by Blizzard Entertainment.",
]


HAMILTON_FACTS = [
    # Creation
    "Hamilton's music, lyrics, and book were all written by Lin-Manuel Miranda.",
    "The musical is based on Ron Chernow's 2004 biography of Alexander Hamilton.",
    "Miranda debuted an early version at a 2009 White House poetry event as 'The Hamilton Mixtape.'",
    "Hamilton blends hip-hop, R&B, pop, and soul with traditional show tunes.",
    "The show deliberately casts actors of color as America's Founding Fathers.",

    # Production
    "Hamilton premiered Off-Broadway at The Public Theater in early 2015.",
    "It opened on Broadway at the Richard Rodgers Theatre in August 2015.",
    "The original cast featured Leslie Odom Jr. as Aaron Burr and Daveed Diggs as Lafayette and Jefferson.",
    "Phillipa Soo, Renée Elise Goldsberry, and Jasmine Cephas Jones originated the three Schuyler sisters.",
    "A filmed version of the original cast premiered on Disney+ in July 2020.",

    # Awards & legacy
    "Hamilton received a record 16 Tony nominations in 2016 and won 11.",
    "Hamilton won the 2016 Pulitzer Prize for Drama.",
    "Leslie Odom Jr. won the Tony for Best Actor in a Musical for playing Aaron Burr.",
    "The original cast recording won the Grammy for Best Musical Theater Album.",
]


CLOVERPIT_TIPS = [
    "Cloverpit is a slot-machine roguelike from indie studio Panik Arcade, released in 2025.",
    "In Cloverpit you're trapped in a cramped room, feeding a slot machine to pay off escalating debt.",
    "Charms modify Cloverpit's slot machine — stacking the right ones is how you chase a saving jackpot.",
    "Miss one of Cloverpit's debt deadlines and the run is over.",
    "Cloverpit wraps its gambling loop in a tense, claustrophobic horror atmosphere.",
    "The clovers and lucky symbols of Cloverpit play into its desperate escape-the-pit theme.",
]


def random_fact() -> str:
    return random.choice(
        COASTER_FACTS + CAT_FACTS + BALATRO_FACTS
        + DIABLO_FACTS + WOW_FACTS + HAMILTON_FACTS + CLOVERPIT_TIPS
    )
