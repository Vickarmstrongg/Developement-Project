from sqlalchemy import (
    Column, Integer, SmallInteger, String, Date, DateTime,
    Time, Boolean, Numeric, ForeignKey
)
from database import Base
from sqlalchemy.orm import relationship


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

        # --- added for access control (matches the supporting-tables migration) ---
    full_name = Column(String)
    status = Column(String)                       # invited | active | revoked
    token_hash = Column(String)
    token_expires_at = Column(DateTime(timezone=True))
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked = Column(Boolean, nullable=False, default=False)

    vendor_links = relationship(
        "UserVendorLink", back_populates="user",
        cascade="all, delete-orphan", lazy="selectin",
    )

    @property
    def vendor_ids(self):
        return sorted(link.vendor_id for link in self.vendor_links)

    @property
    def all_vendors(self):
        return self.role == "Admin"



class UserVendorLink(Base):
    # vendor_id has no foreign key on purpose
    __tablename__ = "user_vendor_links"

    user_id = Column(Integer, ForeignKey("users.user_id"), primary_key=True)
    vendor_id = Column(Integer, primary_key=True)

    user = relationship("User", back_populates="vendor_links")



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

class Notification(Base):
    __tablename__ = "notifications"

    notification_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    vendor_id = Column(Integer, nullable=False)
    message = Column(String)
    trigger_type = Column(String)
    is_read = Column(Boolean, nullable=False, default=False)
    is_pinned = Column(Boolean, nullable=False, default=False)
    is_cleared = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class ReportExport(Base):
    __tablename__ = "report_exports"

    report_id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer)  # no foreign key, same as user_vendor_links
    generated_by_user_id = Column(Integer, ForeignKey("users.user_id"))
    report_type = Column(String)
    period_start = Column(Date)
    period_end = Column(Date)
    generated_at = Column(DateTime(timezone=True), nullable=False)
    generated_by = relationship("User", lazy="joined")
    generated_by = relationship("User", lazy="joined")
