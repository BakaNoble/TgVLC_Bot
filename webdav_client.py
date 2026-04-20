"""
Lightweight WebDAV client for browsing remote directories.

Uses only stdlib (urllib + xml) — no extra dependencies required.
"""
import logging
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

_DAV_NS = "DAV:"
_PROPFIND_BODY = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<D:propfind xmlns:D="DAV:">'
    "<D:prop>"
    "<D:resourcetype/>"
    "<D:getcontentlength/>"
    "</D:prop>"
    "</D:propfind>"
).encode("utf-8")


@dataclass(slots=True)
class WebDAVEntry:
    """A single file or collection returned by PROPFIND."""

    name: str
    href: str
    is_directory: bool
    size: int = 0


def list_directory(
    url: str,
    username: str = "",
    password: str = "",
    video_extensions: Optional[Set[str]] = None,
) -> Tuple[bool, List[WebDAVEntry], str]:
    """PROPFIND *url* with Depth:1 and return child entries.

    Returns ``(success, entries, message)``.
    """
    if not url.endswith("/"):
        url += "/"

    req = urllib.request.Request(url, data=_PROPFIND_BODY, method="PROPFIND")
    req.add_header("Content-Type", "application/xml; charset=utf-8")
    req.add_header("Depth", "1")

    if username:
        token = b64encode(f"{username}:{password}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        msg = f"WebDAV HTTP {exc.code}"
        logger.error("WebDAV PROPFIND failed: %s %s", url, msg)
        return False, [], msg
    except urllib.error.URLError as exc:
        msg = f"WebDAV 连接失败: {exc.reason}"
        logger.error("WebDAV PROPFIND failed: %s %s", url, msg)
        return False, [], msg
    except Exception as exc:
        msg = f"WebDAV 错误: {exc}"
        logger.error("WebDAV PROPFIND failed: %s %s", url, msg)
        return False, [], msg

    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        msg = f"WebDAV XML 解析失败: {exc}"
        logger.error(msg)
        return False, [], msg

    request_path_decoded = urllib.parse.unquote(
        urllib.parse.urlparse(url).path
    ).rstrip("/")
    parent_prefix = request_path_decoded + "/"
    entries: List[WebDAVEntry] = []

    for response_elem in root.iter(f"{{{_DAV_NS}}}response"):
        href_elem = response_elem.find(f"{{{_DAV_NS}}}href")
        if href_elem is None or not href_elem.text:
            continue

        href_raw = href_elem.text
        href_decoded = urllib.parse.unquote(href_raw).rstrip("/")

        # Skip the directory itself
        if href_decoded == request_path_decoded:
            continue

        # Only accept direct children (no deeper descendants)
        if not href_decoded.startswith(parent_prefix):
            continue
        relative = href_decoded[len(parent_prefix):]
        if "/" in relative:
            continue

        # Locate <prop> inside the first <propstat>
        propstat = response_elem.find(f"{{{_DAV_NS}}}propstat")
        if propstat is None:
            continue
        prop = propstat.find(f"{{{_DAV_NS}}}prop")
        if prop is None:
            continue

        rt = prop.find(f"{{{_DAV_NS}}}resourcetype")
        is_dir = rt is not None and rt.find(f"{{{_DAV_NS}}}collection") is not None

        name = href_decoded.rsplit("/", 1)[-1]
        if not name:
            continue

        size = 0
        cl = prop.find(f"{{{_DAV_NS}}}getcontentlength")
        if cl is not None and cl.text:
            try:
                size = int(cl.text)
            except ValueError:
                pass

        # Filter non-video files
        if not is_dir and video_extensions:
            ext_pos = name.rfind(".")
            ext = name[ext_pos:].lower() if ext_pos != -1 else ""
            if ext not in video_extensions:
                continue

        entries.append(WebDAVEntry(name=name, href=href_raw, is_directory=is_dir, size=size))

    entries.sort(key=lambda e: (not e.is_directory, e.name.lower()))
    return True, entries, f"已加载 {len(entries)} 个项目"


def build_full_url(base_url: str, href: str) -> str:
    """Turn a PROPFIND *href* (server-relative path) into a full HTTP URL."""
    parsed = urllib.parse.urlparse(base_url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, href, "", "", ""))
