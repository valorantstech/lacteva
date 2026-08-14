"""Identity module — API schemas (commands/queries DTOs)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterUserCommand(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    locale: str = "en"


class UserView(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    email: str
    full_name: str
    locale: str
    #: DEMO-014 — the clock this person reads timestamps in, or null for the
    #: organization's. Display only; never a business date.
    timezone: str | None = None
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
