"""Create the first local/staging administrator without changing existing accounts.

Run only through the identified Compose API container. The command prompts on the
controlling terminal; it never accepts or prints credentials as arguments.
"""

from getpass import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select, text

from app.core.config import settings
from app.core.db import SyncSessionLocal
from app.core.security import hash_password
from app.models.learning import Grade, Student, User


ALLOWED_ENVIRONMENTS = {"development", "local", "staging"}
CONFIRMATION = "CREATE_INITIAL_ADMIN"


def bootstrap_allowed(environment: str) -> bool:
    return environment.strip().lower() in ALLOWED_ENVIRONMENTS


def validated_email(value: str) -> str:
    return str(TypeAdapter(EmailStr).validate_python(value.strip())).lower()


def main() -> None:
    if not bootstrap_allowed(settings.ENVIRONMENT):
        raise RuntimeError("Initial-admin bootstrap is restricted to local or staging environments.")

    with SyncSessionLocal() as session:
        database_name, database_user = session.execute(text("SELECT current_database(), current_user")).one()
        print(f"Connected database: {database_name}; database role: {database_user}")
        if session.scalar(select(User.id).where(User.is_admin.is_(True)).limit(1)) is not None:
            print("An administrator already exists. No changes were made.")
            return

        email_input = input("Administrator email: ")
        try:
            email = validated_email(email_input)
        except ValidationError as exc:
            raise RuntimeError("A valid administrator email is required.") from exc
        password = getpass("Administrator password (minimum 12 characters): ")
        confirm_password = getpass("Confirm administrator password: ")
        if len(password) < 12:
            raise RuntimeError("Administrator password must contain at least 12 characters.")
        if password != confirm_password:
            raise RuntimeError("Passwords do not match.")
        if input(f"Type {CONFIRMATION} to create the first administrator in this database: ") != CONFIRMATION:
            raise RuntimeError("No database modification was authorized.")

        # Recheck immediately before the transaction writes, so a concurrent
        # bootstrap cannot silently create another first administrator.
        if session.scalar(select(User.id).where(User.is_admin.is_(True)).limit(1)) is not None:
            print("An administrator already exists. No changes were made.")
            return
        if session.scalar(select(User.id).where(User.email == email).limit(1)) is not None:
            raise RuntimeError("A user with that email already exists; refusing to modify or elevate it.")
        grade = session.scalar(select(Grade).where(Grade.name == "Class 10"))
        if grade is None:
            raise RuntimeError("Class 10 grade is missing; seed grades before creating the administrator.")

        user = User(email=email, password_hash=hash_password(password), is_admin=True)
        session.add(user)
        session.flush()
        session.add(Student(user_id=user.id, grade_id=grade.id, display_name="Administrator"))
        session.commit()
    print("Initial administrator created. No credentials, hashes, or tokens were displayed.")


if __name__ == "__main__":
    main()
