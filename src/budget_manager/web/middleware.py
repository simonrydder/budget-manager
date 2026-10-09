"""Refuse every request that does not come from the local network, and sign in automatically
when the app only serves the computer it runs on."""

from __future__ import annotations

import ipaddress
import logging
import os
import re

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect

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


THIS_COMPUTER = parse_networks(["127.0.0.0/8", "::1/128"])


def local_person():
    """The one person of a budget manager that only serves this computer: the first one there
    is, or a new one named after the computer's user, with a budget to set up."""
    from budget_manager.ledger import budgets

    User = get_user_model()
    user = User.objects.order_by("pk").first()
    if user is None:
        name = os.environ.get("USERNAME") or os.environ.get("USER") or "Me"
        username = re.sub(r"[^\w.@+-]", "", name)[:150] or "me"
        user = User(username=username, first_name=name[:150])
        user.set_unusable_password()
        user.save()
        budgets.give_access(user)
    return user


class ThisComputerLoginMiddleware:
    """With ``settings.LOCAL_ONLY`` (the one-file start, which only listens on this computer)
    there is no login: a request from this computer is signed in as its person. A request from
    anywhere else still needs to log in, should one ever get through."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        address = request.META.get("REMOTE_ADDR", "")
        if settings.LOCAL_ONLY and is_allowed(address, THIS_COMPUTER):
            if not request.user.is_authenticated:
                login(request, local_person(), backend="django.contrib.auth.backends.ModelBackend")
            if request.path_info in ("/login/", "/setup/"):
                return redirect("/")
        return self.get_response(request)
