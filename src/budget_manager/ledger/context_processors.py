from django.db import DatabaseError

from budget_manager.ledger import services


def navigation(request):
    """The budget being looked at, the person's other budgets and the status for the sidebar."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    budget = getattr(request, "budget", None)
    try:
        context = {"current_budget": budget, "my_budgets": list(user.budgets.all())}
        if budget is None:
            return context
        started = services.budget_started(budget)
        context["nav_started"] = started
        if not started:
            context["nav_setup_step"] = min(budget.setup_step, 5)
            return context
        month = services.next_close_month(budget)
        draft = services.draft_close(budget, month)
        context.update(
            {
                "nav_close_month": month,
                "nav_close_step": draft.step if draft else None,
                "nav_transfer_day": (month - 1).last_day(),
                "nav_waiting": budget.moves.filter(done=False).count(),
            }
        )
    except DatabaseError:
        return {}
    return context
