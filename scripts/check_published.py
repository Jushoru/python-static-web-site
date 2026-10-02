"""Check the published report over HTTP, including the expected source commit."""

import argparse
import json
import re
import time
from urllib.error import URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


CHECKS = ("index.html", "results.html", "search/search_index.json",
          "assets/generated/build-times.svg", "assets/theory/ssg-comparison.svg")


def validate_contents(contents, commit):
    if "PYTHON-STATIC-REPORT-T1-P3" not in contents["index.html"]:
        raise ValueError("Control string is missing from the home page")
    if commit not in contents["results.html"]:
        raise ValueError("Published results do not yet contain the expected commit")
    index = json.loads(contents["search/search_index.json"])
    if not isinstance(index, dict) or not isinstance(index.get("docs"), list) or not index["docs"]:
        raise ValueError("Search index is empty or invalid")
    for path in CHECKS[-2:]:
        if "<svg" not in contents[path]:
            raise ValueError(f"Expected an SVG image at {path}")


def check_once(base, commit):
    contents = {}
    for path in CHECKS:
        url = urljoin(base, path) + "?revision=" + commit
        request = Request(url, headers={"User-Agent": "MkDocs-report-check", "Cache-Control": "no-cache"})
        with urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise ValueError(f"HTTP {response.status} for {path}")
            contents[path] = response.read().decode("utf-8")
    validate_contents(contents, commit)
    return len(contents)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--attempts", type=int, default=6)
    parser.add_argument("--delay", type=float, default=10)
    args = parser.parse_args()
    url = urlsplit(args.url)
    if url.scheme != "https" or not url.netloc or url.query or url.fragment or not args.url.endswith("/"):
        parser.error("Use an HTTPS site URL ending in / with no query or fragment")
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        parser.error("Use the full 40-character source commit SHA")
    if not 1 <= args.attempts <= 10 or not 0 <= args.delay <= 30:
        parser.error("Attempts must be 1..10 and delay 0..30 seconds")
    for attempt in range(1, args.attempts + 1):
        try:
            count = check_once(args.url, args.commit)
            print(f"OK: HTTP 200 for {count} resources; marker, commit, search index and SVGs verified.")
            return
        except (URLError, OSError, ValueError) as error:
            print(f"Check {attempt}/{args.attempts}: {error}", flush=True)
            if attempt == args.attempts:
                raise SystemExit("Published report verification failed") from error
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
