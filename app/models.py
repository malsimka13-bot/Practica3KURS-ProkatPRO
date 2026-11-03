import os, datetime as dt
from sqlalchemy import create_engine, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

URL = os.getenv("DATABASE_URL", "sqlite:///./rental.db")
engine = create_engine(URL, connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {})
Session = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True, index=True)
    pw: Mapped[str]
    role: Mapped[str] = mapped_column(default="client")  # client | manager | admin


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    icon: Mapped[str] = mapped_column(default="📦")


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        CheckConstraint("price_per_day > 0"),
        CheckConstraint("stock_total >= 0 AND in_repair >= 0 AND written_off >= 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    description: Mapped[str] = mapped_column(default="")
    photo: Mapped[str] = mapped_column(default="")
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    price_per_day: Mapped[float]
    stock_total: Mapped[int]
    in_repair: Mapped[int] = mapped_column(default=0)
    written_off: Mapped[int] = mapped_column(default=0)
    category = relationship(Category)

    @property
    def usable(self):
        return self.stock_total - self.in_repair - self.written_off


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (CheckConstraint("qty > 0"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    qty: Mapped[int]
    start: Mapped[dt.date]
    end: Mapped[dt.date]
    status: Mapped[str] = mapped_column(default="booked")  # booked|confirmed|issued|returned|cancelled
    total: Mapped[float]
    fine: Mapped[float] = mapped_column(default=0)
    note: Mapped[str] = mapped_column(default="")
    issue_note: Mapped[str] = mapped_column(default="")
    user = relationship(User)
    equipment = relationship(Equipment)


class WriteOff(Base):
    __tablename__ = "writeoffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    qty: Mapped[int]
    reason: Mapped[str]
    day: Mapped[dt.date] = mapped_column(default=dt.date.today)
    equipment = relationship(Equipment)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5"), UniqueConstraint("user_id", "equipment_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    rating: Mapped[int]
    text: Mapped[str] = mapped_column(default="")
    day: Mapped[dt.date] = mapped_column(default=dt.date.today)
    user = relationship(User)
