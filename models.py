# models.py
from sqlalchemy import Column, Integer, String, ForeignKey, Enum, DateTime, Text, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    users = relationship("User", back_populates="department")
    courses = relationship("Course", back_populates="department")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    name = Column(String(50), nullable=False)
    student_number = Column(String(20), nullable=True)
    role = Column(Enum('ADMIN', 'INSTRUCTOR', 'STUDENT'), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    department = relationship("Department", back_populates="users")
    enrollments = relationship("Enrollment", back_populates="user")
    attendances = relationship("Attendance", back_populates="student")

class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    semester = Column(String(20), nullable=False)
    
    # [NEW] 이수구분 (전공, 교양 등)
    course_type = Column(String(20), default="전공", nullable=False)
    
    instructor_id = Column(Integer, ForeignKey("users.id"))
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)

    instructor = relationship("User")
    department = relationship("Department", back_populates="courses")
    sessions = relationship("ClassSession", back_populates="course", cascade="all, delete-orphan")
    enrollments = relationship("Enrollment", back_populates="course", cascade="all, delete-orphan")

# --- 아래는 기존과 동일 ---
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

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"))
    target_type = Column(String(50))
    target_id = Column(Integer)
    action = Column(String(50))
    details = Column(Text)
    created_at = Column(DateTime, default=func.now())