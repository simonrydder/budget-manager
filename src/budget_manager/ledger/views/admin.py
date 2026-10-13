"""A budget's settings, and the people who can log in."""

from __future__ import annotations

import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.forms import SetPasswordForm
from django.core.cache import cache
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from budget_manager import cli
from budget_manager.ledger import services
from budget_manager.ledger.forms import NewUserForm, SettingsForm
from budget_manager.ledger.models import Budget
from budget_manager.ledger.scope import budget_free


def settings_view(request):
    budget = request.budget
    form = SettingsForm(request.POST or None, instance=budget, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Settings saved.")
        return redirect("settings")
    context = {
        "form": form,
        "started": services.budget_started(budget),
        "running": services.last_closed(budget) is not None,
        "everyday": services.everyday_estimate(budget),
        "updater": settings.UPDATER,
        "version": settings.VERSION,
        "commit": settings.COMMIT,
        "check_minutes": settings.CHECK_MINUTES,
        "update_request": _update_request(),
        "update_failed": settings.UPDATE_FAILED_FILE.exists(),
        "newest": _newest_version(),
        "launcher_log": _launcher_log(),
    }
    if context["newest"]:
        context["outdated"] = cli.is_newer(context["newest"], settings.VERSION)
    return render(request, "ledger/settings.html", context)


#: The launcher looks for an update request every few seconds, so one that is still there
#: after this long was not picked up: the launcher is not running.
UPDATE_PATIENCE = 2 * 60


def _update_request() -> str | None:
    """The state of an update asked for from the app: "waiting" while it is on its way,
    "stuck" when the launcher did not pick it up, or None."""
    try:
        age = time.time() - settings.UPDATE_REQUEST_FILE.stat().st_mtime
    except OSError:
        return None
    return "waiting" if age < UPDATE_PATIENCE else "stuck"


def _newest_version() -> str | None:
    """The newest version on GitHub, looked up at most every 10 minutes; None if unknown."""
    if not settings.CHECK_NEWEST:
        return None
    newest = cache.get("newest-version")
    if newest is None:
        try:
            newest = cli.newest_version(timeout=3)
        except Exception:  # offline, GitHub unavailable, ...
            newest = ""
        cache.set("newest-version", newest, 10 * 60)
    return newest or None


def _launcher_log(lines: int = 40) -> str:
    """The end of the Windows launcher's log, which says what each update did."""
    try:
        with settings.LAUNCHER_LOG.open("rb") as log:
            log.seek(0, 2)
            log.seek(max(0, log.tell() - 16_000))
            text = log.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:])


@require_POST
def request_update(request):
    """Ask the launcher on the PC to update to the newest version and restart. The page answers
    first; the launcher notices the request within seconds."""
    if not settings.UPDATER:
        messages.error(request, "This copy of Budget Manager is not run by the Windows launcher.")
        return redirect("settings")
    settings.UPDATE_REQUEST_FILE.write_text(f"{timezone.now().isoformat()} {request.user}\n")
    messages.success(
        request,
        "Updating to the newest version. Budget Manager restarts in a minute or two; "
        "reload the page then.",
    )
    return redirect("settings")


@budget_free
def user_list(request):
    User = get_user_model()
    mine = request.user.budgets.all()
    current = getattr(request, "budget", None)
    initial = {"budgets": [current.pk]} if current else {}
    form = NewUserForm(request.POST or None, budgets=mine, initial=initial)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"{user.username} can now log in.")
        return redirect("users")
    people = []
    for person in User.objects.order_by("username").prefetch_related("budgets"):
        shared = [budget for budget in person.budgets.all() if budget in mine]
        people.append({"person": person, "budgets": shared})
    return render(request, "ledger/users/list.html", {"form": form, "people": people})


@budget_free
def user_password(request, pk: int):
    user = get_object_or_404(get_user_model(), pk=pk)
    form = SetPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        if user == request.user:
            update_session_auth_hash(request, user)
        messages.success(request, f"Password changed for {user.username}.")
        return redirect("users")
    return render(request, "ledger/users/password.html", {"form": form, "person": user})


@budget_free
def user_delete(request, pk: int):
    user = get_object_or_404(get_user_model(), pk=pk)
    blocked = "You cannot delete yourself." if user == request.user else None
    alone = Budget.objects.annotate(people=Count("members")).filter(members=user, people=1)
    if alone.exists() and not blocked:
        blocked = (
            f"{user.username} is the only person who can use one of the budgets. Give someone "
            "else access to it under its Settings first, or delete it."
        )
    if request.method == "POST" and not blocked:
        user.delete()
        messages.success(request, f"{user.username} can no longer log in.")
        return redirect("users")
    return render(
        request, "ledger/confirm_delete.html", {"object": user, "blocked": blocked, "kind": "user"}
    )
