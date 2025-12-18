# models.py
from sqlalchemy import Column, Integer, String, ForeignKey, Enum, DateTime, Text, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

# [NEW] 0. 학과 모델
class Department(Base):
    __tablename__ = "departments"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False) # 예: 컴퓨터공학과
    
    # 관계 설정
    users = relationship("User", back_populates="department")
    courses = relationship("Course", back_populates="department")

# 1. 사용자 모델 (학과 연결 추가)
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    name = Column(String(50), nullable=False)
    student_number = Column(String(20), nullable=True)
    role = Column(Enum('ADMIN', 'INSTRUCTOR', 'STUDENT'), nullable=False)
    
    # [NEW] 소속 학과 ID
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    
    created_at = Column(DateTime, default=func.now())

    department = relationship("Department", back_populates="users")
    enrollments = relationship("Enrollment", back_populates="user")
    attendances = relationship("Attendance", back_populates="student")

# 2. 강의 모델 (학과 연결 추가)
class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    semester = Column(String(20), nullable=False)
    instructor_id = Column(Integer, ForeignKey("users.id"))
    
    # [NEW] 개설 학과 ID
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)

    instructor = relationship("User")
    department = relationship("Department", back_populates="courses")
    sessions = relationship("ClassSession", back_populates="course")
    enrollments = relationship("Enrollment", back_populates="course")

# --- 나머지 모델은 기존과 동일 ---
class ClassSession(Base):
    __tablename__ = "class_sessions"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    week_number = Column(Integer, nullable=False)
    session_date = Column(DateTime, nullable=False)
    attendance_method = Column(Enum('ELECTRONIC', 'AUTH_CODE', 'CALL'), default='ELECTRONIC')
    auth_code = Column(String(10), nullable=True)
    is_open = Column(Boolean, default=False)
    course = relationship("Course", back_populates="sessions")

class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    joined_at = Column(DateTime, default=func.now())
    user = relationship("User", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")

class Attendance(Base):
    __tablename__ = "attendances"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Integer, default=0)
    checked_at = Column(DateTime, default=func.now())
    student = relationship("User", back_populates="attendances")

class ExcuseRequest(Base):
    __tablename__ = "excuse_requests"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=False)
    file_path = Column(String(255), nullable=True)
    status = Column(Enum('PENDING', 'APPROVED', 'REJECTED'), default='PENDING')
    admin_comment = Column(Text, nullable=True)

# 7. 감사 로그 (시스템 상태 확인용)
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id")) # 누가
    target_type = Column(String(50)) # 무엇을 (User, Course...)
    target_id = Column(Integer) # 대상 ID
    action = Column(String(50)) # CREATE, UPDATE, DELETE
    details = Column(Text) # 상세 내용
    created_at = Column(DateTime, default=func.now())