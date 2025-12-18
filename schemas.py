# schemas.py
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum
from datetime import datetime

class UserRole(str, Enum):
    ADMIN = "ADMIN"
    INSTRUCTOR = "INSTRUCTOR"
    STUDENT = "STUDENT"

# [NEW] 학과 정보
class DepartmentCreate(BaseModel):
    name: str

class DepartmentResponse(BaseModel):
    id: int
    name: str
    class Config:
        from_attributes = True

# 회원가입/생성 (학과 ID 추가)
class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    student_number: Optional[str] = None
    role: UserRole
    department_id: Optional[int] = None # [NEW]

class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    student_number: Optional[str] = None
    role: str
    department_id: Optional[int] = None
    class Config:
        from_attributes = True

# 강의 생성 (학과 ID 추가)
class CourseCreate(BaseModel):
    title: str
    semester: str
    department_id: Optional[int] = None # [NEW]

class CourseResponse(BaseModel):
    id: int
    title: str
    semester: str
    instructor_id: int
    department_id: Optional[int] = None
    class Config:
        from_attributes = True

# --- 기존 유지 ---
class SessionCreate(BaseModel):
    week_number: int
    session_date: datetime
    attendance_method: str = "ELECTRONIC"

class AttendanceUpdate(BaseModel):
    student_id: int
    status: int

class AttendanceCreate(BaseModel):
    pass 

class AttendanceResponse(BaseModel):
    id: int
    session_id: int
    student_id: int
    status: int
    checked_at: datetime
    class Config:
        from_attributes = True

class SessionResponse(BaseModel):
    id: int
    week_number: int
    session_date: datetime
    is_open: bool
    auth_code: Optional[str] = None
    class Config:
        from_attributes = True

class StudentReport(BaseModel):
    student_name: str
    total_sessions: int
    attended_count: int
    attendance_rate: float

class CourseReportResponse(BaseModel):
    course_title: str
    reports: List[StudentReport]

# [NEW] 감사 로그 응답용
class AuditLogResponse(BaseModel):
    id: int
    actor_id: Optional[int]
    target_type: str
    action: str
    details: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True