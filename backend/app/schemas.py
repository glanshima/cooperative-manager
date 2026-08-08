import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .models import MemberStatus, Gender


class MemberBase(BaseModel):
    psn: str
    name: str
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    gender: Optional[Gender] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    next_of_kin: Optional[str] = None
    next_of_kin_phone: Optional[str] = None
    status: MemberStatus = MemberStatus.FINANCIAL


class MemberCreate(MemberBase):
    pass


class MemberUpdate(BaseModel):
    name: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    gender: Optional[Gender] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    next_of_kin: Optional[str] = None
    next_of_kin_phone: Optional[str] = None
    status: Optional[MemberStatus] = None


class MemberOut(MemberBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
