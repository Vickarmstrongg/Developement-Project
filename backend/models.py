from sqlalchemy import (
    Column, Integer, SmallInteger, String, Date, DateTime,
    Time, Boolean, Numeric, ForeignKey
)
from database import Base


class Student(Base):
    __tablename__ = "students"

    id_number = Column(String, primary_key=True)
    last_name = Column(String)
    first_name = Column(String)
    dob = Column(Date)
    gender = Column(String)
    email = Column(String)
    phone = Column(String)
    address = Column(String)


class VendorType(Base):
    __tablename__ = "vendor_types"

    type_id = Column(Integer, primary_key=True)
    name = Column(String)


class Vendor(Base):
    __tablename__ = "vendors"

    vendor_id = Column(Integer, primary_key=True)
    name = Column(String)
    address = Column(String)
    gps = Column(String)
    type_id = Column(Integer, ForeignKey("vendor_types.type_id"))


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(Integer, primary_key=True)
    student_id = Column(String, ForeignKey("students.id_number"))
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id"))
    datetime = Column(DateTime)
    value = Column(Numeric)
    discount = Column(Numeric)


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    password_hash = Column(String)
    role = Column(String)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id"))


class ContextEvent(Base):
    __tablename__ = "context_events"

    context_id = Column(String, primary_key=True)
    category = Column(String)
    subcategory = Column(String)
    title = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    notes = Column(String)


class ContextualEvent(Base):
    __tablename__ = "contextual_events"

    event_id = Column(Integer, primary_key=True)
    source_context_id = Column(String, unique=True)
    source_year = Column(SmallInteger)
    name = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    subcategory = Column(String)
    start_date = Column(Date, nullable=False)
    start_time = Column(Time)
    end_date = Column(Date, nullable=False)
    end_time = Column(Time)
    all_day = Column(Boolean)
    location = Column(String)
    campus = Column(String)
    faculty = Column(String)
    scope = Column(String)
    source = Column(String, nullable=False)
    source_organisation = Column(String)
    source_name = Column(String)
    source_file = Column(String)
    source_url = Column(String)
    source_page = Column(String)
    verification_status = Column(String)
    notes = Column(String)
    created_by_user_id = Column(
        Integer, ForeignKey("users.user_id")
    )
    updated_at = Column(DateTime(timezone=True), nullable=False)
