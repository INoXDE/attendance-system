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


UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# [NEW] 공휴일 리스트 (2025-2학기, 주말 제외)
HOLIDAYS_2025_2 = [
    "2025-10-03", # 개천절
    "2025-10-06", # 추석 대체? (임시)
    "2025-10-07", # 추석 대체? (임시)
    "2025-10-08", # 임시
    "2025-10-09", # 한글날
    "2025-12-25"  # 성탄절
]

# [NEW] 요일 매핑 헬퍼
DAY_MAP = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

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

# main.py (학과 관리 부분 수정)

# 1. 학과 목록 조회 (인원 수 포함)
@app.get("/admin/departments")
def get_departments(db: Session = Depends(get_db)):
    depts = db.query(models.Department).all()
    result = []
    for d in depts:
        # 안전한 삭제를 위해 연관 데이터 개수를 미리 셉니다.
        u_count = db.query(models.User).filter_by(department_id=d.id).count()
        c_count = db.query(models.Course).filter_by(department_id=d.id).count()
        result.append({
            "id": d.id, 
            "name": d.name,
            "user_count": u_count,
            "course_count": c_count
        })
    return result

# 2. 학과 생성 (기존 동일)
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

# main.py (수정 및 삭제 함수 교체)

# 3. [보호됨] 학과 이름 변경
@app.put("/admin/departments/{dept_id}")
def update_department(dept_id: int, dept: schemas.DepartmentCreate, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if user.role != "ADMIN": raise HTTPException(403)
    
    d = db.query(models.Department).filter(models.Department.id == dept_id).first()
    if not d: raise HTTPException(404)
    
    # [NEW] 안전장치: 대학본부는 수정 절대 불가
    if d.name == "대학본부":
        raise HTTPException(status_code=400, detail="⛔ 시스템 기본 학과(대학본부)는 수정할 수 없습니다.")
    
    old_name = d.name
    d.name = dept.name
    db.commit()
    log_audit(db, user.id, "DEPT", d.id, "UPDATE", f"{old_name} -> {dept.name}")
    return {"msg": "Updated", "name": d.name}

# 4. [보호됨] 학과 삭제
@app.delete("/admin/departments/{dept_id}")
def delete_department(dept_id: int, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if user.role != "ADMIN": raise HTTPException(403)
    
    d = db.query(models.Department).filter(models.Department.id == dept_id).first()
    if not d: raise HTTPException(404)

    # [NEW] 안전장치: 대학본부는 삭제 절대 불가
    if d.name == "대학본부":
        raise HTTPException(status_code=400, detail="⛔ 시스템 기본 학과(대학본부)는 삭제할 수 없습니다.")
    
    # 기존 안전장치: 구성원이나 강의가 있으면 삭제 불가
    u_count = db.query(models.User).filter_by(department_id=dept_id).count()
    c_count = db.query(models.Course).filter_by(department_id=dept_id).count()
    
    if u_count > 0 or c_count > 0:
        raise HTTPException(status_code=400, detail=f"삭제 불가: 구성원({u_count}명) 또는 강의({c_count}개)가 남아있습니다.")
        
    db.delete(d)
    db.commit()
    log_audit(db, user.id, "DEPT", dept_id, "DELETE")
    
    return {"msg": "Deleted"}

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

# main.py (사용자 삭제 함수 교체)

@app.delete("/admin/users/{user_id}")
def delete_user(user_id: int, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    
    target = db.query(models.User).filter(models.User.id == user_id).first()
    
    if target:
        # [NEW] 마지막 관리자 삭제 방지 로직
        if target.role == "ADMIN":
            admin_count = db.query(models.User).filter(models.User.role == "ADMIN").count()
            if admin_count <= 1:
                raise HTTPException(status_code=400, detail="⛔ 마지막 남은 관리자는 삭제할 수 없습니다.")

        db.delete(target)
        db.commit()
        log_audit(db, me.id, "USER", user_id, "DELETE")
        return {"msg": "Deleted"}
    
    return {"msg": "User not found"}

@app.get("/admin/users", response_model=list[schemas.UserResponse])
def get_users(me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    return db.query(models.User).all()

# 3. 강좌 관리 (Create, Update, Delete, Enrollment)
# 1. [수정] 강의 생성 함수 (공휴일 체크 추가)
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
            
            # [NEW] 공휴일 리스트 체크
            is_hol = (date_str in HOLIDAYS_2025_2)
            
            sessions.append(models.ClassSession(
                course_id=new_c.id, 
                week_number=i+1, 
                session_date=current_date,
                is_holiday=is_hol # DB에 저장
            ))
        db.add_all(sessions)
        db.commit()
        
    log_audit(db, me.id, "COURSE", new_c.id, "CREATE", f"{c.title}")
    return new_c

# ... (update_course 등 나머지 함수에도 day_of_week 필드 처리 추가 필요) ...
@app.put("/admin/courses/{course_id}", response_model=schemas.CourseResponse)
def update_course(course_id: int, c: schemas.CourseUpdate, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    target = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not target: raise HTTPException(404)
    
    target.title = c.title
    target.course_type = c.course_type
    target.day_of_week = c.day_of_week
    
    # [수정] 학과 ID가 null이 아닐 때만 업데이트 (혹은 프론트에서 보내줌)
    if c.department_id: target.department_id = c.department_id
    if c.instructor_id: target.instructor_id = c.instructor_id
    
    db.commit()
    log_audit(db, me.id, "COURSE", course_id, "UPDATE", c.title)
    return target

# 2. [수정] 학과 삭제 함수 (방어 로직 강화)
@app.delete("/admin/departments/{dept_id}")
def delete_department(dept_id: int, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if user.role != "ADMIN": raise HTTPException(403)
    
    d = db.query(models.Department).filter(models.Department.id == dept_id).first()
    if not d: raise HTTPException(404)

    # 본부는 절대 삭제 불가
    if d.name == "대학본부":
        raise HTTPException(status_code=400, detail="⛔ 대학본부는 삭제할 수 없습니다.")
    
    # 구성원 존재 시 삭제 불가
    u_count = db.query(models.User).filter_by(department_id=dept_id).count()
    c_count = db.query(models.Course).filter_by(department_id=dept_id).count()
    
    if u_count > 0 or c_count > 0:
        raise HTTPException(status_code=400, detail=f"구성원({u_count}명) 또는 강의({c_count}개)가 있어 삭제할 수 없습니다.")
        
    db.delete(d)
    db.commit()
    return {"msg": "Deleted"}

@app.get("/admin/courses", response_model=list[schemas.CourseResponse])
def get_all_courses(me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    return db.query(models.Course).all()

# 3. 수강생 추가 (학번 검색으로 변경)
@app.post("/admin/courses/{course_id}/students")
def add_student_to_course(course_id: int, student_number: str, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    
    # [수정] 이메일 대신 학번으로 검색
    student = db.query(models.User).filter(models.User.student_number == student_number).first()
    if not student: raise HTTPException(404, detail="해당 학번의 학생을 찾을 수 없습니다.")
    
    if db.query(models.Enrollment).filter_by(user_id=student.id, course_id=course_id).first():
        raise HTTPException(400, detail="이미 수강 중인 학생입니다.")
        
    db.add(models.Enrollment(user_id=student.id, course_id=course_id))
    db.commit()
    log_audit(db, me.id, "ENROLL", course_id, "ADD_STUDENT", f"{student.name}({student_number})")
    return {"msg": "Enrolled"}

# 4. 수강생 목록 조회 (학번 포함 반환)
@app.get("/admin/courses/{course_id}/students")
def get_course_students(course_id: int, me: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if me.role != "ADMIN": raise HTTPException(403)
    enrolls = db.query(models.Enrollment).filter_by(course_id=course_id).all()
    result = []
    for e in enrolls:
        u = db.query(models.User).filter(models.User.id == e.user_id).first()
        result.append({
            "id": u.id, 
            "name": u.name, 
            "email": u.email, 
            "student_number": u.student_number # 학번 필수
        })
    return result

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
            "student_id": student.id, 
            "student_number": student.student_number, 
            "student_name": student.name,
            "email": student.email, 
            "status": att.status if att else 0, 
            "proof_file": att.proof_file if att else None # [NEW] 파일 경로
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

# 3. [추가] 교수님 보강일 설정 API
@app.patch("/instructor/sessions/{session_id}/date")
def update_session_date(session_id: int, date_data: schemas.SessionUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "INSTRUCTOR": raise HTTPException(403)
    
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    if not session: raise HTTPException(404)
    
    # 본인 강의인지 체크 (보안)
    course = db.query(models.Course).filter(models.Course.id == session.course_id).first()
    if course.instructor_id != current_user.id: raise HTTPException(403, detail="본인의 강의가 아닙니다.")
    
    session.session_date = date_data.session_date
    # 날짜를 바꾸면 공휴일 상태 해제 (정상 수업으로 전환)
    session.is_holiday = False 
    
    db.commit()
    log_audit(db, current_user.id, "SESSION", session_id, "RESCHEDULE", str(date_data.session_date))
    return {"msg": "Updated"}

@app.get("/instructor/courses/{course_id}/stack_report")
def get_stack_report(course_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "INSTRUCTOR": raise HTTPException(403)
    
    # A. 주차별 출석률
    sessions = db.query(models.ClassSession).filter_by(course_id=course_id).all()
    weekly_rates = []
    total_enroll = db.query(models.Enrollment).filter_by(course_id=course_id).count()
    
    for s in sessions:
        if total_enroll == 0:
            weekly_rates.append(0)
            continue
        # 출석(1) + 공결(4) 만 인정
        attended = db.query(models.Attendance).filter(
            models.Attendance.session_id == s.id, 
            models.Attendance.status.in_([1, 4])
        ).count()
        weekly_rates.append(round((attended / total_enroll) * 100, 1))

    # B. 공결 승인률
    # status 4(승인) / (status 4 + status 5(신청중) + 반려된 케이스(보통 3으로 되돌림, 추적 어려우므로 여기선 4+5 기준))
    total_req = db.query(models.Attendance).join(models.ClassSession).filter(
        models.ClassSession.course_id == course_id,
        models.Attendance.proof_file != None
    ).count()
    
    approved = db.query(models.Attendance).join(models.ClassSession).filter(
        models.ClassSession.course_id == course_id,
        models.Attendance.status == 4
    ).count()
    
    approval_rate = round((approved / total_req * 100), 1) if total_req > 0 else 0.0

    # C. 학생별 스택 & 위험군 분석
    students = db.query(models.User).join(models.Enrollment).filter(models.Enrollment.course_id == course_id).all()
    risk_list = []
    
    for stu in students:
        # 해당 강의의 모든 출석 기록 가져오기
        atts = db.query(models.Attendance).join(models.ClassSession).filter(
            models.ClassSession.course_id == course_id,
            models.Attendance.student_id == stu.id
        ).all()
        
        absent = 0
        late = 0
        consecutive_late = 0
        max_consecutive_late = 0
        
        for a in atts:
            if a.status == 3: absent += 1
            if a.status == 2: 
                late += 1
                consecutive_late += 1
            else:
                consecutive_late = 0
            max_consecutive_late = max(max_consecutive_late, consecutive_late)
            
        # [스택 계산] 지각 3회 -> 결석 1회 환산 (예시)
        converted = absent + (late // 3)
        
        # [위험군 판별] 환산 결석 3회 이상이거나 연속 지각 2회 이상
        is_risk = (converted >= 3) or (max_consecutive_late >= 2)
        
        risk_list.append({
            "student_name": stu.name,
            "total_absent": absent,
            "total_late": late,
            "converted_absent": converted,
            "is_risk": is_risk
        })
        
    # 위험군을 상위로 정렬
    risk_list.sort(key=lambda x: x['converted_absent'], reverse=True)

    return {
        "weekly_attendance": weekly_rates,
        "official_approval_rate": approval_rate,
        "risk_group": risk_list
    }

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

@app.post("/student/sessions/{session_id}/excuse")
def apply_excuse(session_id: int, file: UploadFile = File(...), current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    # 파일 저장
    file_ext = file.filename.split(".")[-1]
    file_name = f"{current_user.id}_{session_id}_{int(time.time())}.{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # DB 업데이트 (상태 5: 신청중)
    att = db.query(models.Attendance).filter_by(session_id=session_id, student_id=current_user.id).first()
    if not att:
        att = models.Attendance(session_id=session_id, student_id=current_user.id)
        db.add(att)
    
    att.status = 5 # 공결 신청 상태
    att.proof_file = file_name
    db.commit()
    
    return {"msg": "Uploaded", "path": file_name}