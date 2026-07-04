#!/usr/bin/env python3
"""Generate the VAPID keypair that enables Device Notifications (web push).

Usage:
    poetry run python scripts/generate_vapid_keys.py

Put the printed values in your environment (.env). The private key must stay
secret and must not change once users have subscribed — rotating it silently
invalidates every existing subscription.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from application.utils.web_push import generate_vapid_keys  # noqa: E402


def main() -> None:
    private_key, public_key = generate_vapid_keys()
    print('# Add to your .env — keep VAPID_PRIVATE_KEY secret and stable:')
    print(f'VAPID_PRIVATE_KEY={private_key}')
    print('# Contact for push services (mailto: or https: URL):')
    print('VAPID_SUBJECT=mailto:you@example.com')
    print()
    print(f'# Derived public key (informational; served to browsers automatically): {public_key}')


if __name__ == '__main__':
    main()
