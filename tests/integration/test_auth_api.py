from datetime import timedelta

import jwt

from tests.conftest import FAKE_JWT_SECRET
from tests.helpers import register_and_login


def count_users(conn):
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def test_register_created(client, conn):
    r = client.post("/auth/register", json={"email": "Milena@Example.com", "password": "clave-segura-1"})
    assert r.status_code == 201
    assert r.json() == {"id": 1, "email": "milena@example.com"}
    assert count_users(conn) == 1


def test_register_duplicate_case_insensitive(client, conn):
    client.post("/auth/register", json={"email": "milena@example.com", "password": "clave-segura-1"})
    r = client.post("/auth/register", json={"email": "MILENA@EXAMPLE.COM", "password": "clave-segura-1"})
    assert r.status_code == 409
    assert r.json() == {"detail": "El email ya está registrado"}
    assert count_users(conn) == 1


def test_register_invalid(client, conn):
    for body in (
        {"email": "no-es-email", "password": "clave-segura-1"},
        {"email": "a@example.com", "password": "x" * 7},
        {"email": "a@example.com", "password": "x" * 129},
    ):
        assert client.post("/auth/register", json=body).status_code == 422
    assert count_users(conn) == 0
    assert client.post("/auth/register", json={"email": "a@example.com", "password": "x" * 128}).status_code == 201
    assert client.post("/auth/register", json={"email": "b@example.com", "password": "x" * 8}).status_code == 201


def test_login(client, clock):
    client.post("/auth/register", json={"email": "milena@example.com", "password": "clave-segura-1"})
    r = client.post("/auth/login", json={"email": "milena@example.com", "password": "clave-segura-1"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"access_token", "token_type", "expires_at"}
    assert body["token_type"] == "bearer"
    assert body["expires_at"] == (clock.now() + timedelta(hours=2)).isoformat()
    payload = jwt.decode(body["access_token"], FAKE_JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False})
    assert payload["exp"] - payload["iat"] == 7200


def test_login_wrong_credentials(client):
    client.post("/auth/register", json={"email": "milena@example.com", "password": "clave-segura-1"})
    for body in (
        {"email": "milena@example.com", "password": "incorrecta"},
        {"email": "otro@example.com", "password": "clave-segura-1"},
    ):
        r = client.post("/auth/login", json=body)
        assert r.status_code == 401
        assert r.json() == {"detail": "Credenciales inválidas"}


def test_unauthenticated(client, clock):
    headers = register_and_login(client, "milena@example.com")
    for h in ({}, {"Authorization": "Bearer basura"}, {"Authorization": "Token x"}):
        r = client.get("/profile", headers=h)
        assert r.status_code == 401
        assert r.json() == {"detail": "No autenticado"}
    assert client.get("/profile", headers=headers).status_code == 200
    clock.advance(timedelta(hours=2, minutes=1))
    r = client.get("/profile", headers=headers)
    assert r.status_code == 401
    assert r.json() == {"detail": "No autenticado"}


def test_token_renewal_until_7_days(client, clock):
    login_time = clock.now()
    headers = register_and_login(client, "milena@example.com")
    r = client.get("/profile", headers=headers)
    first = r.headers["X-Session-Token"]
    clock.advance(timedelta(hours=1))
    r = client.get("/profile", headers={"Authorization": f"Bearer {first}"})
    second = r.headers["X-Session-Token"]
    exp1 = jwt.decode(first, FAKE_JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False})["exp"]
    exp2 = jwt.decode(second, FAKE_JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False})["exp"]
    assert exp2 == exp1 + 3600

    token = second
    while clock.now() + timedelta(hours=1, minutes=50) - login_time < timedelta(days=7):
        clock.advance(timedelta(hours=1, minutes=50))
        r = client.get("/profile", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        token = r.headers["X-Session-Token"]
    clock.set(login_time + timedelta(days=7))
    r = client.get("/profile", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
