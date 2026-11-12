"""Small, exact-allowlist HTTPS fetcher for untrusted official source excerpts."""

import http.client
import ipaddress
import math
import socket
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import suppress
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

MAX_BODY_BYTES = 65_536
MAX_TEXT_CHARS = 1_000
MAX_REDIRECTS = 2
APPROVED_URLS = frozenset(
    {
        "https://www2.daad.de/deutschland/stipendium/datenbank/en/"
        "21148-scholarship-database/?detail=50026200",
        "https://www.smaccs.eu/",
        "https://www.smaccs.eu/practical/scholarships/",
        "https://www.smaccs.eu/admissions/admission-criteria/",
        "https://www.smaccs.eu/admissions/deadlines/",
        # Phase 6A: individually reviewed catalogue sources, never a domain wildcard.
        "https://www.master-ediss.eu/scholarship/",
        "https://deai.ulb.be/home/students/tuition-fees-scholarships/",
        "https://www.cybersure-master.eu/scholarships-and-fees",
        "https://cybermacs.eu/scholarships/",
        "https://www.imlex.org/fees-and-scholarships/",
        "https://densys.univ-lorraine.fr/fees-and-scholarships/",
        "https://www.erasmus-mundus.emimep.eu/admission-applications/"
        "erasmus-scholarships/",
        "https://emsse.eu/admission-and-scholarships/scholarships/",
        "https://www.unite-codas-master.eu/scholarship.html",
        "https://www.eusmat.net/international-studies/master/amase/application/"
        "fees-and-scholarships/",
        "https://master-epico.ec-nantes.fr/english-version/admission/"
        "fees-scholarships-1",
        "https://master-eu-core.ec-nantes.fr/admission/students/fees-scholarships",
        "https://jemaro.ec-nantes.fr/english-version/admission/"
        "jemaro-fees-and-scholarships",
        "https://ifrosmaster.org/ifros-applicants/fees-grants",
        "https://eminent-master.eu/scholarships/",
        "https://www2.daad.de/deutschland/stipendium/datenbank/en/"
        "21148-scholarship-database/?detail=57742130",
        "https://stipendiumhungaricum.hu/about/",
        "https://www.kz.emb-japan.go.jp/itpr_ru/11_000001_00641.html",
        "https://admission.kaist.ac.kr/intl-graduate/FinancialSupport/Scholarship/"
        "KAISTScholarship/",
        "https://www.gist.ac.kr/iadm/html/sub04/0401.html",
    }
)
_RESOLVER_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="official-dns")
_RESOLVER_SLOTS = threading.BoundedSemaphore(2)


class PublicPageError(Exception):
    """Safe error codes only: never expose request data or underlying exceptions."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class OfficialPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_url: str
    fetched_at: AwareDatetime
    untrusted_text: str = Field(max_length=MAX_TEXT_CHARS)
    truncated: bool
    untrusted: Literal[True] = True

    @field_validator("source_url")
    @classmethod
    def source_must_be_approved(cls, value: str) -> str:
        try:
            return approved_url(value)
        except PublicPageError:
            raise ValueError("Source URL is not approved") from None


def approved_url(url: str) -> str:
    if (
        not isinstance(url, str)
        or len(url) > 2_048
        or "\\" in url
        or "#" in url
        or any(ord(character) <= 32 or ord(character) == 127 for character in url)
    ):
        raise PublicPageError("url_not_approved")
    try:
        parts = urlsplit(url)
        if (
            parts.scheme.lower() != "https"
            or not parts.hostname
            or parts.port not in (None, 443)
            or parts.username
            or parts.password
            or parts.fragment
        ):
            raise ValueError("invalid source URL")
        hostname = parts.hostname.lower()
        # No IP literals, alternative host spellings, arbitrary paths, or queries.
        canonical = urlunsplit(
            (
                "https",
                hostname,
                parts.path or "/",
                urlencode(
                    sorted(
                        parse_qsl(
                            parts.query, keep_blank_values=True, strict_parsing=True
                        )
                    )
                ),
                "",
            )
        )
        if canonical not in APPROVED_URLS:
            raise ValueError("not allowlisted")
        return canonical
    except TypeError, ValueError:
        raise PublicPageError("url_not_approved") from None


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise PublicPageError("timeout")
    return remaining


def is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if (
        not address.is_global
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or address.is_loopback
        or address.is_link_local
    ):
        return False
    if isinstance(address, ipaddress.IPv6Address):
        embedded = [address.ipv4_mapped, address.sixtofour]
        if address.teredo:
            embedded.extend(address.teredo)
        if any(
            item is not None and not is_public_address(str(item)) for item in embedded
        ):
            return False
    return True


def resolve_public_address(hostname: str, deadline: float) -> tuple[int, str]:
    # getaddrinfo cannot be cancelled portably. Bound both workers and pending
    # jobs so repeated DNS stalls cannot create unbounded threads or a queue.
    if not _RESOLVER_SLOTS.acquire(timeout=_remaining(deadline)):
        raise PublicPageError("timeout")
    try:
        future = _RESOLVER_POOL.submit(
            socket.getaddrinfo,
            hostname,
            443,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
    except RuntimeError:
        _RESOLVER_SLOTS.release()
        raise PublicPageError("network_error") from None
    future.add_done_callback(lambda _future: _RESOLVER_SLOTS.release())
    try:
        answers = future.result(timeout=_remaining(deadline))
    except FutureTimeoutError:
        future.cancel()
        raise PublicPageError("timeout") from None
    except OSError:
        raise PublicPageError("network_error") from None
    if not answers:
        raise PublicPageError("network_error")
    addresses = [(family, sockaddr[0]) for family, _, _, _, sockaddr in answers]
    if any(
        family not in (socket.AF_INET, socket.AF_INET6) or not is_public_address(ip)
        for family, ip in addresses
    ):
        raise PublicPageError("nonpublic_address")
    _remaining(deadline)
    return addresses[0]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect directly to a checked numeric address, preserving TLS hostname."""

    def __init__(self, host: str, family: int, address: str, deadline: float):
        super().__init__(
            host,
            port=443,
            timeout=_remaining(deadline),
            context=ssl.create_default_context(),
        )
        self._family = family
        self._address = address
        self._deadline = deadline
        self._transport = None
        self._transport_lock = threading.Lock()
        self.expired = False

    def abort(self) -> None:
        self.expired = True
        with self._transport_lock:
            transport = self._transport
        if transport is not None:
            with suppress(OSError):
                transport.shutdown(socket.SHUT_RDWR)
            with suppress(OSError):
                transport.close()

    def connect(self) -> None:
        with self._transport_lock:
            if self.expired:
                raise TimeoutError
            raw = socket.socket(self._family, socket.SOCK_STREAM)
            self._transport = raw
        try:
            raw.settimeout(_remaining(self._deadline))
            target = (
                (self._address, 443, 0, 0)
                if self._family == socket.AF_INET6
                else (
                    self._address,
                    443,
                )
            )
            raw.connect(target)
            # Do not call HTTPSConnection.connect/create_connection: they resolve
            # again. Disable automatic handshake to publish the TLS socket to the
            # watchdog before any server-controlled handshake bytes are read.
            wrapped = self._context.wrap_socket(
                raw,
                server_hostname=self.host,
                do_handshake_on_connect=False,
            )
            with self._transport_lock:
                self._transport = wrapped
            if self.expired:
                self.abort()
                raise TimeoutError
            wrapped.settimeout(_remaining(self._deadline))
            wrapped.do_handshake()
            self.sock = wrapped
        except BaseException:
            with suppress(OSError):
                raw.close()
            self.close()
            raise

    def close(self) -> None:
        with suppress(OSError):
            super().close()
        with self._transport_lock:
            transport = self._transport
            self._transport = None
        if transport is not None:
            with suppress(OSError):
                transport.close()


class _VisibleText(HTMLParser):
    _EXCLUDED = frozenset(
        {"script", "style", "form", "nav", "noembed", "noscript", "head"}
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._excluded: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._EXCLUDED:
            self._excluded.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._excluded:
            del self._excluded[self._excluded.index(tag) :]

    def handle_data(self, data: str) -> None:
        if not self._excluded:
            self.parts.append(data)


def fetch_official_page(url: str, *, timeout: float = 6.0) -> OfficialPage:
    """Fetch one approved excerpt; it cannot alter catalogue facts or rules.

    A socket-shutdown watchdog enforces the overall deadline even for a peer
    that drips response headers/body bytes faster than an individual read timeout.
    DNS resolution has a separate bounded deadline and bounded worker pool.
    """
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise PublicPageError("timeout")
    deadline = time.monotonic() + min(timeout, 6.0)
    current = approved_url(url)
    for hop in range(MAX_REDIRECTS + 1):
        parts = urlsplit(current)
        family, address = resolve_public_address(parts.hostname, deadline)
        connection = _PinnedHTTPSConnection(parts.hostname, family, address, deadline)
        watchdog = threading.Timer(_remaining(deadline), connection.abort)
        watchdog.daemon = True
        watchdog.start()
        response = None
        try:
            target = parts.path + (f"?{parts.query}" if parts.query else "")
            connection.request(
                "GET",
                target,
                headers={
                    "Accept": "text/html, text/plain",
                    "Accept-Encoding": "identity",
                    "User-Agent": "ScholarshipHunterAI/0.5 (official-source-review)",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                if hop >= MAX_REDIRECTS:
                    raise PublicPageError("redirect_limit")
                location = response.getheader("Location")
                if not location:
                    raise PublicPageError("invalid_redirect")
                current = approved_url(urljoin(current, location))
                continue
            if response.status != 200:
                raise PublicPageError("http_error")
            content_type = (
                response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            )
            if content_type not in ("text/html", "text/plain"):
                raise PublicPageError("unsupported_content")
            encoding = (
                response.getheader("Content-Encoding", "identity").strip().lower()
            )
            if encoding not in ("", "identity"):
                raise PublicPageError("unsupported_encoding")
            declared = response.getheader("Content-Length")
            if declared is not None:
                try:
                    length = int(declared)
                except ValueError:
                    raise PublicPageError("invalid_content_length") from None
                if length < 0 or length > MAX_BODY_BYTES:
                    raise PublicPageError("content_limit")
            body = bytearray()
            while True:
                _remaining(deadline)
                chunk = response.read(min(4_096, MAX_BODY_BYTES + 1 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
                if len(body) > MAX_BODY_BYTES:
                    raise PublicPageError("content_limit")
            _remaining(deadline)
            text = body.decode("utf-8", errors="replace")
            if content_type == "text/html":
                parser = _VisibleText()
                parser.feed(text)
                parser.close()
                text = " ".join(parser.parts)
            text = " ".join(text.split())
            if not text:
                raise PublicPageError("empty_content")
            _remaining(deadline)
            return OfficialPage(
                source_url=current,
                fetched_at=datetime.now(UTC),
                untrusted_text=text[:MAX_TEXT_CHARS],
                truncated=len(text) > MAX_TEXT_CHARS,
            )
        except TimeoutError:
            raise PublicPageError("timeout") from None
        except OSError, http.client.HTTPException:
            raise PublicPageError(
                "timeout" if connection.expired else "network_error"
            ) from None
        finally:
            watchdog.cancel()
            if response is not None:
                with suppress(OSError):
                    response.close()
            connection.close()
    raise PublicPageError("redirect_limit")
