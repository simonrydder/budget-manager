"""Move money between General Savings and the expenses any day, not only at a month-end."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from budget_manager.engine import CloseError, format_amount
from budget_manager.ledger import services
from budget_manager.ledger.forms import OverdraftForm, RefundForm
from budget_manager.ledger.models import Move
from budget_manager.ledger.views.common import next_value, safe_next, today


def balance(request):
    budget = request.budget
    form = RefundForm(request.POST or None, budget=budget)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        Move.objects.create(
            budget=budget,
            kind=Move.Type.REFUND,
            account=data["account"],
            expense=data["expense"],
            amount=data["amount"],
            note=data["note"],
            created_by=request.user,
        )
        messages.success(request, f"{format_amount(data['amount'])} is waiting to be moved.")
        return redirect("balance")
    state = services.build_state(budget)
    plan = services.balancing(budget, today(), state)
    context = {
        "plan": plan,
        "form": form,
        "overdraft_form": OverdraftForm(budget=budget, prefix="overdraft"),
        "started": services.budget_started(budget),
        "next_month": state.month,
        "recent": budget.moves.filter(done=True).select_related("expense", "account")[:20],
    }
    return render(request, "ledger/balance.html", context)


def overdraft(request):
    """The bank covered an account that went below zero, by itself."""
    budget = request.budget
    form = OverdraftForm(request.POST or None, budget=budget, prefix="overdraft")
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            services.record_overdraft(
                budget,
                data["target"],
                data["expense"],
                data["source"],
                data["amount"],
                request.user,
                data["note"],
            )
        except CloseError as error:
            messages.error(request, str(error))
        else:
            messages.success(
                request,
                f"Recorded: the bank moved {format_amount(data['amount'])} from "
                f"{data['source'].name} to {data['target'].name}.",
            )
            return redirect(safe_next(request, "balance"))
    return render(request, "ledger/overdraft.html", {"form": form, "next": next_value(request)})


@require_POST
def balance_made(request):
    try:
        plan = services.make_moves(request.budget, today(), request.user)
    except CloseError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            f"Done. General Savings is now {format_amount(plan.general_savings_after)} and the "
            "expense balances are updated.",
        )
    return redirect("balance")


@require_POST
def move_cancel(request, pk: int):
    get_object_or_404(Move, pk=pk, done=False, budget=request.budget).delete()
    messages.success(request, "Cancelled.")
    return redirect("balance")


@require_POST
def move_undo(request, pk: int):
    move = get_object_or_404(Move, pk=pk, done=True, budget=request.budget)
    try:
        services.undo_move(move)
    except CloseError as error:
        messages.error(request, str(error))
    else:
        if move.kind == Move.Type.OVERDRAFT:
            messages.success(request, "Removed.")
        else:
            messages.success(request, "Undone. The move is waiting again.")
    return redirect("balance")
