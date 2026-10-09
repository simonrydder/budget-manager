"""The one-file start serves only this computer, so there is no login."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from budget_manager.ledger.models import Budget

pytestmark = pytest.mark.django_db


@pytest.fixture
def local(settings, monkeypatch):
    settings.LOCAL_ONLY = True
    monkeypatch.setenv("USERNAME", "Kim")


def test_the_first_visit_signs_in_and_starts_the_setup(local):
    browser = Client()
    response = browser.get("/", follow=True)
    user = get_user_model().objects.get()
    assert (user.username, user.first_name, user.has_usable_password()) == ("Kim", "Kim", False)
    assert Budget.objects.get().members.get() == user
    page = response.content.decode()
    assert "Set up" in page
    assert "Log out" not in page
    assert ">People</a>" not in page  # nobody else can log in
    # There is nothing to log in to.
    assert browser.get("/login/").url == "/"
    assert browser.get("/setup/").url == "/"
    # A second browser on this computer is the same person.
    Client().get("/")
    assert get_user_model().objects.count() == 1


def test_it_signs_in_as_the_person_already_there(local, user):
    Client().get("/")
    assert get_user_model().objects.get() == user


def test_another_device_still_has_to_log_in(local, user):
    response = Client().get("/", REMOTE_ADDR="192.168.1.20")
    assert response.url == "/login/?next=/"


def test_without_local_mode_the_login_stays(user):
    assert Client().get("/").url == "/login/?next=/"
