"""Ask GitHub whether a newer release exists.  Never downloads or installs anything.

Only the public "latest release" endpoint is contacted; drafts and pre-releases
are never reported.  Users can switch the startup check off in Settings.
"""
import json
import re
import urllib.request

from version import APP_VERSION, REPOSITORY

LATEST_API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
RELEASES_PAGE = f'https://github.com/{REPOSITORY}/releases/latest'


def parse_version(text):
    """'v0.8.10' -> (0, 8, 10); anything else -> None."""
    match = re.fullmatch(r'\s*[vV]?(\d+)\.(\d+)(?:\.(\d+))?\s*', str(text or ''))
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def is_newer(latest, current=APP_VERSION):
    latest, current = parse_version(latest), parse_version(current)
    return latest is not None and current is not None and latest > current


def fetch_latest(timeout=6, opener=urllib.request.urlopen):
    """Return (tag, page_url) of the newest published release; raises OSError/ValueError on failure."""
    request = urllib.request.Request(LATEST_API, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': f'FH6CarModManager/{APP_VERSION}',
    })
    with opener(request, timeout=timeout) as response:
        data = json.loads(response.read(256 * 1024).decode('utf-8'))
    tag = data.get('tag_name') if isinstance(data, dict) else None
    if not isinstance(tag, str) or parse_version(tag) is None:
        raise ValueError('GitHub returned no usable release version')
    page = data.get('html_url')
    if not isinstance(page, str) or not page.startswith(f'https://github.com/{REPOSITORY}/'):
        page = RELEASES_PAGE  # never open an unexpected address
    return tag, page
