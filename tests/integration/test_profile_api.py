from tests.helpers import register_and_login, seed_link, user_id_by_email

FULL = {
    "level": "intermedio",
    "frequency": 4,
    "target_distance_km": 10.0,
    "current_pace": "6:00",
    "city": "Rosario",
    "preferred_range": {"start": "07:00", "end": "09:00"},
    "send_time": "06:00",
}


def test_put_full_then_get(client):
    h = register_and_login(client, "milena@example.com")
    r = client.put("/profile", json=FULL, headers=h)
    assert r.status_code == 200
    assert r.json() == {**FULL, "telegram_linked": False}
    r = client.get("/profile", headers=h)
    assert r.status_code == 200
    assert r.json() == {**FULL, "telegram_linked": False}
    assert "X-Session-Token" in r.headers


def test_get_empty_profile(client):
    h = register_and_login(client, "milena@example.com")
    body = client.get("/profile", headers=h).json()
    assert all(v is None for k, v in body.items() if k != "telegram_linked")


def test_partial_put_changes_only_sent_fields(client):
    h = register_and_login(client, "milena@example.com")
    client.put("/profile", json=FULL, headers=h)
    r = client.put("/profile", json={"city": "Córdoba"}, headers=h)
    assert r.status_code == 200
    assert r.json() == {**FULL, "city": "Córdoba", "telegram_linked": False}


def test_invalid_field_among_valid_saves_nothing(client):
    h = register_and_login(client, "milena@example.com")
    client.put("/profile", json=FULL, headers=h)
    for bad in (
        {"city": "Mendoza", "frequency": 9},
        {"city": "Mendoza", "send_time": "10:00"},
        {"city": "Mendoza", "level": "experto"},
        {"city": "Mendoza", "current_pace": "6:60"},
        {"city": "Mendoza", "level": None},
    ):
        r = client.put("/profile", json=bad, headers=h)
        assert r.status_code == 422, bad
    assert client.get("/profile", headers=h).json() == {**FULL, "telegram_linked": False}


def test_level_changes_accepted(client):
    h = register_and_login(client, "milena@example.com")
    client.put("/profile", json=FULL, headers=h)
    assert client.put("/profile", json={"level": "novato"}, headers=h).status_code == 200
    assert client.put("/profile", json={"level": "avanzado"}, headers=h).status_code == 200
    assert client.get("/profile", headers=h).json()["level"] == "avanzado"


def test_novice_can_clear_pace(client):
    h = register_and_login(client, "milena@example.com")
    client.put("/profile", json={**FULL, "level": "novato"}, headers=h)
    r = client.put("/profile", json={"current_pace": None}, headers=h)
    assert r.status_code == 200
    assert r.json()["current_pace"] is None


def test_telegram_linked_flag(client, conn):
    h = register_and_login(client, "milena@example.com")
    assert client.get("/profile", headers=h).json()["telegram_linked"] is False
    seed_link(conn, user_id_by_email(conn, "milena@example.com"), 555)
    assert client.get("/profile", headers=h).json()["telegram_linked"] is True
