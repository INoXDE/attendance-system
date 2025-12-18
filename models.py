# models.py
from sqlalchemy import Column, Integer, String, ForeignKey, Enum, DateTime, Text, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship # [NEW] 관계 설정을 위해 추가
from database import Base
from datetime import datetime

# 1. 사용자 모델 (명세서: 학번, 역할 등)
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    name = Column(String(50), nullable=False)
    student_number = Column(String(20), nullable=True) # [NEW] 학번 추가 (교수는 null 가능)
    role = Column(Enum('ADMIN', 'INSTRUCTOR', 'STUDENT'), nullable=False)
    created_at = Column(DateTime, default=func.now())

    # 관계 설정 (DB조작 편의성)
    enrollments = relationship("Enrollment", back_populates="user")
    attendances = relationship("Attendance", back_populates="student")

# 2. 강의 모델
class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    semester = Column(String(20), nullable=False) # 예: "2025-2"
    instructor_id = Column(Integer, ForeignKey("users.id"))

    # 관계 설정
    instructor = relationship("User")
    sessions = relationship("ClassSession", back_populates="course")
    enrollments = relationship("Enrollment", back_populates="course")

# 3. 강의 세션(주차) 모델
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

# 4. 수강신청 모델
class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    joined_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")

# 5. 출석 기록 모델
class Attendance(Base):
    __tablename__ = "attendances"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # [cite_start]0:미정, 1:출석, 2:지각, 3:결석, 4:공결 [cite: 12]
    status = Column(Integer, default=0) 
    checked_at = Column(DateTime, default=func.now())

    student = relationship("User", back_populates="attendances")

# 6. 공결 신청 모델
class ExcuseRequest(Base):
    __tablename__ = "excuse_requests"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=False)
    file_path = Column(String(255), nullable=True)
    status = Column(Enum('PENDING', 'APPROVED', 'REJECTED'), default='PENDING')
    admin_comment = Column(Text, nullable=True)

# [cite_start]7. [NEW] 감사 로그 (Audit Log) - 관리자용 [cite: 29]
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id")) # 변경한 사람 (교수/관리자)
    target_type = Column(String(50)) # 예: "ATTENDANCE", "COURSE_POLICY"
    target_id = Column(Integer) # 변경된 대상 ID
    action = Column(String(50)) # 예: "UPDATE", "DELETE"
    details = Column(Text) # 변경 내용 상세 (JSON 등)
    created_at = Column(DateTime, default=func.now())