import enum


class Role(str, enum.Enum):
    ADMIN = "Admin"
    MANAGER = "Manager"
    STAFF = "Staff"


class UserStatus(str, enum.Enum):
    INVITED = "invited"  # invite sent, password not set yet
    ACTIVE = "active"
    REVOKED = "revoked"