import os, datetime as dt, collections, jwt, bcrypt
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func
from .models import Base, engine, Session, User, Category, Equipment, Booking, WriteOff, Review
from . import services as svc

SECRET = os.getenv("SECRET_KEY", "dev-secret-change-me-in-production-0123456789")
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def seed():
    with Session() as s:
        if s.query(User).first():
            return
        h = lambda p: bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
        s.add_all([User(name="Администратор", email="admin@rent.local", pw=h("admin123"), role="admin"),
                   User(name="Менеджер", email="manager@rent.local", pw=h("manager123"), role="manager"),
                   User(name="Клиент", email="client@rent.local", pw=h("client123"))])
        cats = {n: Category(name=n, icon=i) for n, i in
                [("Колёса", "🚴"), ("Лагерь", "⛺"), ("Инструмент", "🔨")]}
        s.add_all(cats.values())
        s.flush()
        for n, c, p, k, d, ph in [
            ("Велосипед Повелителя Скал", "Колёса", 900, 6, "Горный, алюминиевая рама, 21 скорость, шлем в комплекте", "velosiped"),
            ("BMX «Укротитель Рампы»", "Колёса", 800, 5, "Усиленная рама, пеги, для скейт-парка", "bmx"),
            ("Электросамокат «Городской Метеор»", "Колёса", 700, 5, "До 25 км/ч, запас хода 30 км", "samokat"),
            ("Ролики «Ночной Гонщик»", "Колёса", 450, 6, "Раздвижные, размеры 36–45, защита в комплекте", "rolik"),
            ("Палатка «Дом Странника»", "Лагерь", 600, 5, "4-местная, трёхсезонная, тамбур, лёгкая сборка", "palatka"),
            ("Горелка «Малый Вулкан»", "Лагерь", 250, 10, "Газовая, компактная, ветрозащита, пьезоподжиг", "burner"),
            ("Рюкзак «Хранитель Троп»", "Лагерь", 300, 8, "80 л, анатомическая спинка, дождевик", "ryukzak"),
            ("Перфоратор «Громобой»", "Инструмент", 800, 4, "SDS+, 3 режима, набор буров", "perforator"),
            ("Шлифмашина «Искрогрыз»", "Инструмент", 500, 5, "Угловая, 125 мм, регулировка оборотов", "shlifmashina"),
            ("Пистолет автомойки «Водопад»", "Инструмент", 450, 6, "Для мойки высокого давления, пенная насадка", "mojka")]:
            s.add(Equipment(name=n, category_id=cats[c].id, price_per_day=p, stock_total=k, description=d,
                            photo=f"/static/img/{ph}.jpg"))
        s.commit()


@asynccontextmanager
async def lifespan(_):
    Base.metadata.create_all(engine)
    seed()
    yield


app = FastAPI(title="ПрокатПро", lifespan=lifespan)


def db():
    with Session() as s:
        yield s


def make_token(u):
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=12)
    return jwt.encode({"sub": str(u.id), "exp": exp}, SECRET, "HS256")


def current(authorization: str = Header(None), s=Depends(db)):
    try:
        u = s.get(User, int(jwt.decode(authorization.split()[1], SECRET, ["HS256"])["sub"]))
    except Exception:
        u = None
    if not u:
        raise HTTPException(401, "Войдите в аккаунт")
    return u


def need(*roles):
    def dep(u=Depends(current)):
        if u.role not in roles:
            raise HTTPException(403, "Недостаточно прав")
        return u
    return dep


class Reg(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    email: str = Field(pattern=EMAIL, max_length=120)
    password: str = Field(min_length=6, max_length=72)


class Login(BaseModel):
    email: str
    password: str


class BookIn(BaseModel):
    equipment_id: int
    start: dt.date
    end: dt.date
    qty: int = Field(1, ge=1, le=50)


class Ret(BaseModel):
    damage_fine: float = Field(0, ge=0, le=1_000_000)
    note: str = Field("", max_length=300)


class EquipIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    category_id: int
    price_per_day: float = Field(gt=0, le=1_000_000)
    stock_total: int = Field(ge=0, le=10_000)
    in_repair: int = Field(0, ge=0)
    written_off: int = Field(0, ge=0)
    description: str = Field("", max_length=300)
    photo: str = Field("", max_length=200)


class CatIn(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    icon: str = Field("📦", max_length=4)


class WriteIn(BaseModel):
    qty: int = Field(ge=1, le=10_000)
    reason: str = Field(min_length=3, max_length=200)


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field("", max_length=300)


class NoteIn(BaseModel):
    note: str = Field("", max_length=300)


class RoleIn(BaseModel):
    role: str = Field(pattern="^(client|manager|admin)$")


def user_out(u):
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role}


def ratings(s):
    rows = s.query(Review.equipment_id, func.avg(Review.rating), func.count(Review.id)).group_by(Review.equipment_id).all()
    return {r[0]: (float(r[1]), r[2]) for r in rows}


def eq_out(e, free=None, rv=None):
    return {"rating": round(rv[0], 1) if rv else 0, "reviews": rv[1] if rv else 0, "id": e.id, "name": e.name, "description": e.description, "photo": e.photo,
            "category_id": e.category_id, "category": e.category.name, "icon": e.category.icon,
            "price_per_day": e.price_per_day, "stock_total": e.stock_total, "in_repair": e.in_repair,
            "written_off": e.written_off, "usable": e.usable, "free": e.usable if free is None else max(free, 0)}


def b_out(b):
    return {"id": b.id, "user": b.user.name, "equipment": b.equipment.name, "icon": b.equipment.category.icon,
            "qty": b.qty, "start": b.start.isoformat(), "end": b.end.isoformat(), "status": svc.status_of(b),
            "total": b.total, "fine": b.fine, "note": b.note, "issue_note": b.issue_note}


@app.post("/api/register")
def register(d: Reg, s=Depends(db)):
    email = d.email.lower()
    if s.query(User).filter_by(email=email).first():
        raise HTTPException(409, "Этот email уже зарегистрирован")
    u = User(name=d.name.strip(), email=email, pw=bcrypt.hashpw(d.password.encode(), bcrypt.gensalt()).decode())
    s.add(u)
    s.commit()
    return {"token": make_token(u), "user": user_out(u)}


@app.post("/api/login")
def login(d: Login, s=Depends(db)):
    u = s.query(User).filter_by(email=d.email.lower()).first()
    if not u or not bcrypt.checkpw(d.password.encode()[:72], u.pw.encode()):
        raise HTTPException(401, "Неверный email или пароль")
    return {"token": make_token(u), "user": user_out(u)}


@app.get("/api/me")
def me(u=Depends(current)):
    return user_out(u)


@app.get("/api/categories")
def categories(s=Depends(db)):
    return [{"id": c.id, "name": c.name, "icon": c.icon} for c in s.query(Category).order_by(Category.id)]


@app.post("/api/categories")
def add_cat(d: CatIn, s=Depends(db), _=Depends(need("admin"))):
    if s.query(Category).filter_by(name=d.name).first():
        raise HTTPException(409, "Такая категория уже есть")
    s.add(Category(name=d.name, icon=d.icon))
    s.commit()
    return {"ok": True}


@app.put("/api/categories/{cid}")
def edit_cat(cid: int, d: CatIn, s=Depends(db), _=Depends(need("admin"))):
    c = s.get(Category, cid)
    if not c:
        raise HTTPException(404, "Категория не найдена")
    if s.query(Category).filter(Category.name == d.name, Category.id != cid).first():
        raise HTTPException(409, "Такая категория уже есть")
    c.name, c.icon = d.name, d.icon
    s.commit()
    return {"ok": True}


@app.get("/api/equipment")
def equipment(q: str = "", category_id: int = 0, start: dt.date = None, end: dt.date = None, s=Depends(db)):
    qs = s.query(Equipment)
    if category_id:
        qs = qs.filter_by(category_id=category_id)
    items = qs.order_by(Equipment.id).all()
    if q:  # регистронезависимый поиск в Python: SQLite не умеет lower() для кириллицы
        items = [e for e in items if q.strip().casefold() in e.name.casefold()]
    ok = start and end and end >= start
    rm = ratings(s)
    return [eq_out(e, svc.free_units(s, e, start, end) if ok else None, rm.get(e.id)) for e in items]


@app.get("/api/equipment/{eid}/reviews")
def reviews(eid: int, s=Depends(db)):
    if not s.get(Equipment, eid):
        raise HTTPException(404, "Оборудование не найдено")
    rows = s.query(Review).filter_by(equipment_id=eid).order_by(Review.id.desc()).all()
    return [{"user": r.user.name, "rating": r.rating, "text": r.text, "day": r.day.isoformat()} for r in rows]


@app.post("/api/equipment/{eid}/reviews")
def add_review(eid: int, d: ReviewIn, s=Depends(db), u=Depends(current)):
    if not s.get(Equipment, eid):
        raise HTTPException(404, "Оборудование не найдено")
    r = s.query(Review).filter_by(user_id=u.id, equipment_id=eid).first()
    if r:
        r.rating, r.text, r.day = d.rating, d.text.strip(), dt.date.today()
    else:
        s.add(Review(user_id=u.id, equipment_id=eid, rating=d.rating, text=d.text.strip()))
    s.commit()
    avg, n = ratings(s).get(eid, (0, 0))
    return {"rating": round(avg, 1), "reviews": n}


@app.post("/api/equipment")
def add_eq(d: EquipIn, s=Depends(db), _=Depends(need("admin"))):
    if d.in_repair + d.written_off > d.stock_total:
        raise HTTPException(400, "Ремонт и списание не могут превышать общий остаток")
    if not s.get(Category, d.category_id):
        raise HTTPException(404, "Категория не найдена")
    e = Equipment(**d.model_dump())
    s.add(e)
    s.commit()
    return eq_out(e)


@app.put("/api/equipment/{eid}")
def edit_eq(eid: int, d: EquipIn, s=Depends(db), _=Depends(need("admin"))):
    e = s.get(Equipment, eid)
    if not e:
        raise HTTPException(404, "Оборудование не найдено")
    if d.in_repair + d.written_off > d.stock_total:
        raise HTTPException(400, "Ремонт и списание не могут превышать общий остаток")
    for k, v in d.model_dump().items():
        setattr(e, k, v)
    s.commit()
    return eq_out(e)


@app.post("/api/equipment/{eid}/writeoff")
def write_off(eid: int, d: WriteIn, s=Depends(db), _=Depends(need("admin"))):
    e = s.get(Equipment, eid)
    if not e:
        raise HTTPException(404, "Оборудование не найдено")
    if d.qty > e.usable:
        raise HTTPException(400, f"Можно списать не больше {e.usable} шт.")
    e.written_off += d.qty
    s.add(WriteOff(equipment_id=e.id, qty=d.qty, reason=d.reason.strip()))
    s.commit()
    return eq_out(e)


@app.get("/api/writeoffs")
def writeoffs(s=Depends(db), _=Depends(need("admin"))):
    return [{"id": w.id, "equipment": w.equipment.name, "qty": w.qty, "reason": w.reason, "day": w.day.isoformat()}
            for w in s.query(WriteOff).order_by(WriteOff.id.desc()).limit(30)]


@app.post("/api/bookings")
def book(d: BookIn, s=Depends(db), u=Depends(need("client", "manager", "admin"))):
    return b_out(svc.make_booking(s, u, d.equipment_id, d.start, d.end, d.qty))


@app.get("/api/bookings/my")
def my_bookings(s=Depends(db), u=Depends(current)):
    return [b_out(b) for b in s.query(Booking).filter_by(user_id=u.id).order_by(Booking.id.desc())]


@app.get("/api/bookings")
def all_bookings(s=Depends(db), _=Depends(need("manager", "admin"))):
    return [b_out(b) for b in s.query(Booking).order_by(Booking.id.desc())]


def get_booking(s, bid):
    b = s.get(Booking, bid)
    if not b:
        raise HTTPException(404, "Бронь не найдена")
    return b


@app.post("/api/bookings/{bid}/cancel")
def cancel(bid: int, s=Depends(db), u=Depends(current)):
    b = get_booking(s, bid)
    if b.user_id != u.id and u.role == "client":
        raise HTTPException(403, "Это чужая бронь")
    if b.status not in ("booked", "confirmed"):
        raise HTTPException(409, "Отменить можно только бронь, которая ещё не выдана")
    b.status = "cancelled"
    s.commit()
    return b_out(b)


@app.post("/api/bookings/{bid}/confirm")
def confirm(bid: int, s=Depends(db), _=Depends(need("manager", "admin"))):
    b = get_booking(s, bid)
    svc.step(b, "confirm")
    s.commit()
    return b_out(b)


@app.post("/api/bookings/{bid}/issue")
def issue(bid: int, d: NoteIn, s=Depends(db), _=Depends(need("manager", "admin"))):
    b = get_booking(s, bid)
    svc.step(b, "issue")
    b.issue_note = d.note
    s.commit()
    return b_out(b)


@app.post("/api/bookings/{bid}/return")
def give_back(bid: int, d: Ret, s=Depends(db), _=Depends(need("manager", "admin"))):
    b = get_booking(s, bid)
    svc.finish(b, d.damage_fine, d.note)
    s.commit()
    return b_out(b)


@app.get("/api/users")
def users(s=Depends(db), _=Depends(need("admin"))):
    return [user_out(u) for u in s.query(User).order_by(User.id)]


@app.put("/api/users/{uid}/role")
def set_role(uid: int, d: RoleIn, s=Depends(db), a=Depends(need("admin"))):
    u = s.get(User, uid)
    if not u:
        raise HTTPException(404, "Пользователь не найден")
    if u.id == a.id:
        raise HTTPException(400, "Нельзя менять собственную роль")
    u.role = d.role
    s.commit()
    return user_out(u)


@app.get("/api/stats")
def stats(s=Depends(db), _=Depends(need("admin"))):
    bs = [b for b in s.query(Booking).all()]
    by_status = collections.Counter(svc.status_of(b) for b in bs)
    by_month, top = collections.Counter(), collections.Counter()
    for b in bs:
        if b.status != "cancelled":
            by_month[b.start.strftime("%Y-%m")] += b.total + b.fine
            top[b.equipment.name] += b.qty
    return {"by_status": by_status, "by_month": dict(sorted(by_month.items())),
            "top": top.most_common(5), "fines": sum(b.fine for b in bs),
            "revenue": sum(b.total + b.fine for b in bs if b.status in ("issued", "returned"))}


@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "static", "index.html"))


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "static")), name="static")
