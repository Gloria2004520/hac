import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeURLError(ValueError):
    pass


TRUSTED_PLATFORM_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "bilibili.com",
    "b23.tv",
    "tiktok.com",
    "instagram.com",
)


def is_allowed_host(hostname: str, allowed_domains: tuple[str, ...]) -> bool:
    host = hostname.rstrip(".").lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def _assert_public_addresses(hostname: str) -> None:
    try:
        results = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURLError("域名无法解析") from exc

    if not results:
        raise UnsafeURLError("域名没有可用地址")

    for result in results:
        address = ipaddress.ip_address(result[4][0])
        if not address.is_global:
            raise UnsafeURLError("链接解析到了内网或保留地址")


def validate_source_url(url: str, allowed_domains: tuple[str, ...]) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLError("只支持 HTTP 或 HTTPS 链接")
    if parsed.username or parsed.password:
        raise UnsafeURLError("链接不能包含用户名或密码")
    if not parsed.hostname:
        raise UnsafeURLError("链接缺少域名")
    if parsed.port not in {None, 80, 443}:
        raise UnsafeURLError("链接使用了不允许的端口")
    if not is_allowed_host(parsed.hostname, allowed_domains):
        raise UnsafeURLError("暂不支持这个视频平台")
    # Proxy clients such as Clash may resolve public sites to 198.18.0.0/15
    # fake-IP addresses. The built-in platform list is fixed and trusted, so
    # DNS-level SSRF checks are only needed for user-added domains.
    if not is_allowed_host(parsed.hostname, TRUSTED_PLATFORM_DOMAINS):
        _assert_public_addresses(parsed.hostname)
    return url
