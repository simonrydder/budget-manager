from django.db import DatabaseError

from budget_manager.ledger import services


def navigation(request):
    """Month-end status for the sidebar."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    try:
        month = services.next_close_month()
        draft = services.draft_close(month)
    except DatabaseError:
        return {}
    return {
        "nav_close_month": month,
        "nav_close_step": draft.step if draft else None,
        "nav_transfer_day": (month - 1).last_day(),
    }
