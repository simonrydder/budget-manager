"""A budget's settings, and the people who can log in."""

from __future__ import annotations

import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.forms import SetPasswordForm
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

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
        "update_waiting": _update_waiting(),
    }
    return render(request, "ledger/settings.html", context)


#: A request the launcher has not picked up within this time is shown as not taken.
UPDATE_PATIENCE = 10 * 60


def _update_waiting() -> bool:
    """True while an update asked for from the app has not been picked up by the launcher."""
    try:
        age = time.time() - settings.UPDATE_REQUEST_FILE.stat().st_mtime
    except OSError:
        return False
    return age < UPDATE_PATIENCE


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
