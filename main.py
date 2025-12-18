# main.py
import time
import shutil
import os
from fastapi.staticfiles import StaticFiles # 이거 추가
from fastapi.responses import FileResponse # 이거 추가
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Response
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from database import engine, get_db
import models, schemas, auth

app = FastAPI(title="Inoxde 출석 서비스", description="Service Level Deployment")

# CORS 설정 (프론트엔드와 통신하기 위해 필수)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 실제 배포 시 "https://inoxde.com"으로 변경 권장
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

# --- [1] 로그인: 쿠키 자동 발급 (PDF source: 15) ---
@app.post("/auth/login")
def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password):
        raise HTTPException(status_code=400, detail="이메일 또는 비밀번호 오류")
    
    # 토큰 생성
    access_token = auth.create_access_token(data={"sub": user.email, "role": user.role})
    
    # [핵심] 쿠키에 토큰 심기 (자동 로그인 구현)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,   # 자바스크립트에서 탈취 불가능하게 설정 (보안)
        samesite="Lax",  # CSRF 보호
        secure=False     # HTTPS 적용 전이므로 False (배포 시 True로 변경)
    )
    return {"message": "로그인 성공", "role": user.role}

# 로그아웃 (쿠키 삭제) 
@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "로그아웃 되었습니다."}

# 회원가입
@app.post("/users", status_code=201)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(status_code=400, detail="이미 존재하는 이메일")
    hashed_pw = auth.get_password_hash(user.password)
    new_user = models.User(email=user.email, password=hashed_pw, name=user.name, role=user.role.value)
    db.add(new_user)
    db.commit()
    return {"email": user.email, "role": user.role}

# --- [2] 관리자(Admin) 영역: 강의(Course) 관리 ---
@app.post("/admin/courses", response_model=schemas.CourseResponse, status_code=201)
def create_course_admin(
    course: schemas.CourseCreate, 
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # 관리자만 강의를 개설할 수 있음
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="관리자(Admin)만 강의를 개설할 수 있습니다.")

    new_course = models.Course(
        title=course.title, 
        semester=course.semester, 
        instructor_id=current_user.id # 임시로 관리자 본인 할당 or 추후 수정 가능
    )
    db.add(new_course)
    db.commit()
    return new_course

# --- [3] 교원(Instructor) 영역: 수업(Session) 및 출석 관리 ---
@app.post("/instructor/courses/{course_id}/sessions", response_model=schemas.SessionResponse)
def create_session_instructor(
    course_id: int,
    session: schemas.SessionCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # 교원만 수업 일정을 만들 수 있음
    if current_user.role != "INSTRUCTOR":
        raise HTTPException(status_code=403, detail="담당 교원만 수업을 생성할 수 있습니다.")
    
    # (추가 검증 로직 가능: 본인이 담당한 과목인지 확인)
    
    new_session = models.ClassSession(
        course_id=course_id,
        week_number=session.week_number,
        session_date=session.session_date,
        attendance_method=session.attendance_method
    )
    db.add(new_session)
    db.commit()
    return new_session

@app.post("/instructor/sessions/{session_id}/open")
def open_attendance(session_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "INSTRUCTOR":
        raise HTTPException(status_code=403, detail="권한 없음")
    
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    session.is_open = True
    db.commit()
    return {"message": "출석 시작"}

# --- [4] 학생(Student) 영역: 출석 및 공결 ---
# main.py 의 기존 attend_student 함수를 이걸로 교체하세요.

@app.post("/student/sessions/{session_id}/attend")
def attend_student(
    session_id: int, 
    code: str = None, # 인증번호 파라미터 추가
    current_user: models.User = Depends(auth.get_current_user), 
    db: Session = Depends(get_db)
):
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    
    # 1. 기본 체크 (수업 존재 여부, 오픈 여부)
    if not session:
        raise HTTPException(status_code=404, detail="수업이 없습니다.")
    if not session.is_open:
        raise HTTPException(status_code=400, detail="출석체크 시간이 아닙니다.")
    
    # 2. [NEW] 인증번호 방식일 경우 번호 검사 
    if session.attendance_method == 'AUTH_CODE':
        if not code:
            raise HTTPException(status_code=400, detail="인증번호를 입력해주세요.")
        if code != session.auth_code:
            raise HTTPException(status_code=400, detail="인증번호가 틀렸습니다.")

    # 3. 중복 출석 방지
    if db.query(models.Attendance).filter_by(session_id=session_id, student_id=current_user.id).first():
        raise HTTPException(status_code=400, detail="이미 출석하셨습니다.")

    # 4. 출석 저장
    db.add(models.Attendance(session_id=session_id, student_id=current_user.id, status=1))
    db.commit()
    return {"status": "출석 완료"}

@app.post("/courses/{course_id}/enroll")
def enroll_course(course_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if db.query(models.Enrollment).filter_by(user_id=current_user.id, course_id=course_id).first():
        raise HTTPException(status_code=400, detail="이미 수강 중")
    db.add(models.Enrollment(user_id=current_user.id, course_id=course_id))
    db.commit()
    return {"message": "수강신청 완료"}

# --- main.py 기존 코드 사이에 추가 ---

# [NEW] 학생용 메인 대시보드 데이터 (수강 목록 + 출석률)
@app.get("/student/dashboard", response_model=list[schemas.CourseReportResponse])
def get_student_dashboard(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # 1. 내가 수강 중인 강의 목록 찾기
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.user_id == current_user.id).all()
    
    dashboard_data = []
    
    for enroll in enrollments:
        course = db.query(models.Course).filter(models.Course.id == enroll.course_id).first()
        
        # 2. 각 강의별 나의 출석률 계산
        total_sessions = db.query(models.ClassSession).filter(models.ClassSession.course_id == course.id).count()
        
        attended_count = db.query(models.Attendance).join(models.ClassSession).filter(
            models.ClassSession.course_id == course.id,
            models.Attendance.student_id == current_user.id,
            models.Attendance.status.in_([1, 4]) # 출석, 공결
        ).count()
        
        rate = (attended_count / total_sessions * 100) if total_sessions > 0 else 0.0
        
        # 리포트 형식 재활용 (학생 본인 데이터만 담음)
        student_stat = schemas.StudentReport(
            student_name=current_user.name,
            total_sessions=total_sessions,
            attended_count=attended_count,
            attendance_rate=round(rate, 1)
        )
        
        dashboard_data.append(schemas.CourseReportResponse(
            course_title=course.title,
            reports=[student_stat] # 리스트지만 나 혼자만 들어감
        ))
        
    return dashboard_data

# [NEW] 특정 강의의 상세 주차 정보 및 내 출석 상태 조회
# 기존 API를 보완하여 "내가 출석했는지 여부(my_status)"를 함께 내려줍니다.
@app.get("/student/courses/{course_id}/sessions")
def get_student_sessions(
    course_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    sessions = db.query(models.ClassSession).filter(models.ClassSession.course_id == course_id).all()
    
    result = []
    for s in sessions:
        # 이 세션에 대한 나의 출석 기록 조회
        att = db.query(models.Attendance).filter_by(
            session_id=s.id, 
            student_id=current_user.id
        ).first()
        
        my_status = att.status if att else 0 # 0:미정, 1:출석...
        
        result.append({
            "id": s.id,
            "week_number": s.week_number,
            "session_date": s.session_date,
            "is_open": s.is_open,
            "attendance_method": s.attendance_method,
            "my_status": my_status # [중요] 프론트에서 버튼 활성화 여부 결정
        })
    return result

# --- [누락된 기능 복원] ---

# 1. 내 정보 보기 (프론트엔드 대시보드에서 사용)
@app.get("/users/me", response_model=schemas.UserResponse)
def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

# 2. 강의 리포트 보기 (통계 확인용)
# 학생도 자기 통계를 봐야 하므로 권한 체크를 완화했습니다.
@app.get("/courses/{course_id}/report", response_model=schemas.CourseReportResponse)
def get_course_report(
    course_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # 강의 정보 가져오기
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="강의가 없습니다.")

    # 이 강의를 듣는 모든 학생 찾기
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.course_id == course_id).all()
    total_sessions = db.query(models.ClassSession).filter(models.ClassSession.course_id == course_id).count()
    
    report_list = []

    for enrollment in enrollments:
        student = db.query(models.User).filter(models.User.id == enrollment.user_id).first()
        
        # 출석(1) + 공결(4) 횟수
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
        
    return schemas.CourseReportResponse(
        course_title=course.title,
        reports=report_list
    )
# --- [교수용 기능 추가] main.py 에 추가해주세요 ---
import random
import string

# 1. 교수용 대시보드 (담당 강의 목록)
@app.get("/instructor/dashboard", response_model=list[schemas.CourseResponse])
def get_instructor_dashboard(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "INSTRUCTOR":
        raise HTTPException(status_code=403, detail="교수 권한이 필요합니다.")
    
    return db.query(models.Course).filter(models.Course.instructor_id == current_user.id).all()

# 2. 특정 강의의 주차별 수업 목록 (교수용)
@app.get("/instructor/courses/{course_id}/sessions")
def get_instructor_sessions(
    course_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # 본인 강의인지 확인 로직은 생략 (서비스 레벨에선 필요)
    return db.query(models.ClassSession).filter(models.ClassSession.course_id == course_id).all()

# 3. 수업 상태 변경 (출석 시작/마감 및 인증번호 생성) [cite: 11]
@app.patch("/sessions/{session_id}/status")
def update_session_status(
    session_id: int,
    is_open: bool,
    method: str = "ELECTRONIC", # ELECTRONIC, AUTH_CODE
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "INSTRUCTOR":
        raise HTTPException(status_code=403, detail="권한 없음")
        
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    session.is_open = is_open
    session.attendance_method = method
    
    # 인증번호 방식이고, 문을 열 때(True) 인증번호가 없다면 생성
    if is_open and method == 'AUTH_CODE' and not session.auth_code:
        # 4자리 숫자 랜덤 생성
        session.auth_code = ''.join(random.choices(string.digits, k=4))
        
    db.commit()
    return {"message": "상태 변경 완료", "auth_code": session.auth_code}

# 4. 실시간 출석 현황 조회 (24/30명) [cite: 5]
@app.get("/sessions/{session_id}/stat")
def get_session_live_stat(
    session_id: int,
    db: Session = Depends(get_db)
):
    # 1. 전체 수강생 수 (Enrollment)
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    total_students = db.query(models.Enrollment).filter(models.Enrollment.course_id == session.course_id).count()
    
    # 2. 현재 출석한 인원 수
    attended_count = db.query(models.Attendance).filter(
        models.Attendance.session_id == session_id,
        models.Attendance.status.in_([1, 4])
    ).count()
    
    return {
        "total": total_students,
        "attended": attended_count,
        "auth_code": session.auth_code # 화면 표시용
    }
# --- [교수용 명부 관리 API 추가] main.py ---

# 5. 특정 수업의 출석부 조회 (명단 + 상태)
@app.get("/instructor/sessions/{session_id}/attendances")
def get_session_attendances(
    session_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "INSTRUCTOR":
        raise HTTPException(status_code=403, detail="권한 없음")

    # 1. 수업 정보
    session = db.query(models.ClassSession).filter(models.ClassSession.id == session_id).first()
    
    # 2. 수강생 전체 목록 (Enrollment 기준)
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.course_id == session.course_id).all()
    
    roster = []
    for enroll in enrollments:
        student = db.query(models.User).filter(models.User.id == enroll.user_id).first()
        
        # 3. 출석 기록 조회 (없으면 0:미정)
        att = db.query(models.Attendance).filter_by(
            session_id=session_id, 
            student_id=student.id
        ).first()
        
        status_code = att.status if att else 0
        
        roster.append({
            "student_id": student.id,
            "student_name": student.name,
            "email": student.email,
            "status": status_code,
            "attendance_id": att.id if att else None
        })
        
    return roster

# 6. 출석 상태 직권 수정 (교수 권한)
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

    # 기존 기록 찾기
    att = db.query(models.Attendance).filter_by(
        session_id=session_id, 
        student_id=update_data.student_id
    ).first()

    if att:
        att.status = update_data.status # 상태 업데이트
    else:
        # 기록이 없으면 새로 생성 (미정 -> 출석 등)
        new_att = models.Attendance(
            session_id=session_id,
            student_id=update_data.student_id,
            status=update_data.status
        )
        db.add(new_att)
    
    db.commit()
    return {"message": "수정되었습니다."}
# --- [추가됨] 웹페이지(Static) 연결 설정 ---
# static 폴더 안의 파일들을 주소로 접근 가능하게 함
app.mount("/static", StaticFiles(directory="static"), name="static")

# 접속 시 로그인 페이지(index.html) 보여주기
@app.get("/")
def read_root():
    return FileResponse('static/index.html')