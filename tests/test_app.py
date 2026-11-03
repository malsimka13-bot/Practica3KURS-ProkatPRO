import datetime as dt
from app.models import Session, Booking

TODAY = dt.date.today()
D = lambda n: (TODAY + dt.timedelta(days=n)).isoformat()
# Демо-данные: оборудование №1 — «Велосипед Повелителя Скал», 900 ₽/сут, 6 шт.; пользователи: 1 admin, 2 manager, 3 client


def book(c, h, start, end, qty=1, eid=1):
    return c.post("/api/bookings", json={"equipment_id": eid, "start": start, "end": end, "qty": qty}, headers=h)


# ---------- регистрация и авторизация ----------
def test_register_ok(c):
    r = c.post("/api/register", json={"name": "Иван", "email": "Ivan@Test.ru", "password": "secret1"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "client" and r.json()["user"]["email"] == "ivan@test.ru"


def test_register_duplicate_email(c):
    assert c.post("/api/register", json={"name": "Иван", "email": "client@rent.local", "password": "secret1"}).status_code == 409


def test_register_validation(c):
    ok = {"name": "Иван", "email": "a@b.ru", "password": "secret1"}
    for bad in ({"email": "не-почта"}, {"password": "12345"}, {"name": "И"}, {"password": "x" * 73}):
        assert c.post("/api/register", json={**ok, **bad}).status_code == 422, bad


def test_login_wrong_password(c):
    assert c.post("/api/login", json={"email": "client@rent.local", "password": "wrong"}).status_code == 401


def test_no_token_or_garbage_token(c):
    assert c.get("/api/me").status_code == 401
    assert c.get("/api/me", headers={"Authorization": "Bearer abc"}).status_code == 401


# ---------- разграничение ролей ----------
def test_roles_are_enforced(c, client_h, manager_h):
    assert c.get("/api/users", headers=client_h).status_code == 403
    assert c.get("/api/bookings", headers=client_h).status_code == 403
    assert c.get("/api/stats", headers=manager_h).status_code == 403
    assert c.post("/api/equipment", headers=manager_h, json={}).status_code == 403
    assert c.get("/api/bookings", headers=manager_h).status_code == 200


# ---------- бронирование: стоимость и границы ----------
def test_booking_total(c, client_h):
    r = book(c, client_h, D(1), D(3), qty=2)  # 3 суток × 2 шт. × 900
    assert r.status_code == 200 and r.json()["total"] == 5400 and r.json()["status"] == "booked"


def test_one_day_booking_today(c, client_h):
    assert book(c, client_h, D(0), D(0)).json()["total"] == 900


def test_booking_past_date_rejected(c, client_h):
    assert book(c, client_h, D(-1), D(1)).status_code == 400


def test_booking_end_before_start_rejected(c, client_h):
    assert book(c, client_h, D(3), D(1)).status_code == 400


def test_booking_max_duration_boundary(c, client_h):
    assert book(c, client_h, D(1), D(60)).status_code == 200  # 60 суток — можно
    assert book(c, client_h, D(1), D(61), eid=2).status_code == 400  # 61 сутки — нельзя


def test_booking_qty_boundaries(c, client_h):
    assert book(c, client_h, D(1), D(2), qty=0).status_code == 422
    assert book(c, client_h, D(1), D(2), qty=51).status_code == 422
    assert book(c, client_h, D(1), D(2), qty=7).status_code == 409  # на складе 6
    assert book(c, client_h, D(1), D(2), qty=6).status_code == 200  # ровно весь остаток


def test_booking_unknown_equipment(c, client_h):
    assert book(c, client_h, D(1), D(2), eid=999).status_code == 404


# ---------- пересечение дат ----------
def test_overlapping_bookings(c, client_h):
    assert book(c, client_h, D(1), D(3), qty=6).status_code == 200
    r = book(c, client_h, D(3), D(5))  # пересечение в один день
    assert r.status_code == 409 and "свободно только 0" in r.json()["detail"]
    assert book(c, client_h, D(0), D(1)).status_code == 409  # пересечение слева
    assert book(c, client_h, D(2), D(2)).status_code == 409  # внутри периода
    assert book(c, client_h, D(4), D(5)).status_code == 200  # встык, без пересечения


def test_partial_availability(c, client_h):
    book(c, client_h, D(1), D(3), qty=4)
    assert book(c, client_h, D(2), D(4), qty=3).status_code == 409
    assert book(c, client_h, D(2), D(4), qty=2).status_code == 200


def test_cancel_frees_units(c, client_h):
    bid = book(c, client_h, D(1), D(3), qty=6).json()["id"]
    assert c.post(f"/api/bookings/{bid}/cancel", headers=client_h).status_code == 200
    assert book(c, client_h, D(1), D(3), qty=6).status_code == 200


def test_catalog_shows_free_units_for_dates(c, client_h):
    book(c, client_h, D(1), D(3), qty=4)
    free = lambda q: next(e for e in c.get("/api/equipment?" + q).json() if e["id"] == 1)["free"]
    assert free(f"start={D(2)}&end={D(2)}") == 2
    assert free(f"start={D(5)}&end={D(6)}") == 6


def test_catalog_search_and_category(c):
    assert [e["name"] for e in c.get("/api/equipment?q=ПАЛАТКА").json()] == ["Палатка «Дом Странника»"]
    assert len(c.get("/api/equipment?category_id=3").json()) == 3
    assert c.get("/api/equipment?q=нет-такого").json() == []


# ---------- жизненный цикл брони ----------
def test_full_flow_and_wrong_order(c, client_h, manager_h):
    bid = book(c, client_h, D(1), D(2)).json()["id"]
    assert c.post(f"/api/bookings/{bid}/issue", json={}, headers=manager_h).status_code == 409  # без подтверждения
    assert c.post(f"/api/bookings/{bid}/confirm", headers=client_h).status_code == 403
    assert c.post(f"/api/bookings/{bid}/confirm", headers=manager_h).json()["status"] == "confirmed"
    assert c.post(f"/api/bookings/{bid}/return", json={}, headers=manager_h).status_code == 409  # ещё не выдано
    r = c.post(f"/api/bookings/{bid}/issue", json={"note": "исправно"}, headers=manager_h).json()
    assert r["status"] == "issued" and r["issue_note"] == "исправно"
    r = c.post(f"/api/bookings/{bid}/return", json={"damage_fine": 300, "note": "царапина"}, headers=manager_h).json()
    assert r["status"] == "returned" and r["fine"] == 300 and r["note"] == "царапина"
    assert c.post(f"/api/bookings/{bid}/cancel", headers=client_h).status_code == 409  # уже возвращено


def test_cannot_cancel_foreign_booking(c, client_h):
    bid = book(c, client_h, D(1), D(2)).json()["id"]
    other = c.post("/api/register", json={"name": "Пётр", "email": "p@test.ru", "password": "secret1"}).json()["token"]
    assert c.post(f"/api/bookings/{bid}/cancel", headers={"Authorization": "Bearer " + other}).status_code == 403


# ---------- штрафы ----------
def test_late_return_fine_and_overdue_status(c, client_h, manager_h):
    with Session() as s:
        s.add(Booking(user_id=3, equipment_id=1, qty=1, start=TODAY - dt.timedelta(5), end=TODAY - dt.timedelta(2),
                      status="issued", total=3600))
        s.commit()
    b = c.get("/api/bookings/my", headers=client_h).json()[0]
    assert b["status"] == "overdue"
    r = c.post(f"/api/bookings/{b['id']}/return", json={"damage_fine": 500}, headers=manager_h).json()
    assert r["fine"] == 2 * 900 * 1.5 + 500  # 2 суток просрочки × 150% + повреждение
    assert r["status"] == "returned"


def test_damage_fine_cannot_be_negative(c, client_h, manager_h):
    bid = book(c, client_h, D(0), D(1)).json()["id"]
    c.post(f"/api/bookings/{bid}/confirm", headers=manager_h)
    c.post(f"/api/bookings/{bid}/issue", json={}, headers=manager_h)
    assert c.post(f"/api/bookings/{bid}/return", json={"damage_fine": -5}, headers=manager_h).status_code == 422


# ---------- склад, каталог, пользователи ----------
def test_writeoff_reduces_stock_and_availability(c, admin_h, client_h):
    assert c.post("/api/equipment/1/writeoff", json={"qty": 7, "reason": "слишком много"}, headers=admin_h).status_code == 400
    r = c.post("/api/equipment/1/writeoff", json={"qty": 2, "reason": "сломаны рамы"}, headers=admin_h).json()
    assert r["written_off"] == 2 and r["usable"] == 4
    assert book(c, client_h, D(1), D(2), qty=5).status_code == 409
    assert c.get("/api/writeoffs", headers=admin_h).json()[0]["reason"] == "сломаны рамы"


def test_repair_plus_writeoff_cannot_exceed_stock(c, admin_h):
    body = {"name": "Велосипед Повелителя Скал", "category_id": 1, "price_per_day": 900, "stock_total": 6, "in_repair": 4, "written_off": 3}
    assert c.put("/api/equipment/1", json=body, headers=admin_h).status_code == 400


def test_equipment_validation(c, admin_h):
    ok = {"name": "Лыжи", "category_id": 1, "price_per_day": 300, "stock_total": 3}
    assert c.post("/api/equipment", json=ok, headers=admin_h).status_code == 200
    for bad in ({"price_per_day": 0}, {"price_per_day": -1}, {"stock_total": -1}, {"name": "Л"}):
        assert c.post("/api/equipment", json={**ok, **bad}, headers=admin_h).status_code == 422, bad
    assert c.post("/api/equipment", json={**ok, "category_id": 999}, headers=admin_h).status_code == 404


def test_categories_admin(c, admin_h):
    assert c.post("/api/categories", json={"name": "Колёса"}, headers=admin_h).status_code == 409
    assert c.post("/api/categories", json={"name": "Музыка", "icon": "🎸"}, headers=admin_h).status_code == 200
    assert c.put("/api/categories/1", json={"name": "Лагерь"}, headers=admin_h).status_code == 409


def test_role_management(c, admin_h, client_h):
    assert c.put("/api/users/3/role", json={"role": "manager"}, headers=admin_h).json()["role"] == "manager"
    assert c.put("/api/users/3/role", json={"role": "boss"}, headers=admin_h).status_code == 422
    assert c.put("/api/users/1/role", json={"role": "client"}, headers=admin_h).status_code == 400  # себе нельзя


def test_stats(c, admin_h, client_h):
    book(c, client_h, D(1), D(2))
    s = c.get("/api/stats", headers=admin_h).json()
    assert s["by_status"] == {"booked": 1} and s["top"][0][0] == "Велосипед Повелителя Скал"


# ---------- отзывы и оценки (кресты) ----------
def test_review_requires_login(c):
    assert c.post("/api/equipment/1/reviews", json={"rating": 5, "text": "ок"}).status_code == 401


def test_review_rating_bounds_and_unknown_item(c, client_h):
    for bad in (0, 6, -1):
        assert c.post("/api/equipment/1/reviews", json={"rating": bad}, headers=client_h).status_code == 422
    assert c.post("/api/equipment/1/reviews", json={"rating": 1}, headers=client_h).status_code == 200
    assert c.post("/api/equipment/1/reviews", json={"rating": 5}, headers=client_h).status_code == 200
    assert c.post("/api/equipment/999/reviews", json={"rating": 5}, headers=client_h).status_code == 404


def test_review_average_and_one_review_per_user(c, client_h, manager_h):
    c.post("/api/equipment/1/reviews", json={"rating": 5, "text": "отлично"}, headers=client_h)
    r = c.post("/api/equipment/1/reviews", json={"rating": 2}, headers=manager_h).json()
    assert r == {"rating": 3.5, "reviews": 2}
    r = c.post("/api/equipment/1/reviews", json={"rating": 1, "text": "передумал"}, headers=client_h).json()
    assert r == {"rating": 1.5, "reviews": 2}  # повторный отзыв обновляет прежний
    item = next(e for e in c.get("/api/equipment").json() if e["id"] == 1)
    assert item["rating"] == 1.5 and item["reviews"] == 2
    assert next(e for e in c.get("/api/equipment").json() if e["id"] == 2)["reviews"] == 0


def test_reviews_list(c, client_h):
    c.post("/api/equipment/1/reviews", json={"rating": 4, "text": "хороший прокат"}, headers=client_h)
    lst = c.get("/api/equipment/1/reviews").json()
    assert lst[0]["user"] == "Клиент" and lst[0]["rating"] == 4 and lst[0]["text"] == "хороший прокат"
    assert c.get("/api/equipment/999/reviews").status_code == 404
