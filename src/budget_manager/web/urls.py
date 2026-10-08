"""Every page except logging in, the list of budgets and the people is part of a budget and is
served under ``/b/<id>/`` (see ``budget_manager.ledger.scope``)."""

from django.contrib.auth import views as auth_views
from django.urls import path

from budget_manager.ledger.scope import budget_free
from budget_manager.ledger.views import (
    admin,
    balance,
    budgets,
    home,
    manage,
    month_end,
    reports,
    setup,
)

urlpatterns = [
    path("", home.dashboard, name="dashboard"),
    path("setup/", home.first_login, name="first-login"),
    path("login/", budget_free(home.LoginView.as_view()), name="login"),
    path("logout/", budget_free(auth_views.LogoutView.as_view()), name="logout"),
    path("done-starting/", home.start_transfers_done, name="start-transfers-done"),
    # Setting up a budget, step by step
    path("start/", setup.resume, name="start"),
    path("start/accounts/", setup.accounts, name="setup-accounts"),
    path("start/expenses/", setup.expenses, name="setup-expenses"),
    path("start/summary/", setup.summary, name="setup-summary"),
    path("start/income/", setup.income, name="setup-income"),
    path("start/transfers/", setup.transfers, name="setup-transfers"),
    # Month-end checklist
    path("month-end/", month_end.month_end, name="month-end"),
    path("month-end/<str:month>/spending/", month_end.spending, name="month-end-spending"),
    path("month-end/<str:month>/interest/", month_end.interest, name="month-end-interest"),
    path("month-end/<str:month>/income/", month_end.income, name="month-end-income"),
    path("month-end/<str:month>/transfers/", month_end.transfers, name="month-end-transfers"),
    path("month-end/<str:month>/check/", month_end.check, name="month-end-check"),
    path("month-end/<str:month>/close/", month_end.finish, name="month-end-close"),
    path("closes/", month_end.close_list, name="closes"),
    path("closes/<str:month>/", month_end.close_detail, name="close-detail"),
    path("closes/<str:month>/reopen/", month_end.close_reopen, name="close-reopen"),
    # Moving money between month-ends
    path("balance/", balance.balance, name="balance"),
    path("balance/made/", balance.balance_made, name="balance-made"),
    path("balance/<int:pk>/cancel/", balance.move_cancel, name="move-cancel"),
    path("balance/<int:pk>/undo/", balance.move_undo, name="move-undo"),
    # Management
    path("accounts/", manage.account_list, name="accounts"),
    path("accounts/new/", manage.account_form, name="account-new"),
    path("accounts/<int:pk>/edit/", manage.account_form, name="account-edit"),
    path("accounts/<int:pk>/delete/", manage.account_delete, name="account-delete"),
    path("accounts/correct/<str:target>/", manage.correction, name="correction"),
    path("expenses/", manage.expense_board, name="expenses"),
    path("expenses/new/", manage.expense_form, name="expense-new"),
    path("expenses/<int:pk>/", manage.expense_detail, name="expense-detail"),
    path("expenses/<int:pk>/edit/", manage.expense_form, name="expense-edit"),
    path("expenses/<int:pk>/end/", manage.expense_end, name="expense-end"),
    path("expenses/<int:pk>/delete/", manage.expense_delete, name="expense-delete"),
    path("expenses/<int:pk>/move/", manage.expense_move, name="expense-move"),
    path("expenses/<int:pk>/release/", manage.expense_release, name="expense-release"),
    path("categories/", manage.category_list, name="categories"),
    path("categories/<int:pk>/edit/", manage.category_edit, name="category-edit"),
    path("categories/<int:pk>/delete/", manage.category_delete, name="category-delete"),
    path(
        "categories/<int:pk>/move/<str:direction>/",
        manage.category_move,
        name="category-move",
    ),
    path("income/", manage.income_list, name="income"),
    path("income/new/", manage.income_form, name="income-new"),
    path("income/<int:pk>/edit/", manage.income_form, name="income-edit"),
    path("income/<int:pk>/delete/", manage.income_delete, name="income-delete"),
    # Reports
    path("forecast/", reports.forecast, name="forecast"),
    path("history/", reports.history, name="history"),
    # The budget's settings
    path("settings/", admin.settings_view, name="settings"),
    path("settings/delete/", budgets.budget_delete, name="budget-delete"),
    # Budgets and people (not part of one budget)
    path("budgets/", budgets.budget_list, name="budgets"),
    path("budgets/new/", budgets.budget_new, name="budget-new"),
    path("budgets/<int:pk>/copy/", budgets.budget_copy, name="budget-copy"),
    path("users/", admin.user_list, name="users"),
    path("users/<int:pk>/password/", admin.user_password, name="user-password"),
    path("users/<int:pk>/delete/", admin.user_delete, name="user-delete"),
]
