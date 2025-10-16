from pyz3r import ALTTPR
import yaml

async def generate_alttpr():
    with open("application/randomizers/presets/alttpr/sglive2025.yaml", "r") as f:
        preset = yaml.safe_load(f)

    seed = await ALTTPR.generate(
        settings=preset['settings'],
    )
    return seed