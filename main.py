# main.py
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

# [상수 정의]
HOLIDAYS_2025_2 = [
    "2025-10-03", "2025-10-06", "2025-10-07", 
    "2025-10-08", "2025-10-09", "2025-12-25"
]
DAY_MAP = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

# 1. 앱 생성
app = FastAPI(title="Inoxde Admin System")

# 2. 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. 파일 저장소 및 정적 파일 설정
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 4. DB 테이블 생성 루프
while True:
    try:
        models.Base.metadata.create_all(bind=engine)
        print("DB 연결 성공")
        break
    except OperationalError:
        print("DB 연결 대기 중...")
        time.sleep(2)

# --- 루트 페이지 ---
@app.get("/")
def read_root(): return FileResponse('static/index.html')

# --- Audit Log Helper ---
def log_audit(db, actor, type, tid, act, det=""):
    try:
        db.add(models.AuditLog(actor_id=actor, target_type=type, target_id=tid, action=act, details=det))
        db.commit()
    except: pass

# ==========================================
# [Auth] 인증 관련
# ==========================================
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
# [Admin] 관리자 기능
# ==========================================

# 1. 학과 관리
@app.get("/admin/departments")
def get_departments(db: Session = Depends(get_db)):
    depts = db.query(models.Department).all()
    result = []
    for d in depts:
        u_count = db.query(models.User).filter_by(department_id=d.id).count()
        c_count = db.query(models.Course).filter_by(department_id=d.id).count()
        result.append({"id": d.id, "name": d.name, "user_count": u_count, "course_count": c_count})
    return result

@app.post("/admin/departments", response_model=schemas.DepartmentResponse)
def create_dept(dept: schemas.DepartmentCreate, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if user.role != "ADMIN": raise HTTPException(403)
    if db.query(models.Department).filter_by(name=dept.name).first():
        raise HTTPException(400, detail="이미 존재하는 학과명입니다.")
    new_d = models.Department(name=dept.name)
    db.add(new_d)
    db.commit()
    log_audit(db, user.id, "DEPT", new_d.id, "CREATE", dept.name)
    return new_d

@app.put("/admin/departments/{dept_id}")
def update_department(dept_id: int, dept: schemas.DepartmentCreate, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if user.role != "ADMIN": raise HTTPException(403)
    d = db.query(models.Department).filter(models.Department.id == dept_id).first()
    if not d: raise HTTPException(404)
    if d.name == "대학본부": raise HTTPException(status_code=400, detail="⛔ 시스템 기본 학과(대학본부)는 수정할 수 없습니다.")
    
    old_name = d.name
    d.name = dept.name
    db.commit()
    log_audit(db, user.id, "DEPT", d.id, "UPDATE", f"{old_name} -> {dept.name}")
    return {"msg": "Updated", "name": d.name}

@app.delete("/admin/departments/{dept_id}")
def delete_department(dept_id: int, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if user.role != "ADMIN": raise HTTPException(403)
    d = db.query(models.Department).filter(models.Department.id == dept_id).first()
    if not d: raise HTTPException(404)
    if d.name == "대학본부": raise HTTPException(status_code=400, detail="⛔ 대학본부는 삭제할 수 없습니다.")
    
    u_count = db.query(models.User).filter_by(department_id=dept_id).count()
    c_count = db.query(models.Course).filter_by(department_id=dept_id).count()
    if u_count > 0 or c_count > 0:
        raise HTTPException(status_code=400, detail=f"삭제 불가: 구성원({u_count}명) 또는 강의({c_count}개)가 남아있습니다.")
        
    db.delete(d)
    db.commit()
    log_audit(db, user.id, "DEPT", dept_id, "DELETE")
    return {"msg": "Deleted"}

# 2. 사용자 관리
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
        if target.role == "ADMIN":
            admin_count = db.query(models.User).filter(models.User.role == "ADMIN").count()
            if admin_count <= 1: raise HTTPException(status_code=400, detail="⛔ 마지막 남은 관리자는 삭제할 수 없습니다.")
        db.delete(target)
        db.commit()
        log_audit(db, me.id, "USER", user_id, "DELETE")
        return {"msg": "Deleted"}
    return {"msg": "User not found"}

@app.get("/admin/users", response_model=list[schemas.UserResponse])
def get_users(me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    return db.query(models.User).all()

# 3. 강좌 관리
@app.post("/admin/courses", response_model=schemas.CourseResponse)
def create_course(c: schemas.CourseCreate, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    instructor = db.query(models.User).filter(models.User.id == c.instructor_id, models.User.role == 'INSTRUCTOR').first()
    if not instructor: raise HTTPException(400, detail="유효하지 않은 교수 ID")

    new_c = models.Course(
        title=c.title, semester=c.semester, course_type=c.course_type, 
        day_of_week=c.day_of_week, instructor_id=c.instructor_id, department_id=c.department_id
    )
    db.add(new_c)
    db.commit()
    db.refresh(new_c)
    
    if "2025" in c.semester:
        base_start = datetime(2025, 9, 1, 9, 0, 0)
        target_weekday = DAY_MAP.get(c.day_of_week, 0)
        days_ahead = target_weekday - base_start.weekday()
        if days_ahead < 0: days_ahead += 7
        first_session_date = base_start + timedelta(days=days_ahead)
        
        sessions = []
        for i in range(17):
            current_date = first_session_date + timedelta(weeks=i)
            date_str = current_date.strftime("%Y-%m-%d")
            is_hol = (date_str in HOLIDAYS_2025_2)
            sessions.append(models.ClassSession(course_id=new_c.id, week_number=i+1, session_date=current_date, is_holiday=is_hol))
        db.add_all(sessions)
        db.commit()
        
    log_audit(db, me.id, "COURSE", new_c.id, "CREATE", f"{c.title}")
    return new_c

@app.put("/admin/courses/{course_id}", response_model=schemas.CourseResponse)
def update_course(course_id: int, c: schemas.CourseUpdate, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    target = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not target: raise HTTPException(404)
    
    target.title = c.title
    target.course_type = c.course_type
    target.day_of_week = c.day_of_week
    if c.department_id: target.department_id = c.department_id
    if c.instructor_id: target.instructor_id = c.instructor_id
    
    db.commit()
    log_audit(db, me.id, "COURSE", course_id, "UPDATE", c.title)
    return target

@app.delete("/admin/courses/{course_id}")
def delete_course(course_id: int, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    c = db.query(models.Course).filter(models.Course.id == course_id).first()
    if c:
        db.delete(c)
        db.commit()
    return {"msg": "Deleted"}

@app.get("/admin/courses", response_model=list[schemas.CourseResponse])
def get_all_courses(me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    return db.query(models.Course).all()

@app.post("/admin/courses/{course_id}/students")
def add_student_to_course(course_id: int, student_number: str, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    student = db.query(models.User).filter(models.User.student_number == student_number).first()
    if not student: raise HTTPException(404, detail="해당 학번의 학생을 찾을 수 없습니다.")
    if db.query(models.Enrollment).filter_by(user_id=student.id, course_id=course_id).first():
        raise HTTPException(400, detail="이미 수강 중인 학생입니다.")
    db.add(models.Enrollment(user_id=student.id, course_id=course_id))
    db.commit()
    log_audit(db, me.id, "ENROLL", course_id, "ADD_STUDENT", f"{student.name}({student_number})")
    return {"msg": "Enrolled"}

@app.get("/admin/courses/{course_id}/students")
def get_course_students(course_id: int, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    enrolls = db.query(models.Enrollment).filter_by(course_id=course_id).all()
    result = []
    for e in enrolls:
        u = db.query(models.User).filter(models.User.id == e.user_id).first()
        result.append({"id": u.id, "name": u.name, "email": u.email, "student_number": u.student_number})
    return result

@app.delete("/admin/courses/{course_id}/students/{student_id}")
def remove_student_from_course(course_id: int, student_id: int, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    enroll = db.query(models.Enrollment).filter_by(user_id=student_id, course_id=course_id).first()
    if enroll:
        db.delete(enroll)
        db.commit()
        log_audit(db, me.id, "ENROLL", course_id, "REMOVE_STUDENT", str(student_id))
    return {"msg": "Removed"}

@app.get("/admin/audit-logs", response_model=list[schemas.AuditLogResponse])
def get_audit_logs(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "ADMIN": raise HTTPException(status_code=403)
    return db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(100).all()

@app.get("/admin/system-status")
def get_system_status(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "ADMIN": raise HTTPException(status_code=403)
    user_count = db.query(models.User).count()
    course_count = db.query(models.Course).count()
    return {"status": "OK", "database": "Connected", "users": user_count, "courses": course_count, "server_time": datetime.now()}

# ==========================================
# [Instructor] 교원 영역
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
    log_audit(db, current_user.id, "SESSION", session.id, "UPDATE_STATUS", f"{is_open}")
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
    vote_y = 0
    vote_n = 0
    for enroll in enrollments:
        student = db.query(models.User).filter(models.User.id == enroll.user_id).first()
        att = db.query(models.Attendance).filter_by(session_id=session_id, student_id=student.id).first()
        if att and att.vote_response == 'Y': vote_y += 1
        if att and att.vote_response == 'N': vote_n += 1
        roster.append({
            "student_id": student.id, 
            "student_number": student.student_number, 
            "student_name": student.name,
            "email": student.email, 
            "status": att.status if att else 0, 
            "proof_file": att.proof_file if att else None,
            "appeal_reason": att.appeal_reason if att else None
        })
    return {"roster": roster, "vote_stat": {"Y": vote_y, "N": vote_n}}

@app.patch("/instructor/sessions/{session_id}/attendances")
def update_attendance_manual(session_id: int, update_data: schemas.AttendanceUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "INSTRUCTOR": raise HTTPException(status_code=403, detail="권한 없음")
    att = db.query(models.Attendance).filter_by(session_id=session_id, student_id=update_data.student_id).first()
    if att: att.status = update_data.status
    else: db.add(models.Attendance(session_id=session_id, student_id=update_data.student_id, status=update_data.status))
    db.commit()
    log_audit(db, current_user.id, "ATTENDANCE", session_id, "MANUAL_UPDATE", f"Student {update_data.student_id} -> {update_data.status}")
    return {"message": "수정되었습니다."}

@app.patch("/instructor/sessions/{session_id}/date")
def update_session_date(session_id: int, date_data: schemas.SessionUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "INSTRUCTOR": raise HTTPException(403)
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    if not session: raise HTTPException(404)
    course = db.query(models.Course).filter(models.Course.id == session.course_id).first()
    if course.instructor_id != current_user.id: raise HTTPException(403)
    session.session_date = date_data.session_date
    session.is_holiday = False 
    db.commit()
    log_audit(db, current_user.id, "SESSION", session_id, "RESCHEDULE", str(date_data.session_date))
    return {"msg": "Updated"}

@app.get("/instructor/courses/{course_id}/stack_report")
def get_stack_report(course_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "INSTRUCTOR": raise HTTPException(403)
    sessions = db.query(models.ClassSession).filter_by(course_id=course_id).all()
    weekly_rates = []
    total_enroll = db.query(models.Enrollment).filter_by(course_id=course_id).count()
    for s in sessions:
        if total_enroll == 0:
            weekly_rates.append(0)
            continue
        attended = db.query(models.Attendance).filter(models.Attendance.session_id == s.id, models.Attendance.status.in_([1, 4])).count()
        weekly_rates.append(round((attended / total_enroll) * 100, 1))

    total_req = db.query(models.Attendance).join(models.ClassSession).filter(models.ClassSession.course_id == course_id, models.Attendance.proof_file != None).count()
    approved = db.query(models.Attendance).join(models.ClassSession).filter(models.ClassSession.course_id == course_id, models.Attendance.status == 4).count()
    approval_rate = round((approved / total_req * 100), 1) if total_req > 0 else 0.0

    students = db.query(models.User).join(models.Enrollment).filter(models.Enrollment.course_id == course_id).all()
    risk_list = []
    for stu in students:
        atts = db.query(models.Attendance).join(models.ClassSession).filter(models.ClassSession.course_id == course_id, models.Attendance.student_id == stu.id).all()
        absent = 0
        late = 0
        consecutive_late = 0
        max_consecutive_late = 0
        for a in atts:
            if a.status == 3: absent += 1
            if a.status == 2: 
                late += 1
                consecutive_late += 1
            else: consecutive_late = 0
            max_consecutive_late = max(max_consecutive_late, consecutive_late)
        converted = absent + (late // 3)
        is_risk = (converted >= 3) or (max_consecutive_late >= 2)
        risk_list.append({"student_name": stu.name, "total_absent": absent, "total_late": late, "converted_absent": converted, "is_risk": is_risk})
        
    risk_list.sort(key=lambda x: x['converted_absent'], reverse=True)
    return {"weekly_attendance": weekly_rates, "official_approval_rate": approval_rate, "risk_group": risk_list}

class NoticeUpdate(BaseModel):
    notice: str

@app.patch("/instructor/courses/{course_id}/notice")
def update_course_notice(course_id: int, notice_data: NoticeUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "INSTRUCTOR": raise HTTPException(403)
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if course.instructor_id != current_user.id: raise HTTPException(403)
    course.notice = notice_data.notice
    db.commit()
    log_audit(db, current_user.id, "COURSE", course_id, "UPDATE_NOTICE")
    return {"msg": "Notice updated"}

@app.patch("/instructor/sessions/{session_id}/vote")
def toggle_vote(session_id: int, is_voting: bool, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "INSTRUCTOR": raise HTTPException(403)
    session = db.query(models.ClassSession).filter_by(id=session_id).first()
    session.is_voting = is_voting
    db.commit()
    log_audit(db, current_user.id, "SESSION", session_id, "VOTE_TOGGLE", str(is_voting))
    return {"msg": "Vote status changed"}

# ==========================================
# [Student] 학생 영역
# ==========================================
@app.post("/courses/{course_id}/enroll")
def enroll_course(course_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if db.query(models.Enrollment).filter_by(user_id=current_user.id, course_id=course_id).first():
        raise HTTPException(status_code=400, detail="이미 수강 중")
    db.add(models.Enrollment(user_id=current_user.id, course_id=course_id))
    db.commit()
    return {"message": "수강신청 완료"}

@app.get("/student/dashboard")
def get_student_dashboard_enhanced(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.user_id == current_user.id).all()
    dashboard_data = []
    for enroll in enrollments:
        course = db.query(models.Course).filter(models.Course.id == enroll.course_id).first()
        total_sessions = db.query(models.ClassSession).filter(models.ClassSession.course_id == course.id).count()
        absent_count = db.query(models.Attendance).join(models.ClassSession).filter(models.ClassSession.course_id == course.id, models.Attendance.student_id == current_user.id, models.Attendance.status == 3).count()
        attended_count = db.query(models.Attendance).join(models.ClassSession).filter(models.ClassSession.course_id == course.id, models.Attendance.student_id == current_user.id, models.Attendance.status.in_([1, 4])).count()
        rate = (attended_count / total_sessions * 100) if total_sessions > 0 else 0.0
        is_warning = (absent_count >= 2)
        dashboard_data.append({
            "course_id": course.id, "course_title": course.title, "semester": course.semester,
            "notice": course.notice, "attendance_rate": round(rate, 1), "is_warning": is_warning
        })
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
        result.append({
            "id": s.id, "week_number": s.week_number, "session_date": s.session_date, 
            "is_open": s.is_open, "is_voting": s.is_voting, "attendance_method": s.attendance_method, 
            "my_status": att.status if att else 0
        })
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

@app.post("/student/sessions/{session_id}/excuse")
def apply_excuse(session_id: int, file: UploadFile = File(...), current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    file_ext = file.filename.split(".")[-1]
    file_name = f"{current_user.id}_{session_id}_{int(time.time())}.{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    att = db.query(models.Attendance).filter_by(session_id=session_id, student_id=current_user.id).first()
    if not att:
        att = models.Attendance(session_id=session_id, student_id=current_user.id)
        db.add(att)
    att.status = 5
    att.proof_file = file_name
    db.commit()
    return {"msg": "Uploaded", "path": file_name}

class AppealCreate(BaseModel):
    reason: str

@app.post("/student/sessions/{session_id}/appeal")
def create_appeal(session_id: int, appeal: AppealCreate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    att = db.query(models.Attendance).filter_by(session_id=session_id, student_id=current_user.id).first()
    if not att:
        att = models.Attendance(session_id=session_id, student_id=current_user.id, status=0)
        db.add(att)
    att.appeal_reason = appeal.reason
    db.commit()
    log_audit(db, current_user.id, "ATTENDANCE", att.id, "APPEAL", appeal.reason)
    return {"msg": "Appeal sent"}

@app.post("/student/sessions/{session_id}/vote")
def cast_vote(session_id: int, vote: str, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if vote not in ['Y', 'N']: raise HTTPException(400)
    att = db.query(models.Attendance).filter_by(session_id=session_id, student_id=current_user.id).first()
    if not att:
        att = models.Attendance(session_id=session_id, student_id=current_user.id)
        db.add(att)
    att.vote_response = vote
    db.commit()
    log_audit(db, current_user.id, "VOTE", session_id, "CAST_VOTE", vote)
    return {"msg": "Voted"}