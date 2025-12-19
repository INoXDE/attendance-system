# main.py (Final Admin Integrated Version)
import time
import shutil
import os
import random
import string
import json
from datetime import datetime, timedelta
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Response
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from database import engine, get_db
import models, schemas, auth

app = FastAPI(title="Inoxde Admin System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ... (DB연결, 정적파일, Auth, 기본 User/System 로직은 기존과 동일) ...
# 기존 코드의 상단 부분은 유지하시되, 아래 Admin 부분만 교체/추가하시면 됩니다.

while True:
    try:
        models.Base.metadata.create_all(bind=engine)
        print("DB 연결 성공")
        break
    except OperationalError:
        print("DB 연결 대기 중...")
        time.sleep(2)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root(): return FileResponse('static/index.html')

def log_audit(db, actor, type, tid, act, det=""):
    try:
        db.add(models.AuditLog(actor_id=actor, target_type=type, target_id=tid, action=act, details=det))
        db.commit()
    except: pass

# --- Auth ---
@app.post("/auth/login")
def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password):
        raise HTTPException(status_code=400, detail="Login failed")
    access_token = auth.create_access_token(data={"sub": user.email, "role": user.role})
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, samesite="Lax", secure=True)
    return {"role": user.role}

@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"msg": "bye"}

@app.get("/users/me", response_model=schemas.UserResponse)
def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

# ==========================================
# [Admin] 관리자 기능 (강화됨)
# ==========================================

# 1. 학과 관리
@app.post("/admin/departments", response_model=schemas.DepartmentResponse)
def create_dept(dept: schemas.DepartmentCreate, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if user.role != "ADMIN": raise HTTPException(403)
    new_d = models.Department(name=dept.name)
    db.add(new_d)
    db.commit()
    log_audit(db, user.id, "DEPT", new_d.id, "CREATE", dept.name)
    return new_d

@app.get("/admin/departments", response_model=list[schemas.DepartmentResponse])
def get_depts(db: Session = Depends(get_db)):
    return db.query(models.Department).all()

# 2. 사용자 관리 (Create, Update, Delete)
@app.post("/admin/users", response_model=schemas.UserResponse)
def create_user(u: schemas.UserCreate, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    if db.query(models.User).filter_by(email=u.email).first(): raise HTTPException(400, "Email exists")
    new_u = models.User(email=u.email, password=auth.get_password_hash(u.password), name=u.name, student_number=u.student_number, role=u.role.value, department_id=u.department_id)
    db.add(new_u)
    db.commit()
    log_audit(db, me.id, "USER", new_u.id, "CREATE", u.email)
    return new_u

@app.put("/admin/users/{user_id}", response_model=schemas.UserResponse)
def update_user(user_id: int, u: schemas.UserUpdate, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target: raise HTTPException(404)
    
    target.name = u.name
    target.email = u.email
    target.role = u.role.value
    target.department_id = u.department_id
    target.student_number = u.student_number
    if u.password: target.password = auth.get_password_hash(u.password)
    
    db.commit()
    log_audit(db, me.id, "USER", user_id, "UPDATE", u.email)
    return target

@app.delete("/admin/users/{user_id}")
def delete_user(user_id: int, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if target:
        db.delete(target)
        db.commit()
        log_audit(db, me.id, "USER", user_id, "DELETE")
    return {"msg": "Deleted"}

@app.get("/admin/users", response_model=list[schemas.UserResponse])
def get_users(me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    return db.query(models.User).all()

# 3. 강좌 관리 (Create, Update, Delete, Enrollment)
@app.post("/admin/courses", response_model=schemas.CourseResponse)
def create_course(c: schemas.CourseCreate, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    # [NEW] course_type 추가
    new_c = models.Course(title=c.title, semester=c.semester, course_type=c.course_type, instructor_id=me.id, department_id=c.department_id)
    db.add(new_c)
    db.commit()
    db.refresh(new_c)
    
    # 17주차 자동 생성
    if "2025" in c.semester:
        start_date = datetime(2025, 9, 1, 9, 0, 0)
        sessions = [models.ClassSession(course_id=new_c.id, week_number=i+1, session_date=start_date+timedelta(weeks=i)) for i in range(17)]
        db.add_all(sessions)
        db.commit()
        
    log_audit(db, me.id, "COURSE", new_c.id, "CREATE", c.title)
    return new_c

@app.put("/admin/courses/{course_id}", response_model=schemas.CourseResponse)
def update_course(course_id: int, c: schemas.CourseUpdate, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    target = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not target: raise HTTPException(404)
    
    target.title = c.title
    target.course_type = c.course_type
    target.department_id = c.department_id
    if c.instructor_id: target.instructor_id = c.instructor_id
    
    db.commit()
    log_audit(db, me.id, "COURSE", course_id, "UPDATE", c.title)
    return target

@app.delete("/admin/courses/{course_id}")
def delete_course(course_id: int, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    target = db.query(models.Course).filter(models.Course.id == course_id).first()
    if target:
        db.delete(target)
        db.commit()
        log_audit(db, me.id, "COURSE", course_id, "DELETE")
    return {"msg": "Deleted"}

@app.get("/admin/courses", response_model=list[schemas.CourseResponse])
def get_all_courses(me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    return db.query(models.Course).all()

# [NEW] 관리자가 특정 강의에 학생을 등록 (수강신청 강제 처리)
@app.post("/admin/courses/{course_id}/students")
def add_student_to_course(course_id: int, student_email: str, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    student = db.query(models.User).filter(models.User.email == student_email).first()
    if not student: raise HTTPException(404, "User not found")
    
    if db.query(models.Enrollment).filter_by(user_id=student.id, course_id=course_id).first():
        raise HTTPException(400, "Already enrolled")
        
    db.add(models.Enrollment(user_id=student.id, course_id=course_id))
    db.commit()
    log_audit(db, me.id, "ENROLL", course_id, "ADD_STUDENT", student.email)
    return {"msg": "Enrolled"}

# [NEW] 관리자가 특정 강의에서 학생 제거
@app.delete("/admin/courses/{course_id}/students/{student_id}")
def remove_student_from_course(course_id: int, student_id: int, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    enroll = db.query(models.Enrollment).filter_by(user_id=student_id, course_id=course_id).first()
    if enroll:
        db.delete(enroll)
        db.commit()
        log_audit(db, me.id, "ENROLL", course_id, "REMOVE_STUDENT", str(student_id))
    return {"msg": "Removed"}

# [NEW] 특정 강의의 수강생 목록 조회 (관리자용)
@app.get("/admin/courses/{course_id}/students")
def get_course_students(course_id: int, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    enrolls = db.query(models.Enrollment).filter_by(course_id=course_id).all()
    result = []
    for e in enrolls:
        u = db.query(models.User).filter(models.User.id == e.user_id).first()
        result.append({"id": u.id, "name": u.name, "email": u.email, "student_number": u.student_number})
    return result

# ... (감사 로그 및 Instructor/Student 영역 등 나머지 코드는 기존 main.py 하단과 동일) ...
@app.get("/admin/audit-logs", response_model=list[schemas.AuditLogResponse])
def get_audit_logs(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "ADMIN": raise HTTPException(status_code=403)
    return db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(100).all()

@app.get("/admin/system-status")
def get_system_status(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "ADMIN": raise HTTPException(status_code=403)
    user_count = 0
    course_count = 0
    db_status = "Error"
    try:
        user_count = db.query(models.User).count()
        course_count = db.query(models.Course).count()
        db_status = "Connected"
    except: pass
    return {"status": "OK", "database": db_status, "users": user_count, "courses": course_count, "server_time": datetime.now()}

# ==========================================
# [3] 교원 영역 (Instructor) - 기존 유지
# ==========================================

@app.get("/instructor/dashboard", response_model=list[schemas.CourseResponse])
def get_instructor_dashboard(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "INSTRUCTOR": raise HTTPException(status_code=403, detail="권한 없음")
    return db.query(models.Course).filter(models.Course.instructor_id == current_user.id).all()

@app.post("/instructor/courses/{course_id}/sessions", response_model=schemas.SessionResponse)
def create_session_instructor(course_id: int, session: schemas.SessionCreate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "INSTRUCTOR": raise HTTPException(status_code=403, detail="권한 없음")
    new_session = models.ClassSession(course_id=course_id, week_number=session.week_number, session_date=session.session_date, attendance_method=session.attendance_method)
    db.add(new_session)
    db.commit()
    return new_session

@app.get("/instructor/courses/{course_id}/sessions")
def get_instructor_sessions(course_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.ClassSession).filter(models.ClassSession.course_id == course_id).all()

@app.patch("/sessions/{session_id}/status")
def update_session_status(session_id: int, is_open: bool, method: str, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "INSTRUCTOR": raise HTTPException(status_code=403, detail="권한 없음")
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    session.is_open = is_open
    session.attendance_method = method
    if is_open and method == 'AUTH_CODE' and not session.auth_code:
        session.auth_code = ''.join(random.choices(string.digits, k=4))
    db.commit()
    log_audit(db, current_user.id, "SESSION", session.id, "UPDATE_STATUS", f"{is_open}") # [NEW] 로그 추가
    return {"message": "상태 변경 완료", "auth_code": session.auth_code}

@app.get("/sessions/{session_id}/stat")
def get_session_live_stat(session_id: int, db: Session = Depends(get_db)):
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    total_students = db.query(models.Enrollment).filter(models.Enrollment.course_id == session.course_id).count()
    attended_count = db.query(models.Attendance).filter(models.Attendance.session_id == session_id, models.Attendance.status.in_([1, 4])).count()
    return {"total": total_students, "attended": attended_count, "auth_code": session.auth_code}

@app.get("/instructor/sessions/{session_id}/attendances")
def get_session_attendances(session_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "INSTRUCTOR": raise HTTPException(status_code=403, detail="권한 없음")
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.course_id == session.course_id).all()
    roster = []
    for enroll in enrollments:
        student = db.query(models.User).filter(models.User.id == enroll.user_id).first()
        att = db.query(models.Attendance).filter_by(session_id=session_id, student_id=student.id).first()
        roster.append({
            "student_id": student.id, "student_number": student.student_number, "student_name": student.name,
            "email": student.email, "status": att.status if att else 0, "attendance_id": att.id if att else None
        })
    return roster

class AttendanceUpdate(BaseModel):
    student_id: int
    status: int

@app.patch("/instructor/sessions/{session_id}/attendances")
def update_attendance_manual(session_id: int, update_data: AttendanceUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "INSTRUCTOR": raise HTTPException(status_code=403, detail="권한 없음")
    att = db.query(models.Attendance).filter_by(session_id=session_id, student_id=update_data.student_id).first()
    if att: att.status = update_data.status
    else: db.add(models.Attendance(session_id=session_id, student_id=update_data.student_id, status=update_data.status))
    db.commit()
    log_audit(db, current_user.id, "ATTENDANCE", session_id, "MANUAL_UPDATE", f"Student {update_data.student_id} -> {update_data.status}") # [NEW] 로그 추가
    return {"message": "수정되었습니다."}

# ==========================================
# [4] 학생 영역 (Student) - 기존 유지
# ==========================================

@app.post("/courses/{course_id}/enroll")
def enroll_course(course_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if db.query(models.Enrollment).filter_by(user_id=current_user.id, course_id=course_id).first():
        raise HTTPException(status_code=400, detail="이미 수강 중")
    db.add(models.Enrollment(user_id=current_user.id, course_id=course_id))
    db.commit()
    return {"message": "수강신청 완료"}

@app.get("/student/dashboard", response_model=list[schemas.CourseReportResponse])
def get_student_dashboard(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.user_id == current_user.id).all()
    dashboard_data = []
    for enroll in enrollments:
        course = db.query(models.Course).filter(models.Course.id == enroll.course_id).first()
        total_sessions = db.query(models.ClassSession).filter(models.ClassSession.course_id == course.id).count()
        attended_count = db.query(models.Attendance).join(models.ClassSession).filter(models.ClassSession.course_id == course.id, models.Attendance.student_id == current_user.id, models.Attendance.status.in_([1, 4])).count()
        rate = (attended_count / total_sessions * 100) if total_sessions > 0 else 0.0
        student_stat = schemas.StudentReport(student_name=current_user.name, total_sessions=total_sessions, attended_count=attended_count, attendance_rate=round(rate, 1))
        dashboard_data.append(schemas.CourseReportResponse(course_title=course.title, reports=[student_stat]))
    return dashboard_data

@app.post("/student/sessions/{session_id}/attend")
def attend_student(session_id: int, code: str = None, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    if not session: raise HTTPException(status_code=404, detail="수업 없음")
    if not session.is_open: raise HTTPException(status_code=400, detail="출석체크 시간이 아닙니다.")
    if session.attendance_method == 'AUTH_CODE':
        if not code: raise HTTPException(status_code=400, detail="인증번호 필요")
        if code != session.auth_code: raise HTTPException(status_code=400, detail="인증번호 불일치")
    if db.query(models.Attendance).filter_by(session_id=session_id, student_id=current_user.id).first():
        raise HTTPException(status_code=400, detail="이미 출석하셨습니다.")
    db.add(models.Attendance(session_id=session_id, student_id=current_user.id, status=1))
    db.commit()
    return {"status": "출석 완료"}

@app.get("/student/courses/{course_id}/sessions")
def get_student_sessions(course_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    sessions = db.query(models.ClassSession).filter(models.ClassSession.course_id == course_id).all()
    result = []
    for s in sessions:
        att = db.query(models.Attendance).filter_by(session_id=s.id, student_id=current_user.id).first()
        result.append({"id": s.id, "week_number": s.week_number, "session_date": s.session_date, "is_open": s.is_open, "attendance_method": s.attendance_method, "my_status": att.status if att else 0})
    return result

@app.get("/courses/{course_id}/report", response_model=schemas.CourseReportResponse)
def get_course_report(course_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course: raise HTTPException(status_code=404, detail="강의가 없습니다.")
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.course_id == course_id).all()
    total_sessions = db.query(models.ClassSession).filter(models.ClassSession.course_id == course_id).count()
    report_list = []
    for enrollment in enrollments:
        student = db.query(models.User).filter(models.User.id == enrollment.user_id).first()
        attended_count = db.query(models.Attendance).join(models.ClassSession).filter(models.ClassSession.course_id == course_id, models.Attendance.student_id == student.id, models.Attendance.status.in_([1, 4])).count()
        rate = (attended_count / total_sessions * 100) if total_sessions > 0 else 0.0
        report_list.append(schemas.StudentReport(student_name=student.name, total_sessions=total_sessions, attended_count=attended_count, attendance_rate=round(rate, 1)))
    return schemas.CourseReportResponse(course_title=course.title, reports=report_list)