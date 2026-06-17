import re


def parse_embed(url: str) -> dict | None:
    """Return embed_html and thumbnail for a supported video URL, or None."""
    url = url.strip()

    # YouTube full
    m = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    if m:
        vid = m.group(1)
        return {
            "embed_html": f'<iframe src="https://www.youtube.com/embed/{vid}?rel=0&autoplay=1" '
                          f'allowfullscreen allow="autoplay; encrypted-media"></iframe>',
            "thumbnail": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
        }

    # YouTube shorts
    m = re.search(r"youtube\.com/shorts/([A-Za-z0-9_-]{11})", url)
    if m:
        vid = m.group(1)
        return {
            "embed_html": f'<iframe src="https://www.youtube.com/embed/{vid}?rel=0&autoplay=1" '
                          f'allowfullscreen allow="autoplay; encrypted-media"></iframe>',
            "thumbnail": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
        }

    # Instagram reel / post
    m = re.search(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    if m:
        code = m.group(1)
        return {
            "embed_html": f'<iframe src="https://www.instagram.com/p/{code}/embed/" '
                          f'allowfullscreen scrolling="no"></iframe>',
            "thumbnail": None,
        }

    # TikTok
    m = re.search(r"tiktok\.com/@[^/]+/video/(\d+)", url)
    if m:
        vid = m.group(1)
        return {
            "embed_html": f'<iframe src="https://www.tiktok.com/embed/v2/{vid}" '
                          f'allowfullscreen allow="autoplay; encrypted-media"></iframe>',
            "thumbnail": None,
        }

    # Twitter / X
    m = re.search(r"(?:twitter|x)\.com/\w+/status/(\d+)", url)
    if m:
        status_id = m.group(1)
        return {
            "embed_html": (
                f'<blockquote class="twitter-tweet"><a href="{url}"></a></blockquote>'
                f'<script async src="https://platform.twitter.com/widgets.js"></script>'
            ),
            "thumbnail": None,
        }

    return None
