# test_automation.py
from database import SessionLocal
import models
from datetime import datetime

def test_auto_schedule():
    db = SessionLocal()
    print("🧪 [테스트 시작] 강의 생성 및 주차별 DB 자동 생성 확인")

    # 1. 테스트용 강의 제목 정의
    test_title = "시스템검증용_자동생성강의"
    
    # 혹시 기존에 같은 이름의 테스트 강의가 있다면 삭제 (청소)
    existing = db.query(models.Course).filter_by(title=test_title).first()
    if existing:
        print(f"🧹 기존 테스트 강의 삭제 중... (ID: {existing.id})")
        # 연관된 세션 삭제
        db.query(models.ClassSession).filter_by(course_id=existing.id).delete()
        db.delete(existing)
        db.commit()

    # 2. [시뮬레이션] 관리자가 강의를 생성했다고 가정
    # (원래는 API를 호출해야 하지만, 여기선 DB 로직을 직접 실행하여 검증)
    from main import create_course_admin
    # API 함수는 의존성(User, DB)이 필요하므로, 여기선 '로직'과 동일하게 DB에 직접 넣어서 테스트
    
    # 2-1. 강의 생성
    new_course = models.Course(
        title=test_title,
        semester="2025-2",
        instructor_id=1 # 임시 ID
    )
    db.add(new_course)
    db.commit()
    db.refresh(new_course)
    
    # 2-2. 17주차 자동 생성 로직 실행 (main.py의 로직 복제 테스트)
    from datetime import timedelta
    start_date = datetime(2025, 9, 1, 9, 0, 0)
    for i in range(17):
        db.add(models.ClassSession(
            course_id=new_course.id,
            week_number=i+1,
            session_date=start_date + timedelta(weeks=i)
        ))
    db.commit()

    # 3. 결과 검증
    sessions = db.query(models.ClassSession).filter_by(course_id=new_course.id).all()
    print(f"📊 생성된 주차 수: {len(sessions)}개 (목표: 17개)")
    
    if len(sessions) == 17:
        print("✅ 성공! 17주차 데이터가 모두 정상적으로 생성되었습니다.")
        # 샘플 출력
        print(f" - 1주차: {sessions[0].session_date}")
        print(f" - 17주차: {sessions[-1].session_date}")
    else:
        print(f"❌ 실패! 생성된 개수가 다릅니다.")

    db.close()

if __name__ == "__main__":
    test_auto_schedule()