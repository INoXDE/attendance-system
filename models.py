# models.py
from sqlalchemy import Column, Integer, String, ForeignKey, Enum, DateTime, Text, Boolean
from sqlalchemy.sql import func
from database import Base

# 사용자 모델 (PDF 31, 3~6번 항목: 관리자, 교원, 수강생)
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False) # 실제론 암호화 필요
    name = Column(String(50), nullable=False)
    role = Column(Enum('ADMIN', 'INSTRUCTOR', 'STUDENT'), nullable=False)
    created_at = Column(DateTime, default=func.now())

# 강의 모델 (PDF 32, 8번 항목: 2025년 2학기 기준)
class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    semester = Column(String(20), nullable=False) # 예: "2025-2"
    instructor_id = Column(Integer, ForeignKey("users.id"))

# --- models.py 맨 아래에 추가 ---

# 강의 세션(주차) 모델 [cite: 9, 33]
class ClassSession(Base):
    __tablename__ = "class_sessions"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    week_number = Column(Integer, nullable=False) # 1주차, 2주차...
    session_date = Column(DateTime, nullable=False) # 수업 날짜
    attendance_method = Column(Enum('ELECTRONIC', 'AUTH_CODE', 'CALL'), default='ELECTRONIC') # 출석 방식 [cite: 10]
    auth_code = Column(String(10), nullable=True) # 인증번호
    is_open = Column(Boolean, default=False) # 출석 시작 여부

# 수강신청 모델 
class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    joined_at = Column(DateTime, default=func.now())

    # --- models.py 맨 아래에 추가 ---

# 출석 기록 모델
class Attendance(Base):
    __tablename__ = "attendances"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Integer, default=1) # 1: 출석 (기본값)
    checked_at = Column(DateTime, default=func.now()) # 출석한 시간

    # --- models.py 맨 아래에 추가 ---

# 공결 신청 모델
class ExcuseRequest(Base):
    __tablename__ = "excuse_requests"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=False) # 사유
    file_path = Column(String(255), nullable=True) # 파일 저장 위치
    status = Column(Enum('PENDING', 'APPROVED', 'REJECTED'), default='PENDING') # 대기, 승인, 반려
    admin_comment = Column(Text, nullable=True) # 교수님 코멘트