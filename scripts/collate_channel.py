from __future__ import annotations

import aiohttp
import argparse
import asyncio
from itertools import chain
import json
import os
import sys


NEW_CHANNEL = (
    "https://github.com/kaste/pc-e02-thecrawl/releases/download"
    "/crawler-status/channel.json"
)
v3_CHANNEL = "https://packagecontrol.io/channel_v3.json"
v4_CHANNEL = "https://packagecontrol.github.io/channel/channel_v4.json"
DEFAULT_OUTPUT_FILE = "./channel.json"


async def main(output_file: str = DEFAULT_OUTPUT_FILE) -> None:
    async with aiohttp.ClientSession() as session:
        new_channel, v3_channel, v4_channel = await asyncio.gather(
            http_get_json(NEW_CHANNEL, session),
            http_get_json(v3_CHANNEL, session),
            http_get_json(v4_CHANNEL, session),
        )

    dependencies = v3_channel.pop('dependencies_cache', {})
    for library in chain(*dependencies.values()):
        del library['load_order']
        for release in library['releases']:
            release['python_versions'] = ['3.3']

    channel = {
        "schema_version": "4.0.0",
        "repositories": v4_channel["repositories"] + new_channel["repositories"],
        "packages_cache": new_channel["packages_cache"],
        "libraries_cache": dependencies | v4_channel["libraries_cache"],
    }

    for repo_url, packages in channel["libraries_cache"].items():
        packages.sort(key=lambda p: p["name"])
        for p in packages:
            if "releases" in p:
                p["releases"].sort(
                    key=lambda r: (
                        r.get("date") or r.get("version"),
                        r.get("platforms"),
                        r.get("sublime_text")
                    )
                )

    drop_count = 0
    for repo_url, packages in channel["packages_cache"].items():
        for p in packages[:]:
            releases = p["releases"]
            for r in releases:
                if is_outdated(r):
                    # err(f"Drop outdated release {r['version']} for package {p['name']} from {repo_url}")
                    releases.remove(r)
            if not releases:
                # err(f"Drop package {p['name']} which is not supported by modern Sublime Text")
                drop_count += 1
                packages.remove(p)

    with open(output_file, "w") as f:
        json.dump(channel, f)

    print(f"Wrote {output_file}")
    print(
        f"Collated {len(channel['repositories'])} repositories with "
        f"{sum(len(pkgs) for pkgs in channel['packages_cache'].values())} packages "
        f"and {sum(len(pkgs) for pkgs in channel['libraries_cache'].values())} libraries."
    )
    print(f"Dropped {drop_count} outdated packages.")

    # print the ten most recent packages
    print("\nTen most recent packages:")
    recent_packages = sorted(
        (p for pkgs in channel['packages_cache'].values() for p in pkgs),
        key=lambda p: p["last_modified"],
        reverse=True
    )[:10]
    for p in recent_packages:
        print(f" - [{p['name']}]({p['homepage']}) - Last modified: {p['last_modified']}")


def is_outdated(rel: Release) -> bool:
    req = rel["sublime_text"].replace(" ", "")
    return any(test in req for test in ("<3000", "-3", "<40", "-40", "<410", "-410"))


def err(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)


async def http_get_json(location: str, session: aiohttp.ClientSession) -> dict:
    text = await http_get(location, session)
    return json.loads(text)


async def http_get(location: str, session: aiohttp.ClientSession) -> str:
    headers={
        'User-Agent': 'Mozilla/5.0',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }
    async with session.get(location, headers=headers, raise_for_status=True) as resp:
        return await resp.text()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collate Package Control channels")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=DEFAULT_OUTPUT_FILE,
        help=f"Path to the output file (default: {DEFAULT_OUTPUT_FILE})"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    args.output = os.path.abspath(args.output)
    asyncio.run(main(args.output))
