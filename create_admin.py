# create_admin.py
from database import SessionLocal
import models
import auth

def init_admin():
    db = SessionLocal()
    print("🚀 초기 관리자 계정 생성 시작...")

    try:
        # 1. 관리자용 '본부' 학과 생성 (없으면)
        admin_dept = db.query(models.Department).filter_by(name="대학본부").first()
        if not admin_dept:
            admin_dept = models.Department(name="대학본부")
            db.add(admin_dept)
            db.commit()
            db.refresh(admin_dept)
            print(f"✅ '대학본부' 학과 생성 완료 (ID: {admin_dept.id})")
        else:
            print(f"ℹ️ '대학본부' 학과가 이미 존재합니다. (ID: {admin_dept.id})")

        # 2. 관리자 계정 생성
        # 이메일: admin@inoxde.com / 비번: admin1234
        admin_email = "admin@inoxde.com"
        
        existing_admin = db.query(models.User).filter_by(email=admin_email).first()
        if not existing_admin:
            hashed_pw = auth.get_password_hash("admin1234")
            admin_user = models.User(
                email=admin_email,
                password=hashed_pw,
                name="시스템관리자",
                role="ADMIN",
                department_id=admin_dept.id
            )
            db.add(admin_user)
            db.commit()
            print(f"🎉 관리자 계정 생성 완료! [ID: {admin_email} / PW: admin1234]")
        else:
            print("ℹ️ 관리자 계정이 이미 존재합니다.")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_admin()