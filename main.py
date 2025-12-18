# main.py (Final Integrated Version)
import time
import shutil
import os
import random
import string
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Response
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from database import engine, get_db
from datetime import datetime, timedelta
import models, schemas, auth

app = FastAPI(title="Inoxde 출석 서비스", description="Service Level Deployment")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB 연결 재시도 로직
while True:
    try:
        models.Base.metadata.create_all(bind=engine)
        print("DB 연결 성공")
        break
    except OperationalError:
        print("DB 연결 대기 중...")
        time.sleep(2)

# 정적 파일 연결 (프론트엔드)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return FileResponse('static/index.html')

# ==========================================
# [1] 인증 및 사용자 관리 (Auth & User)
# ==========================================

@app.post("/auth/login")
def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password):
        raise HTTPException(status_code=400, detail="이메일 또는 비밀번호 오류")
    
    # 토큰 생성
    access_token = auth.create_access_token(data={"sub": user.email, "role": user.role})
    
    # 쿠키 발급
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        samesite="Lax",
        secure=True # HTTPS 환경
    )
    return {"message": "로그인 성공", "role": user.role, "name": user.name}

@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "로그아웃 되었습니다."}

@app.post("/users", status_code=201)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(status_code=400, detail="이미 존재하는 이메일")
    
    hashed_pw = auth.get_password_hash(user.password)
    
    # [수정됨] 학번(student_number) 저장 로직 추가
    new_user = models.User(
        email=user.email, 
        password=hashed_pw, 
        name=user.name, 
        student_number=user.student_number, # models.py 변경 반영
        role=user.role.value
    )
    db.add(new_user)
    db.commit()
    return {"email": user.email, "role": user.role}

@app.get("/users/me", response_model=schemas.UserResponse)
def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

# ==========================================
# [2] 관리자 영역 (Admin)
# ==========================================

# [2] 관리자(Admin) 영역: 강의(Course) 관리 + 17주차 자동 생성
@app.post("/admin/courses", response_model=schemas.CourseResponse, status_code=201)
def create_course_admin(
    course: schemas.CourseCreate, 
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # 1. 관리자 권한 체크
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="관리자(Admin)만 강의를 개설할 수 있습니다.")

    # 2. 강의 생성
    new_course = models.Course(
        title=course.title, 
        semester=course.semester, 
        instructor_id=current_user.id # 관리자 본인을 임시 교수로 지정 (추후 수정 가능)
    )
    db.add(new_course)
    db.commit()
    db.refresh(new_course) # ID 발급을 위해 새로고침

    # 3. [NEW] 17주차 수업 일정 자동 생성 로직
    if course.semester == "2025-2":
        # 기준일: 2025년 9월 1일 (월) 09:00
        start_date = datetime(2025, 9, 1, 9, 0, 0)
        
        sessions_to_add = []
        for i in range(17): # 0~16 (총 17회)
            week_num = i + 1
            # 1주씩 더함 (timedelta)
            current_session_date = start_date + timedelta(weeks=i)
            
            new_session = models.ClassSession(
                course_id=new_course.id,
                week_number=week_num,
                session_date=current_session_date,
                attendance_method='ELECTRONIC', # 기본값
                is_open=False
            )
            sessions_to_add.append(new_session)
        
        db.add_all(sessions_to_add)
        db.commit()
        print(f"✅ {new_course.title} 강의의 17주차 수업 데이터가 생성되었습니다.")

    return new_course

# ==========================================
# [3] 교원 영역 (Instructor)
# ==========================================

# 1. 교수용 대시보드 (담당 강의 목록)
@app.get("/instructor/dashboard", response_model=list[schemas.CourseResponse])
def get_instructor_dashboard(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "INSTRUCTOR":
        raise HTTPException(status_code=403, detail="교수 권한이 필요합니다.")
    return db.query(models.Course).filter(models.Course.instructor_id == current_user.id).all()

# 2. 수업 생성 (주차별 일정)
@app.post("/instructor/courses/{course_id}/sessions", response_model=schemas.SessionResponse)
def create_session_instructor(
    course_id: int,
    session: schemas.SessionCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "INSTRUCTOR":
        raise HTTPException(status_code=403, detail="권한 없음")
    
    new_session = models.ClassSession(
        course_id=course_id,
        week_number=session.week_number,
        session_date=session.session_date,
        attendance_method=session.attendance_method
    )
    db.add(new_session)
    db.commit()
    return new_session

# 3. 특정 강의의 주차 목록 조회
@app.get("/instructor/courses/{course_id}/sessions")
def get_instructor_sessions(
    course_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(models.ClassSession).filter(models.ClassSession.course_id == course_id).all()

# 4. 수업 상태 변경 (출석 시작/마감 + 인증번호 생성)
@app.patch("/sessions/{session_id}/status")
def update_session_status(
    session_id: int,
    is_open: bool,
    method: str = "ELECTRONIC",
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "INSTRUCTOR":
        raise HTTPException(status_code=403, detail="권한 없음")
        
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    session.is_open = is_open
    session.attendance_method = method
    
    # 인증번호 방식이고, 문을 열 때 인증번호가 없으면 생성
    if is_open and method == 'AUTH_CODE' and not session.auth_code:
        session.auth_code = ''.join(random.choices(string.digits, k=4))
        
    db.commit()
    # [Tip] 여기서 AuditLog(감사로그)를 남길 수 있습니다.
    return {"message": "상태 변경 완료", "auth_code": session.auth_code}

# 5. 실시간 출석 현황 조회 (예: 24/30명)
@app.get("/sessions/{session_id}/stat")
def get_session_live_stat(
    session_id: int,
    db: Session = Depends(get_db)
):
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    total_students = db.query(models.Enrollment).filter(models.Enrollment.course_id == session.course_id).count()
    
    attended_count = db.query(models.Attendance).filter(
        models.Attendance.session_id == session_id,
        models.Attendance.status.in_([1, 4]) # 1:출석, 4:공결
    ).count()
    
    return {
        "total": total_students,
        "attended": attended_count,
        "auth_code": session.auth_code
    }

# 6. 특정 수업의 출석부 조회 (명단 + 상태)
@app.get("/instructor/sessions/{session_id}/attendances")
def get_session_attendances(
    session_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "INSTRUCTOR":
        raise HTTPException(status_code=403, detail="권한 없음")

    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.course_id == session.course_id).all()
    
    roster = []
    for enroll in enrollments:
        student = db.query(models.User).filter(models.User.id == enroll.user_id).first()
        
        att = db.query(models.Attendance).filter_by(
            session_id=session_id, 
            student_id=student.id
        ).first()
        
        status_code = att.status if att else 0
        
        roster.append({
            "student_id": student.id,
            "student_number": student.student_number, # [NEW] 학번 추가 반환
            "student_name": student.name,
            "email": student.email,
            "status": status_code,
            "attendance_id": att.id if att else None
        })
        
    return roster

# 7. 출석 상태 직권 수정 (교수 권한)
class AttendanceUpdate(BaseModel):
    student_id: int
    status: int # 0~4

@app.patch("/instructor/sessions/{session_id}/attendances")
def update_attendance_manual(
    session_id: int,
    update_data: AttendanceUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "INSTRUCTOR":
        raise HTTPException(status_code=403, detail="권한 없음")

    att = db.query(models.Attendance).filter_by(
        session_id=session_id, 
        student_id=update_data.student_id
    ).first()

    if att:
        att.status = update_data.status
    else:
        new_att = models.Attendance(
            session_id=session_id,
            student_id=update_data.student_id,
            status=update_data.status
        )
        db.add(new_att)
    
    db.commit()
    # [Tip] 여기서 AuditLog(감사로그) 추가 필요
    return {"message": "수정되었습니다."}

# ==========================================
# [4] 학생 영역 (Student)
# ==========================================

# 1. 수강 신청
@app.post("/courses/{course_id}/enroll")
def enroll_course(course_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if db.query(models.Enrollment).filter_by(user_id=current_user.id, course_id=course_id).first():
        raise HTTPException(status_code=400, detail="이미 수강 중")
    db.add(models.Enrollment(user_id=current_user.id, course_id=course_id))
    db.commit()
    return {"message": "수강신청 완료"}

# 2. 학생용 대시보드 (강의 목록 + 출석률)
@app.get("/student/dashboard", response_model=list[schemas.CourseReportResponse])
def get_student_dashboard(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.user_id == current_user.id).all()
    dashboard_data = []
    
    for enroll in enrollments:
        course = db.query(models.Course).filter(models.Course.id == enroll.course_id).first()
        total_sessions = db.query(models.ClassSession).filter(models.ClassSession.course_id == course.id).count()
        
        attended_count = db.query(models.Attendance).join(models.ClassSession).filter(
            models.ClassSession.course_id == course.id,
            models.Attendance.student_id == current_user.id,
            models.Attendance.status.in_([1, 4])
        ).count()
        
        rate = (attended_count / total_sessions * 100) if total_sessions > 0 else 0.0
        
        student_stat = schemas.StudentReport(
            student_name=current_user.name,
            total_sessions=total_sessions,
            attended_count=attended_count,
            attendance_rate=round(rate, 1)
        )
        dashboard_data.append(schemas.CourseReportResponse(course_title=course.title, reports=[student_stat]))
        
    return dashboard_data

# 3. 출석 체크 액션
@app.post("/student/sessions/{session_id}/attend")
def attend_student(
    session_id: int, 
    code: str = None, 
    current_user: models.User = Depends(auth.get_current_user), 
    db: Session = Depends(get_db)
):
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="수업 없음")
    if not session.is_open:
        raise HTTPException(status_code=400, detail="출석체크 시간이 아닙니다.")
    
    if session.attendance_method == 'AUTH_CODE':
        if not code:
            raise HTTPException(status_code=400, detail="인증번호 필요")
        if code != session.auth_code:
            raise HTTPException(status_code=400, detail="인증번호 불일치")

    if db.query(models.Attendance).filter_by(session_id=session_id, student_id=current_user.id).first():
        raise HTTPException(status_code=400, detail="이미 출석하셨습니다.")

    db.add(models.Attendance(session_id=session_id, student_id=current_user.id, status=1))
    db.commit()
    return {"status": "출석 완료"}

# 4. 주차별 상세 조회 (내 상태 포함)
@app.get("/student/courses/{course_id}/sessions")
def get_student_sessions(
    course_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    sessions = db.query(models.ClassSession).filter(models.ClassSession.course_id == course_id).all()
    
    result = []
    for s in sessions:
        # 이 세션에 대한 나의 출석 기록
        att = db.query(models.Attendance).filter_by(
            session_id=s.id, 
            student_id=current_user.id
        ).first()
        
        my_status = att.status if att else 0 
        
        result.append({
            "id": s.id,
            "week_number": s.week_number,
            "session_date": s.session_date,
            "is_open": s.is_open,
            "attendance_method": s.attendance_method,
            "my_status": my_status # [중요] 프론트 버튼 활성화용
        })
    return result

# 5. 강의 리포트 보기
@app.get("/courses/{course_id}/report", response_model=schemas.CourseReportResponse)
def get_course_report(
    course_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="강의가 없습니다.")

    enrollments = db.query(models.Enrollment).filter(models.Enrollment.course_id == course_id).all()
    total_sessions = db.query(models.ClassSession).filter(models.ClassSession.course_id == course_id).count()
    
    report_list = []
    for enrollment in enrollments:
        student = db.query(models.User).filter(models.User.id == enrollment.user_id).first()
        attended_count = db.query(models.Attendance).join(models.ClassSession).filter(
            models.ClassSession.course_id == course_id,
            models.Attendance.student_id == student.id,
            models.Attendance.status.in_([1, 4]) 
        ).count()
        rate = (attended_count / total_sessions * 100) if total_sessions > 0 else 0.0
        
        report_list.append(schemas.StudentReport(
            student_name=student.name,
            total_sessions=total_sessions,
            attended_count=attended_count,
            attendance_rate=round(rate, 1)
        ))
        
    return schemas.CourseReportResponse(course_title=course.title, reports=report_list)