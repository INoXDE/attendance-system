# schemas.py
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum
from datetime import datetime

class UserRole(str, Enum):
    ADMIN = "ADMIN"
    INSTRUCTOR = "INSTRUCTOR"
    STUDENT = "STUDENT"

class DepartmentCreate(BaseModel):
    name: str

class DepartmentResponse(BaseModel):
    id: int
    name: str
    class Config: from_attributes = True

class UserUpdate(BaseModel):
    name: str
    email: str
    role: UserRole
    department_id: Optional[int] = None
    student_number: Optional[str] = None
    password: Optional[str] = None

class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    student_number: Optional[str] = None
    role: UserRole
    department_id: Optional[int] = None

class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    student_number: Optional[str] = None
    role: str
    department_id: Optional[int] = None
    class Config: from_attributes = True

class CourseUpdate(BaseModel):
    title: str
    course_type: str
    day_of_week: str
    department_id: Optional[int] = None
    instructor_id: Optional[int] = None

class CourseCreate(BaseModel):
    title: str
    semester: str
    department_id: int # 학과 필수
    instructor_id: int # [NEW] 교수 필수
    course_type: str = "전공"
    day_of_week: str = "Mon"

class CourseResponse(BaseModel):
    id: int
    title: str
    semester: str
    course_type: str
    day_of_week: str # [NEW]
    instructor_id: int
    department_id: Optional[int] = None
    class Config: from_attributes = True

# --- 이하 동일 ---
class SessionCreate(BaseModel):
    week_number: int
    session_date: datetime
    attendance_method: str = "ELECTRONIC"

class SessionUpdate(BaseModel):
    session_date: datetime

class AttendanceUpdate(BaseModel):
    student_id: int
    status: int

class SessionResponse(BaseModel):
    id: int
    week_number: int
    session_date: datetime
    is_open: bool
    is_holiday: bool # [NEW] 프론트엔드에 공휴일 정보 전달
    auth_code: Optional[str] = None
    attendance_method: str
    class Config: from_attributes = True

class StudentReport(BaseModel):
    student_name: str
    total_sessions: int
    attended_count: int
    attendance_rate: float

class CourseReportResponse(BaseModel):
    course_title: str
    reports: List[StudentReport]

class AuditLogResponse(BaseModel):
    id: int
    actor_id: Optional[int]
    target_type: str
    action: str
    details: Optional[str]
    created_at: datetime
    class Config: from_attributes = True