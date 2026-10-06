from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, ForeignKey
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