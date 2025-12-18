# schemas.py
from pydantic import BaseModel
from typing import Optional
from enum import Enum

# 역할 정의
class UserRole(str, Enum):
    ADMIN = "ADMIN"
    INSTRUCTOR = "INSTRUCTOR"
    STUDENT = "STUDENT"

# 회원가입 할 때 받는 데이터
class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    role: UserRole

# 사용자 정보를 보여줄 때 사용하는 데이터 (비밀번호 제외)
class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str

    class Config:
        from_attributes = True

# --- schemas.py 맨 아래에 추가 ---
from datetime import datetime

# 강의 생성할 때 입력받는 정보
class CourseCreate(BaseModel):
    title: str
    semester: str # 예: "2025-2"

# 강의 정보를 보여줄 때 사용하는 양식
class CourseResponse(BaseModel):
    id: int
    title: str
    semester: str
    instructor_id: int
    class Config:
        from_attributes = True

# 주차(세션) 생성 정보
class SessionCreate(BaseModel):
    week_number: int
    session_date: datetime # 예: "2025-12-01T14:00:00"
    attendance_method: str = "ELECTRONIC" # 기본값 전자출결

    # --- schemas.py 맨 아래에 추가 ---

# 학생이 출석 체크할 때 보내는 정보 (지금은 비어있어도 됨)
class AttendanceCreate(BaseModel):
    pass 

# 출석 결과 보여주기
class AttendanceResponse(BaseModel):
    id: int
    session_id: int
    student_id: int
    status: int # 1: 출석
    checked_at: datetime
    
    class Config:
        from_attributes = True

# 주차(세션) 정보 보여주기 (강의 목록에 포함될 때 사용)
class SessionResponse(BaseModel):
    id: int
    week_number: int
    session_date: datetime
    is_open: bool
    
    class Config:
        from_attributes = True

        # --- schemas.py 맨 아래에 추가 ---

# 공결 신청 응답
class ExcuseResponse(BaseModel):
    id: int
    student_id: int
    reason: str
    status: str
    
    class Config:
        from_attributes = True

        # --- schemas.py 맨 아래에 추가 ---

class StudentReport(BaseModel):
    student_name: str
    total_sessions: int # 전체 수업 수
    attended_count: int # 출석(1)+공결(4) 횟수
    attendance_rate: float # 출석률 (%)

class CourseReportResponse(BaseModel):
    course_title: str
    reports: list[StudentReport]