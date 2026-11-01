import datetime as dt
from fastapi import HTTPException
from sqlalchemy import func
from .models import Booking, Equipment

ACTIVE = ("booked", "confirmed", "issued")
LATE_RATE = 1.5  # штраф за сутки просрочки = 150% суточной цены


def today():
    return dt.date.today()


def status_of(b):
    return "overdue" if b.status == "issued" and b.end < today() else b.status


def free_units(s, eq, start, end, skip=None):
    """Сколько единиц свободно на весь период (консервативно: сумма пересекающихся броней)."""
    q = s.query(func.coalesce(func.sum(Booking.qty), 0)).filter(
        Booking.equipment_id == eq.id, Booking.status.in_(ACTIVE),
        Booking.start <= end, Booking.end >= start)
    if skip:
        q = q.filter(Booking.id != skip)
    return eq.usable - q.scalar()


def make_booking(s, user, eid, start, end, qty):
    eq = s.get(Equipment, eid)
    if not eq:
        raise HTTPException(404, "Оборудование не найдено")
    if start < today():
        raise HTTPException(400, "Нельзя бронировать на прошедшие даты")
    if end < start:
        raise HTTPException(400, "Дата возврата раньше даты начала")
    if (end - start).days >= 60:
        raise HTTPException(400, "Максимальный срок аренды — 60 суток")
    free = free_units(s, eq, start, end)
    if qty > free:
        raise HTTPException(409, f"На эти даты свободно только {max(free, 0)} шт.")
    days = (end - start).days + 1
    b = Booking(user_id=user.id, equipment_id=eq.id, qty=qty, start=start, end=end,
                total=round(days * eq.price_per_day * qty, 2))
    s.add(b)
    s.commit()
    return b


def step(b, action):
    flow = {"confirm": ("booked", "confirmed"), "issue": ("confirmed", "issued")}
    need, new = flow[action]
    if b.status != need:
        raise HTTPException(409, "Действие недоступно для текущего статуса брони")
    b.status = new


def finish(b, damage, note):
    if b.status != "issued":
        raise HTTPException(409, "Вернуть можно только выданное оборудование")
    late_days = max(0, (today() - b.end).days)
    late = late_days * b.equipment.price_per_day * b.qty * LATE_RATE
    b.fine = round(late + damage, 2)
    b.note = note
    b.status = "returned"
