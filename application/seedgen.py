# we will need random seed generation for
# 1. ALTTPR
# 2. FF1R
# 3. Z1R
# 4. MMR
# 5. OOTR

async def generate_alttpr() -> None:
    return "https://example.com/alttpr-seed-url"

async def generate_ff1r() -> None:
    return "https://example.com/ff1r-seed-url"

async def generate_z1r() -> None:
    return "https://example.com/z1r-seed-url"

async def generate_smmr() -> None:
    return "https://example.com/smmr-seed-url"

async def generate_mmr() -> None:
    return "https://example.com/mmr-seed-url"

async def generate_ootr() -> None:
    return "https://example.com/ootr-seed-url"

async def generate_test() -> None:
    return "https://example.com/test-seed-url"

# map of randomizers to their generation functions
RANDOMIZERS = {
    'alttpr': generate_alttpr,
    'ff1r': generate_ff1r,
    'z1r': generate_z1r,
    'smmr': generate_smmr,
    'mmr': generate_mmr,
    'ootr': generate_ootr,
    'test': generate_test,
}