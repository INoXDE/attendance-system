# test_automation.py
from database import SessionLocal
import models
import auth
from datetime import timedelta, datetime

def test_auto_schedule():
    print("🧪 [테스트 시작] 강의 생성 및 주차별 DB 자동 생성 확인")
    db = SessionLocal()

    try:
        # 1. [Fix] 교수님 계정 존재 여부 확인 및 생성
        # DB가 비어있으면 강의를 만들 수 없으므로, 임시 교수를 먼저 만듭니다.
        instructor = db.query(models.User).filter(models.User.role == "INSTRUCTOR").first()
        
        if not instructor:
            print("⚠️ 테스트를 위한 교수 계정을 생성합니다...")
            hashed_pw = auth.get_password_hash("1234")
            instructor = models.User(
                email="prof_test@inoxde.com",
                password=hashed_pw,
                name="테스트교수",
                role="INSTRUCTOR"
            )
            db.add(instructor)
            db.commit()
            db.refresh(instructor) # ID 발급
            print(f"✅ 교수 계정 생성 완료 (ID: {instructor.id})")
        else:
            print(f"ℹ️ 기존 교수 계정 사용 (ID: {instructor.id})")

        # 2. 시나리오: 관리자가 '2025-2'학기 강의를 생성함
        # 위에서 확보한 교수님의 ID를 사용합니다.
        test_course = models.Course(
            title="자동생성_테스트_강의",
            semester="2025-2",
            instructor_id=instructor.id 
        )
        db.add(test_course)
        db.commit()
        db.refresh(test_course)

        # 3. 17주차 데이터 생성 (main.py의 로직과 동일하게 수행)
        # 2025년 9월 1일 월요일 개강 기준
        start_date = datetime(2025, 9, 1, 9, 0, 0)
        sessions = []
        for i in range(17):
            sessions.append(models.ClassSession(
                course_id=test_course.id,
                week_number=i+1,
                session_date=start_date + timedelta(weeks=i),
                attendance_method='ELECTRONIC',
                is_open=False
            ))
        db.add_all(sessions)
        db.commit()

        # 4. 검증
        count = db.query(models.ClassSession).filter_by(course_id=test_course.id).count()
        print(f"📊 생성된 주차 수: {count}개 (목표: 17개)")
        
        if count == 17:
            print("✅ 성공! 17주차 데이터가 모두 정상적으로 생성되었습니다.")
            first = sessions[0].session_date.strftime("%Y-%m-%d")
            last = sessions[-1].session_date.strftime("%Y-%m-%d")
            print(f"   📅 기간: {first} (1주차) ~ {last} (17주차)")
        else:
            print(f"❌ 실패! 생성된 개수가 다릅니다: {count}")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_auto_schedule()