"""
数据库初始化脚本
- 创建默认用户
- 创建默认课程
首次运行后端前执行一次
"""

from database import SessionLocal
from models import User, Course
from datetime import datetime, timezone
from auth import hash_password

def init_default_user():
    db = SessionLocal()
    try:
        # check if default user already exists
        existing = db.query(User).filter(User.id == 1).first()
        if existing:
            print(f"Default user already exists: {existing.email}")
            return existing

        # create default user
        default_user = User(
            id=1,
            email="default@eduprep.local",
            name="Default User",
            password_hash=hash_password("placeholder") 
        )
        db.add(default_user)
        db.commit()
        db.refresh(default_user)
        print(f"Created default user: {default_user.email}")
        return default_user

    finally:
        db.close()

def init_default_course():
    db = SessionLocal()
    try:
        existing = db.query(Course).filter(Course.id == 1).first()
        if existing:
            print(f"Default course already exists: {existing.title}")
            return existing

        default_course = Course(
            id=1,
            user_id=1,
            title="Default Course"
        )
        db.add(default_course)
        db.commit()
        db.refresh(default_course)
        print(f"Created default course: {default_course.title}")
        return default_course

    finally:
        db.close()


if __name__ == "__main__":
    print("Initializing database...")
    init_default_user()
    init_default_course()
    print("Done.")