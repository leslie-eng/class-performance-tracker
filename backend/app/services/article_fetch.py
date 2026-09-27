"""Fetch a member-submitted article URL and reduce it to readable text.

URLs come from users, so every hop (including redirects) is checked to make
sure it doesn't point at a private/internal address.
"""

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

MAX_BYTES = 3_000_000
MAX_REDIRECTS = 5
BOILERPLATE_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "iframe"]


class ArticleFetchError(Exception):
    pass


def _assert_public_host(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ArticleFetchError("Only http(s) URLs are supported")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ArticleFetchError(f"Could not resolve {parsed.hostname}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ArticleFetchError("URL resolves to a non-public address")


def fetch_html(url: str, timeout: float = 15.0) -> str:
    headers = {"User-Agent": "ClassTrackBot/1.0 (+article grading)"}
    with httpx.Client(timeout=timeout, follow_redirects=False, headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _assert_public_host(url)
            with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    url = urljoin(url, resp.headers["location"])
                    continue
                if resp.status_code >= 400:
                    raise ArticleFetchError(f"Article returned HTTP {resp.status_code}")
                body = b""
                for chunk in resp.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise ArticleFetchError("Article page is too large")
                return body.decode(resp.encoding or "utf-8", errors="replace")
    raise ArticleFetchError("Too many redirects")


def extract_text(html: str) -> tuple[str, str]:
    """Returns (title, body_text) with nav/footer/script boilerplate removed."""
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title else ""
    for tag in soup(BOILERPLATE_TAGS):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    lines = (line.strip() for line in root.get_text("\n").splitlines())
    return title, "\n".join(line for line in lines if line)


def fetch_article(url: str) -> tuple[str, str]:
    title, text = extract_text(fetch_html(url))
    if len(text) < 200:
        raise ArticleFetchError(
            "Couldn't read enough text from that page (it may require login or be rendered by JavaScript)"
        )
    return title, text
