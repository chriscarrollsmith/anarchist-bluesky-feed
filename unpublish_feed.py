#!/usr/bin/env python3
"""Delete a Bluesky feed generator record from your account.

Uses HANDLE / PASSWORD from `.env` (Bluesky app password). The rkey must be
passed explicitly so a default RECORD_NAME cannot delete the wrong feed.

Example (drop the old anarchism generator):

    uv run python unpublish_feed.py anarchism
"""

from __future__ import annotations

import argparse
import os
import sys

from atproto import Client, models
from dotenv import load_dotenv

# Override process env so shell HOSTNAME (e.g. "cursor") cannot beat .env.
load_dotenv(override=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'rkey',
        help='Feed generator record key to delete (e.g. anarchism)',
    )
    args = parser.parse_args(argv)

    handle = os.environ.get('HANDLE')
    password = os.environ.get('PASSWORD')
    missing = [n for n, v in {'HANDLE': handle, 'PASSWORD': password}.items() if not v]
    if missing:
        print(f'Missing required env vars: {", ".join(missing)}', file=sys.stderr)
        return 1

    assert handle is not None
    assert password is not None

    rkey = args.rkey.strip()
    if not rkey or '/' in rkey or rkey != rkey.lower():
        print(
            f'Refusing rkey {args.rkey!r}: expected a lowercase short name like "anarchism".',
            file=sys.stderr,
        )
        return 1

    client = Client()
    client.login(handle, password)
    me = client.me
    if me is None:
        print('Login succeeded but client profile is unavailable.', file=sys.stderr)
        return 1

    client.com.atproto.repo.delete_record(
        models.ComAtprotoRepoDeleteRecord.Data(
            repo=me.did,
            collection=models.ids.AppBskyFeedGenerator,
            rkey=rkey,
        )
    )

    print(f'Deleted feed generator record: at://{me.did}/app.bsky.feed.generator/{rkey}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
