"""The list of budgets: open, create, copy and delete them."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from budget_manager.ledger import budgets, services
from budget_manager.ledger.forms import BudgetForm, CopyBudgetForm, DeleteBudgetForm
from budget_manager.ledger.models import Budget
from budget_manager.ledger.scope import budget_free, budget_reverse, global_url


def _status(budget: Budget) -> str:
    last = services.last_closed(budget)
    if last is not None:
        return f"Running · next month-end {_day(last.budget_month.last_day())}"
    if budget.started_on:
        first = budget.opening.last_day()
        return f"Started on {_day(budget.started_on)} · first month-end {_day(first)}"
    return f"Being set up · step {min(budget.setup_step, 5)} of 5"


def _day(value) -> str:
    return f"{value.day} {value:%b %Y}"


@budget_free
def budget_list(request):
    items = [
        {
            "budget": budget,
            "status": _status(budget),
            "people": [person.first_name or person.username for person in budget.members.all()],
            "current": budget.pk == request.session.get("budget"),
        }
        for budget in request.user.budgets.prefetch_related("members")
    ]
    form = BudgetForm(user=request.user)
    return render(request, "ledger/budgets/list.html", {"items": items, "form": form})


@budget_free
def budget_new(request):
    form = BudgetForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        budget = budgets.create_budget(data["name"], data["members"], request.user)
        messages.success(request, f"Created {budget.name}. Set it up step by step.")
        return redirect(budget_reverse(budget.pk, "start"))
    return render(request, "ledger/budgets/new.html", {"form": form})


@budget_free
def budget_copy(request, pk: int):
    source = get_object_or_404(Budget, pk=pk, members=request.user)
    form = CopyBudgetForm(request.POST or None, user=request.user, source=source)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        everything = data["what"] == CopyBudgetForm.EVERYTHING
        budget = budgets.copy_budget(
            source, data["name"], data["members"], request.user, everything=everything
        )
        if everything:
            messages.success(request, f"Copied {source.name} with all its history.")
            return redirect(budget.get_absolute_url())
        messages.success(
            request,
            f"Copied {source.name}. Check the accounts and expenses, then start the copy.",
        )
        return redirect(budget_reverse(budget.pk, "start"))
    return render(request, "ledger/budgets/copy.html", {"form": form, "source": source})


def budget_delete(request):
    budget = request.budget
    form = DeleteBudgetForm(request.POST or None, budget=budget)
    if request.method == "POST" and form.is_valid():
        name = budget.name
        budgets.delete_budget(budget)
        request.session.pop("budget", None)
        messages.success(request, f"Deleted the budget {name}.")
        return redirect(global_url("budgets"))
    return render(request, "ledger/budgets/delete.html", {"form": form})
