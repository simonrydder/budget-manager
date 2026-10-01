"""Budget settings and the people who can log in."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.forms import SetPasswordForm
from django.shortcuts import get_object_or_404, redirect, render

from budget_manager.ledger import services
from budget_manager.ledger.forms import NewUserForm, SettingsForm
from budget_manager.ledger.models import BudgetSettings


def settings_view(request):
    config = BudgetSettings.load()
    started = services.last_closed() is not None
    form = SettingsForm(request.POST or None, instance=config, started=started)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Settings saved.")
        return redirect("settings")
    return render(request, "ledger/settings.html", {"form": form, "started": started})


def user_list(request):
    User = get_user_model()
    form = NewUserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"{user.username} can now log in.")
        return redirect("users")
    users = User.objects.order_by("username")
    return render(request, "ledger/users/list.html", {"form": form, "users": users})


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


def user_delete(request, pk: int):
    user = get_object_or_404(get_user_model(), pk=pk)
    blocked = "You cannot delete yourself." if user == request.user else None
    if request.method == "POST" and not blocked:
        user.delete()
        messages.success(request, f"{user.username} can no longer log in.")
        return redirect("users")
    return render(
        request, "ledger/confirm_delete.html", {"object": user, "blocked": blocked, "kind": "user"}
    )
