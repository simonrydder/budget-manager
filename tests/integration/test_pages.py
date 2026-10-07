from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from budget_manager.ledger.models import Category, Expense
from budget_manager.web.middleware import is_allowed, parse_networks

from .test_month_end import month_end

pytestmark = pytest.mark.django_db


def test_login_is_required(user):
    anonymous = Client()
    response = anonymous.get("/accounts/")
    assert response.status_code == 302
    assert response.url == "/login/?next=/accounts/"
    assert anonymous.get("/login/").status_code == 200


def test_first_visit_creates_the_first_login(db):
    visitor = Client()
    assert visitor.get("/login/").url == "/setup/"
    response = visitor.post(
        "/setup/",
        {
            "username": "sam",
            "first_name": "Sam",
            "password1": "correct horse battery",
            "password2": "correct horse battery",
        },
    )
    assert response.url == "/"
    assert get_user_model().objects.filter(username="sam").exists()
    assert visitor.get("/").status_code == 200
    assert Client().get("/setup/").url == "/login/"


@pytest.mark.parametrize(
    ("address", "allowed"),
    [
        ("127.0.0.1", True),
        ("192.168.1.20", True),
        ("10.0.0.7", True),
        ("172.20.1.1", True),
        ("::1", True),
        ("::ffff:192.168.1.20", True),
        ("fe80::1%eth0", True),
        ("8.8.8.8", False),
        ("172.32.0.1", False),
        ("2001:db8::1", False),
        ("", False),
        ("not an ip", False),
    ],
)
def test_network_check(address, allowed, settings):
    assert is_allowed(address, parse_networks(settings.ALLOWED_NETWORKS)) is allowed


def test_requests_from_the_internet_are_refused(client):
    response = client.get("/", REMOTE_ADDR="8.8.8.8")
    assert response.status_code == 403
    assert b"only available on the local network" in response.content
    assert Client().get("/login/", REMOTE_ADDR="8.8.4.4").status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/accounts/",
        "/accounts/new/",
        "/expenses/",
        "/expenses/?group=account",
        "/expenses/new/",
        "/categories/",
        "/income/",
        "/income/new/",
        "/forecast/",
        "/forecast/?month=2025-09",
        "/forecast/?month=bad",
        "/history/",
        "/history/?by=expense&year=2025",
        "/history/?by=account&year=2025",
        "/settings/",
        "/users/",
        "/closes/",
        "/accounts/correct/nemkonto/",
    ],
)
def test_pages_render(client, budget, path):
    month_end(client, "2025-05")
    month_end(client, "2025-06", spending={"Rent": "10.000", "Groceries": "4.100"})
    response = client.get(path)
    assert response.status_code == 200


def test_expense_pages_render(client, budget):
    month_end(client, "2025-05")
    rent = Expense.objects.get(name="Rent")
    for path in (
        f"/expenses/{rent.id}/",
        f"/expenses/{rent.id}/edit/",
        f"/expenses/{rent.id}/end/",
    ):
        assert client.get(path).status_code == 200


def test_add_expense_with_danish_amounts(client, budget, accounts):
    response = client.post(
        "/expenses/new/",
        {
            "name": "Car insurance",
            "amount": "4.812,50",
            "interval_months": "12",
            "first_due": "2025-11-01",
            "kind": "fixed",
            "account": accounts["Budget"].id,
            "category": "",
            "starting_balance": "1.000",
            "end_date": "",
            "notes": "",
        },
    )
    assert response.status_code == 302
    car = Expense.objects.get(name="Car insurance")
    assert car.amount == 481250
    assert car.starting_balance == 100000
    assert car.category is None
    assert car.start_month is None  # before the first month-end: counts from the start


def test_expense_added_later_starts_at_the_next_month_end(client, budget, accounts):
    month_end(client, "2025-05")
    client.post(
        "/expenses/new/",
        {
            "name": "Gym",
            "amount": "300",
            "interval_months": "1",
            "first_due": "2025-06-10",
            "kind": "fixed",
            "account": accounts["Budget"].id,
        },
    )
    assert Expense.objects.get(name="Gym").start_month == date(2025, 6, 1)


def test_expense_form_rejects_bad_input(client, budget, accounts):
    response = client.post(
        "/expenses/new/",
        {
            "name": "Broken",
            "amount": "-5",
            "interval_months": "1",
            "first_due": "2025-06-10",
            "end_date": "2025-01-01",
            "kind": "fixed",
            "account": accounts["NemKonto"].id,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert set(form.errors) == {"amount", "account", "end_date"}


def test_drag_and_drop_moves_expenses(client, budget, accounts):
    rent = Expense.objects.get(name="Rent")
    insurance = Category.objects.get(name="Insurance")
    json = {"HTTP_ACCEPT": "application/json"}
    response = client.post(
        f"/expenses/{rent.id}/move/", {"field": "category", "value": insurance.id}, **json
    )
    assert response.json()["ok"]
    rent.refresh_from_db()
    assert rent.category == insurance

    client.post(f"/expenses/{rent.id}/move/", {"field": "category", "value": ""}, **json)
    rent.refresh_from_db()
    assert rent.category is None

    response = client.post(
        f"/expenses/{rent.id}/move/", {"field": "account", "value": accounts["Food"].id}, **json
    )
    assert response.json()["ok"]
    rent.refresh_from_db()
    assert rent.account == accounts["Food"]

    response = client.post(
        f"/expenses/{rent.id}/move/", {"field": "account", "value": accounts["NemKonto"].id}, **json
    )
    assert response.status_code == 400
    assert client.get(f"/expenses/{rent.id}/move/").status_code == 405


def test_moving_an_expense_with_money_warns_about_the_bank(client, budget, accounts):
    month_end(client, "2025-05")
    rent = Expense.objects.get(name="Rent")
    response = client.post(
        f"/expenses/{rent.id}/move/",
        {"field": "account", "value": accounts["Food"].id},
        HTTP_ACCEPT="application/json",
    )
    assert "Move its balance of 10.000,00 from Budget to Food" in response.json()["message"]


def test_expense_with_history_cannot_be_deleted(client, budget):
    month_end(client, "2025-05")
    rent = Expense.objects.get(name="Rent")
    client.post(f"/expenses/{rent.id}/delete/")
    assert Expense.objects.filter(pk=rent.pk).exists()
    response = client.post(f"/expenses/{rent.id}/end/", {"end_date": "2025-08-31"})
    assert response.status_code == 302
    rent.refresh_from_db()
    assert rent.end_date == date(2025, 8, 31)


def test_nemkonto_and_savings_account_are_protected(client, accounts):
    client.post(f"/accounts/{accounts['NemKonto'].id}/delete/")
    client.post(f"/accounts/{accounts['Savings'].id}/delete/")
    assert set(a.name for a in accounts.values()) == {"NemKonto", "Budget", "Food", "Savings"}
    assert all(type(a).objects.filter(pk=a.pk).exists() for a in accounts.values())


def test_general_savings_can_move_to_another_account(client, accounts):
    response = client.post(
        f"/accounts/{accounts['Budget'].id}/edit/",
        {"name": "Budget", "holds_general_savings": "on"},
    )
    assert response.status_code == 302
    accounts["Budget"].refresh_from_db()
    accounts["Savings"].refresh_from_db()
    assert accounts["Budget"].holds_general_savings
    assert not accounts["Savings"].holds_general_savings


def test_categories_can_be_added_reordered_and_deleted(client):
    client.post("/categories/", {"name": "Pets"})
    pets = Category.objects.get(name="Pets")
    before = list(Category.objects.values_list("name", flat=True))
    client.post(f"/categories/{pets.id}/move/up/")
    after = list(Category.objects.values_list("name", flat=True))
    assert after.index("Pets") == before.index("Pets") - 1
    client.post(f"/categories/{pets.id}/delete/")
    assert not Category.objects.filter(name="Pets").exists()


def test_people_can_be_added(client):
    response = client.post(
        "/users/",
        {
            "username": "sam",
            "first_name": "Sam",
            "password1": "correct horse battery",
            "password2": "correct horse battery",
        },
    )
    assert response.status_code == 302
    assert get_user_model().objects.filter(username="sam").exists()


def test_malformed_posts_do_not_crash(client, budget):
    month_end(client, "2025-05", close=False)
    response = client.post("/month-end/2025-05/transfers/", {"action": "tick", "account": "x"})
    assert response.status_code == 404
    client.post("/month-end/2025-05/close/")
    assert client.post("/closes/2025-05/", {"transfer": "nope"}).status_code == 404
    rent = Expense.objects.get(name="Rent")
    response = client.post(f"/expenses/{rent.id}/move/", {"field": "category", "value": "1; drop"})
    assert response.status_code == 400
    assert client.post("/categories/99999/move/up/").status_code == 404


def test_warning_when_expenses_exceed_income(client, budget, accounts):
    # Income 25.000; rent 10.000 + groceries 4.000 + holiday 30.000/12 = 16.500 a month.
    page = client.get("/expenses/new/")
    assert b"Room for 8.500 more a month" in page.content
    response = client.post(
        "/expenses/new/",
        {
            "name": "New car loan",
            "amount": "10.500",
            "interval_months": "1",
            "first_due": "2025-05-15",
            "kind": "fixed",
            "account": accounts["Budget"].id,
        },
        follow=True,
    )
    text = response.content.decode()
    assert "27.000,00 a month on average, 2.000,00 more than your expected income" in text
    # General Savings starts at 10.000: May to September, then it runs out.
    assert "covers 5 months and runs out in October 2025" in text
    assert "2.000,00 more than your expected income" in client.get("/").content.decode()


def test_no_warning_when_income_covers_expenses(client, budget):
    response = client.get("/", follow=True)
    assert "more than your expected income" not in response.content.decode()
