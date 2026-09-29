"""Refuse every request that does not come from the local network."""

from __future__ import annotations

import ipaddress
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden

logger = logging.getLogger(__name__)

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_networks(values: list[str]) -> list[Network]:
    return [ipaddress.ip_network(value, strict=False) for value in values]


def is_allowed(address: str, networks: list[Network]) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return any(ip in network for network in networks if network.version == ip.version)


class LocalNetworkOnlyMiddleware:
    """Only answer clients whose address is inside ``settings.ALLOWED_NETWORKS``.

    The check uses the address of the connecting socket (``REMOTE_ADDR``), never headers such
    as ``X-Forwarded-For`` that a client could fake.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.networks = parse_networks(settings.ALLOWED_NETWORKS)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        address = request.META.get("REMOTE_ADDR", "")
        if not is_allowed(address, self.networks):
            logger.warning("Refused request from %s outside the local network", address)
            return HttpResponseForbidden(
                "This budget manager is only available on the local network.",
                content_type="text/plain",
            )
        return self.get_response(request)
