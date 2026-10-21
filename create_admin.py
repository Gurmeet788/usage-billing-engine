from getpass import getpass

from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Tenant, User

password_hash = PasswordHash.recommended()


def create_admin():
    db: Session = SessionLocal()

    try:
        email = input("Admin email: ").strip().lower()

        existing_user = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        if existing_user:
            print("This email is already registered.")
            return

        password = getpass("Admin password (minimum 8 characters): ")

        if len(password) < 8 or len(password) > 128:
            print("Password must be between 8 and 128 characters.")
            return

        # Create a dedicated platform tenant.
        tenant = Tenant(name="Platform Administration")
        db.add(tenant)
        db.flush()

        admin = User(
            tenant_id=tenant.id,
            email=email,
            hashed_password=password_hash.hash(password),
            role="admin",
            is_active=True
        )

        db.add(admin)
        db.commit()

        print("Platform admin created successfully.")
        print(f"Admin email: {email}")
        print(f"Admin user ID: {admin.id}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    create_admin()