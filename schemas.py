# schemas.py
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum
from datetime import datetime

class UserRole(str, Enum):
    ADMIN = "ADMIN"
    INSTRUCTOR = "INSTRUCTOR"
    STUDENT = "STUDENT"

class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    student_number: Optional[str] = None
    role: UserRole

class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    student_number: Optional[str] = None
    role: str
    class Config:
        from_attributes = True

class CourseCreate(BaseModel):
    title: str
    semester: str

class CourseResponse(BaseModel):
    id: int
    title: str
    semester: str
    instructor_id: int
    class Config:
        from_attributes = True

class SessionCreate(BaseModel):
    week_number: int
    session_date: datetime
    attendance_method: str = "ELECTRONIC"

# [보완] 교수님이 출석 상태 변경할 때 사용
class AttendanceUpdate(BaseModel):
    student_id: int
    status: int # 0~4

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
    class Config:
        from_attributes = True

class ExcuseResponse(BaseModel):
    id: int
    student_id: int
    reason: str
    status: str
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

# [보완] 관리자 감사 로그 조회용
class AuditLogResponse(BaseModel):
    id: int
    actor_id: Optional[int]
    target_type: str
    action: str
    created_at: datetime
    class Config:
        from_attributes = True