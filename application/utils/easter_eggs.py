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


def random_fact() -> str:
    return random.choice(COASTER_FACTS + CAT_FACTS)
