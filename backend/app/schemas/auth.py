from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StudentProfile(BaseModel):
    id: UUID
    user_id: UUID
    email: EmailStr
    display_name: str | None = None
    grade_id: UUID
    grade_name: str
    is_admin: bool = False


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str | None = Field(default=None, max_length=255)
    grade_id: UUID


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    grade_id: UUID | None = None


class AuthResponse(BaseModel):
    student: StudentProfile


class GradeResponse(BaseModel):
    id: UUID
    name: str
