"""Transporte controlado real HTTP; sem serviços públicos nem DNS externo."""

import asyncio
import gzip
import socket
import ssl
import zlib

import httpx2
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dona_maria.planning import BusinessRuleError
from dona_maria.research_network import SecureExtractor


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Wire:
    def __init__(self, responses, *, peer=None, answers=None):
        self.responses = list(responses)
        self.peer = peer
        self.answers = answers or ["93.184.216.34"]
        self.connected = []
        self.sent = []
        self.tls = []
        self.resolved = []
        self.closed = 0

    def resolve(self, host, port, **kwargs):
        self.resolved.append(host)
        return [
            (
                socket.AF_INET6 if ":" in ip else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (ip, port),
            )
            for ip in self.answers
        ]

    async def connect_tcp(self, host, port, **kwargs):
        self.connected.append((host, port))
        return Stream(self, self.responses.pop(0), self.peer or host)

    async def sleep(self, seconds):
        pass

    def client(self, **kwargs):
        client = httpx2.AsyncClient(**kwargs)
        client._transport._pool._network_backend = self
        return client


class Stream:
    def __init__(self, wire, response, peer):
        self.wire, self.response, self.peer = wire, response, peer

    async def read(self, max_bytes, timeout=None):
        chunk, self.response = self.response[:max_bytes], self.response[max_bytes:]
        return chunk

    async def write(self, buffer, timeout=None):
        self.wire.sent.append(bytes(buffer))

    async def aclose(self):
        self.wire.closed += 1

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self.wire.tls.append((server_hostname, ssl_context.verify_mode, ssl_context.check_hostname))
        return self

    def get_extra_info(self, info):
        return (self.peer, 443) if info == "server_addr" else None


def response(body=b"<h1>Arroz</h1><p>Cozinhe.</p>", *, status=200, headers=b""):
    return (
        f"HTTP/1.1 {status} Test\r\nContent-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n".encode()
        + headers
        + b"\r\n"
        + body
    )


@pytest.mark.anyio
async def test_https_pins_public_connection_and_preserves_hostname_for_tls():
    wire = Wire([response()])
    extractor = SecureExtractor(client_factory=wire.client, resolver=wire.resolve)
    result = await extractor.extract("https://example.org/arroz")
    assert result["text"] == "Arroz Cozinhe."
    assert wire.connected == [("93.184.216.34", 443)]
    assert wire.tls == [("example.org", ssl.CERT_REQUIRED, True)]
    assert b"Host: example.org" in b"".join(wire.sent)
    assert result["destinations"][0]["url"] == "https://example.org/arroz"
    assert result["complete"] is True
    assert result["decoded_bytes"] == len(b"<h1>Arroz</h1><p>Cozinhe.</p>")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/",
        "https://example.org:444/",
        "https://user:pass@example.org/",
        "https://127.0.0.1/",
        "https://10.0.0.1/",
        "https://[::1]/",
        "https://[fc00::1]/",
        "https://169.254.169.254/",
        "https://169.254.170.2/",
        "https://100.100.100.200/",
        "https://[fe80::1]/",
        "https://[::ffff:127.0.0.1]/",
        "https://224.0.0.1/",
        "https://192.0.2.1/",
        "https://metadata.google.internal/",
        "https://foo%2ebar/",
        "https://example.org/\r\nAuthorization:secret",
        "https://user@example.org/",
    ],
)
async def test_prohibited_url_never_opens_connection(url):
    wire = Wire([])
    with pytest.raises(BusinessRuleError):
        await SecureExtractor(client_factory=wire.client, resolver=wire.resolve).extract(url)
    assert wire.connected == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "answers,peer",
    [
        (["93.184.216.34", "10.0.0.1"], None),
        (["93.184.216.34", "::ffff:169.254.169.254"], None),
        (["93.184.216.34"], "127.0.0.1"),
        (["93.184.216.34"], "1.1.1.1"),
        (["93.184.216.34", "fc00::1"], None),
    ],
)
async def test_mixed_dns_and_peer_divergence_cannot_send_request(answers, peer):
    wire = Wire([response()], answers=answers, peer=peer)
    with pytest.raises(BusinessRuleError):
        await SecureExtractor(client_factory=wire.client, resolver=wire.resolve).extract(
            "https://example.org/"
        )
    assert wire.sent == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status,headers,body",
    [
        (206, b"", b"Arroz"),
        (200, b"Content-Range: bytes 0-4/100\r\n", b"Arroz"),
        (200, b"", b""),
        (503, b"", b"Falha"),
        (200, b"", b"<script>CANARY_SCRIPT</script>"),
    ],
)
async def test_partial_failed_or_empty_content_cannot_be_complete(status, headers, body):
    wire = Wire([response(body, status=status, headers=headers)])
    with pytest.raises(BusinessRuleError):
        await SecureExtractor(client_factory=wire.client, resolver=wire.resolve).extract(
            "https://example.org/"
        )


@pytest.mark.anyio
async def test_markup_does_not_execute_or_load_resources_and_script_is_not_source_text():
    wire = Wire(
        [
            response(
                b"<p>Arroz</p><script>CANARY_SCRIPT</script><style>SECRET</style>"
                b'<iframe src="https://evil.test"></iframe><img src="file:///private">'
            )
        ]
    )
    result = await SecureExtractor(client_factory=wire.client, resolver=wire.resolve).extract(
        "https://example.org/"
    )
    assert result["text"] == "Arroz"
    assert len(wire.connected) == 1


@pytest.mark.anyio
async def test_redirect_is_validated_and_cookies_are_not_forwarded(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    wire = Wire(
        [
            response(
                b"",
                status=302,
                headers=b"Location: https://other.example/arroz\r\n"
                b"Set-Cookie: secret=CANARY_COOKIE\r\n",
            ),
            response(),
        ]
    )
    result = await SecureExtractor(client_factory=wire.client, resolver=wire.resolve).extract(
        "https://example.org/"
    )
    assert result["url"] == "https://other.example/arroz"
    assert wire.resolved == ["example.org", "other.example"]
    assert len(wire.connected) == 2
    sent = b"".join(wire.sent).lower()
    assert b"cookie:" not in sent and b"authorization:" not in sent
    assert b"canary_cookie" not in sent


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body,headers",
    [
        (b"<!--" + b"x" * (1024 * 1024) + b"--><p>Arroz</p>", b""),
        (b"x" * (64 * 1024 + 1), b""),
        (gzip.compress(b"x" * (1024 * 1024 + 1)), b"Content-Encoding: gzip\r\n"),
    ],
)
async def test_excess_wire_decoded_body_and_text_are_refused(body, headers):
    wire = Wire([response(body, headers=headers)])
    with pytest.raises(BusinessRuleError, match="limite"):
        await SecureExtractor(client_factory=wire.client, resolver=wire.resolve).extract(
            "https://example.org/"
        )


@pytest.mark.anyio
async def test_peer_rebinding_closes_connection_before_any_bytes_are_sent():
    wire = Wire([response()], peer="127.0.0.1")
    with pytest.raises(BusinessRuleError):
        await SecureExtractor(client_factory=wire.client, resolver=wire.resolve).extract(
            "https://example.org/"
        )
    assert wire.sent == []
    assert wire.closed == 1


@pytest.mark.anyio
@pytest.mark.parametrize("count", [3, 4])
async def test_exactly_three_redirects_are_allowed_and_four_are_refused(count):
    redirect = response(b"", status=302, headers=b"Location: /next\r\n")
    wire = Wire([redirect] * count + [response()])
    extractor = SecureExtractor(client_factory=wire.client, resolver=wire.resolve)
    if count == 3:
        assert (await extractor.extract("https://example.org/"))["text"] == "Arroz Cozinhe."
    else:
        with pytest.raises(BusinessRuleError):
            await extractor.extract("https://example.org/")
    assert len(wire.connected) == 4


@pytest.mark.anyio
async def test_redirect_to_private_or_rebound_dns_is_refused_before_request():
    wire = Wire([response(b"", status=302, headers=b"Location: https://10.0.0.1/\r\n")])
    with pytest.raises(BusinessRuleError):
        await SecureExtractor(client_factory=wire.client, resolver=wire.resolve).extract(
            "https://example.org/"
        )
    assert len(wire.connected) == 1
    wire = Wire([response(b"", status=302, headers=b"Location: /again\r\n"), response()])
    calls = []

    def resolver(host, port, **kwargs):
        wire.answers = ["93.184.216.34"] if not calls else ["10.0.0.1"]
        calls.append(host)
        return wire.resolve(host, port, **kwargs)

    with pytest.raises(BusinessRuleError):
        await SecureExtractor(client_factory=wire.client, resolver=resolver).extract(
            "https://example.org/"
        )
    assert len(wire.connected) == 1 and len(calls) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate"])
async def test_exact_decoded_response_and_text_boundaries(encoding):
    # Um MiB de HTML completo, contendo exatamente64KiB de texto.
    plain = b"x" * (64 * 1024)
    body = plain + b"<!--" + b"p" * (1024 * 1024 - len(plain) - 7) + b"-->"
    encoded = (
        body
        if encoding == "identity"
        else (gzip.compress(body) if encoding == "gzip" else zlib.compress(body))
    )
    wire = Wire([response(encoded, headers=f"Content-Encoding: {encoding}\r\n".encode())])
    result = await SecureExtractor(client_factory=wire.client, resolver=wire.resolve).extract(
        "https://example.org/"
    )
    assert result["text"] == plain.decode()


@pytest.mark.anyio
async def test_truncated_transfer_is_refused_even_when_content_length_looks_small():
    wire = Wire([b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 10\r\n\r\nArroz"])
    with pytest.raises(Exception):
        await SecureExtractor(client_factory=wire.client, resolver=wire.resolve).extract(
            "https://example.org/"
        )


@given(octets=st.tuples(*(st.integers(0, 255) for _ in range(3))))
@settings(max_examples=30)
def test_private_ipv4_never_reaches_transport(octets):
    wire = Wire([])
    extractor = SecureExtractor(client_factory=wire.client, resolver=wire.resolve)
    with pytest.raises(BusinessRuleError):
        asyncio.run(extractor.extract("https://10." + ".".join(map(str, octets)) + "/"))
    assert wire.connected == []


@pytest.mark.anyio
async def test_deadline_cancels_a_stalled_response():
    class StalledWire(Wire):
        async def connect_tcp(self, host, port, **kwargs):
            await asyncio.Event().wait()

    wire = StalledWire([])
    with pytest.raises(TimeoutError):
        await SecureExtractor(client_factory=wire.client, resolver=wire.resolve).extract(
            "https://example.org/"
        )


@pytest.mark.anyio
async def test_plain_text_is_not_reinterpreted_as_html():
    body = b"Use <arroz> e cozinhe."
    wire = Wire(
        [
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\n\r\n"
            + body
        ]
    )
    result = await SecureExtractor(client_factory=wire.client, resolver=wire.resolve).extract(
        "https://example.org/"
    )
    assert result["text"] == "Use <arroz> e cozinhe."


@pytest.mark.anyio
@pytest.mark.parametrize("chunked", [False, True])
async def test_response_limit_counts_stream_without_content_length(chunked):
    body = b"x" * (1024 * 1024 + 1)
    headers = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
    if chunked:
        headers += b"Transfer-Encoding: chunked\r\n"
        body = f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n"
    wire = Wire([headers + b"\r\n" + body])
    with pytest.raises(BusinessRuleError) as refusal:
        await SecureExtractor(client_factory=wire.client, resolver=wire.resolve).extract(
            "https://example.org/"
        )
    assert refusal.value.code == "RESOURCE_LIMIT_EXCEEDED"
