"""Move money between General Savings and the expenses any day, not only at a month-end."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from budget_manager.engine import CloseError, Role, format_amount
from budget_manager.ledger import services
from budget_manager.ledger.forms import RefundForm
from budget_manager.ledger.models import Account, Move
from budget_manager.ledger.views.common import today


def balance(request):
    form = RefundForm(
        request.POST or None,
        initial={"account": Account.objects.filter(role=Role.NEMKONTO.value).first()},
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        Move.objects.create(
            kind=Move.Type.REFUND,
            account=data["account"],
            amount=data["amount"],
            note=data["note"],
            created_by=request.user,
        )
        messages.success(request, f"{format_amount(data['amount'])} is waiting to be moved.")
        return redirect("balance")
    state = services.build_state()
    plan = services.balancing(today(), state)
    context = {
        "plan": plan,
        "form": form,
        "started": services.budget_started(),
        "next_month": state.month,
        "recent": Move.objects.filter(done=True).select_related("expense", "account")[:20],
    }
    return render(request, "ledger/balance.html", context)


@require_POST
def balance_made(request):
    try:
        plan = services.make_moves(today(), request.user)
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
    get_object_or_404(Move, pk=pk, done=False).delete()
    messages.success(request, "Cancelled.")
    return redirect("balance")


@require_POST
def move_undo(request, pk: int):
    move = get_object_or_404(Move, pk=pk, done=True)
    try:
        services.undo_move(move)
    except CloseError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Undone. The move is waiting again.")
    return redirect("balance")
