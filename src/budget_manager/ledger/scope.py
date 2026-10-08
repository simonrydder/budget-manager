"""Every budget lives under its own URL prefix, ``/b/<id>/``.

The middleware strips the prefix before Django resolves the URL and sets it as the script
prefix, so the views and templates stay the same and every URL they build (``reverse``,
``{% url %}``, ``redirect``) stays inside the budget being looked at. Two browser tabs on two
budgets therefore never mix them up.
"""

from __future__ import annotations

import re

from django.http import Http404, HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import get_script_prefix, reverse, set_script_prefix

BUDGET_PATH = re.compile(r"^/b/(?P<id>\d+)(?P<rest>/.*)?$")
BUDGET_PREFIX = re.compile(r"^(?P<root>.*/)b/\d+/$")


def root_prefix() -> str:
    """The script prefix without any budget part (normally ``/``)."""
    prefix = get_script_prefix()
    match = BUDGET_PREFIX.match(prefix)
    return match["root"] if match else prefix


def budget_url(budget_id: int, path: str = "/") -> str:
    """``path`` (starting with ``/``) inside the budget ``budget_id``."""
    return f"{root_prefix()}b/{budget_id}{path}"


def budget_reverse(budget_id: int, viewname: str, *args, **kwargs) -> str:
    """The URL of ``viewname`` inside the budget ``budget_id``, from anywhere."""
    path = reverse(viewname, args=args, kwargs=kwargs)
    return budget_url(budget_id, "/" + path[len(get_script_prefix()) :])


def global_url(viewname: str, *args, **kwargs) -> str:
    """The URL of a page outside every budget (like the list of budgets), from anywhere."""
    path = reverse(viewname, args=args, kwargs=kwargs)
    return root_prefix() + path[len(get_script_prefix()) :]


def budget_free(view):
    """Mark a view that does not belong to a budget (login, people, the list of budgets)."""
    view.budget_free = True
    return view


def default_budget(request: HttpRequest):
    """The budget last used in this session, else the person's first one."""
    budgets = request.user.budgets.all()
    last = request.session.get("budget")
    return (budgets.filter(pk=last).first() if last else None) or budgets.first()


class BudgetMiddleware:
    """Serve each budget under ``/b/<id>/`` and check that the person may use it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        request.budget = None
        request.budget_id = None
        match = BUDGET_PATH.match(request.path_info)
        if match is None:
            return self.get_response(request)
        if match["rest"] is None:
            return HttpResponseRedirect(request.path + "/")
        previous = get_script_prefix()
        request.budget_id = int(match["id"])
        request.path_info = match["rest"]
        set_script_prefix(f"{root_prefix()}b/{request.budget_id}/")
        try:
            return self.get_response(request)
        finally:
            set_script_prefix(previous)

    def process_view(self, request: HttpRequest, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return None  # the login pages; everything else is redirected to them first
        if request.budget_id is not None:
            budget = request.user.budgets.filter(pk=request.budget_id).first()
            if budget is None:
                raise Http404("No such budget")
            request.budget = budget
            if request.session.get("budget") != budget.pk:
                request.session["budget"] = budget.pk
            return None
        if getattr(view_func, "budget_free", False):
            return None
        # A budget page without a budget in its address: open it in the last used budget.
        budget = default_budget(request)
        if budget is None:
            return redirect("budgets")
        query = request.META.get("QUERY_STRING", "")
        target = budget_url(budget.pk, request.path_info)
        return HttpResponseRedirect(f"{target}?{query}" if query else target)
