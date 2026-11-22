from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, now
from ..security import admin_only, create_token, current_user, hash_password, verify_password
from ..seed import seed_base, seed_sample
from ..services import audit, get_or_404, save_settings, to_dict

router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["users"])


def user_out(u: User) -> dict:
    return to_dict(u, exclude={"password_hash", "token_version", "failed_logins", "locked_until"})


class SetupIn(BaseModel):
    restaurant_name: str = Field(min_length=2)
    full_name: str = ""
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)
    load_sample_data: bool = False


class LoginIn(BaseModel):
    username: str
    password: str


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return {"needs_setup": db.scalar(select(func.count(User.id))) == 0}


@router.post("/setup")
def setup(body: SetupIn, db: Session = Depends(get_db)):
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(400, "Setup is already complete")
    u = User(username=body.username.strip().lower(), full_name=body.full_name or body.username,
             password_hash=hash_password(body.password), role="admin",
             can_edit_price=True, can_discount=True, can_cancel_bill=True)
    db.add(u)
    save_settings(db, {"restaurant_name": body.restaurant_name})
    seed_base(db)
    if body.load_sample_data:
        seed_sample(db, u.username)
    audit(db, u.username, "SETUP", "system", details={"sample": body.load_sample_data})
    db.commit()
    return {"token": create_token(u), "user": user_out(u)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalars(select(User).where(User.username == body.username.strip().lower())).first()
    if u and u.locked_until and u.locked_until > now():
        raise HTTPException(423, "Too many failed attempts. Try again in a few minutes")
    if not u or not u.is_active or not verify_password(body.password, u.password_hash):
        if u:
            u.failed_logins += 1
            if u.failed_logins >= 5:
                u.locked_until = now() + timedelta(minutes=10)
                u.failed_logins = 0
            db.commit()
        raise HTTPException(401, "Invalid username or password")
    u.failed_logins = 0
    u.locked_until = None
    audit(db, u, "LOGIN", "user", u.id)
    db.commit()
    return {"token": create_token(u), "user": user_out(u)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


@router.post("/change-password")
def change_password(body: PasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is wrong")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    audit(db, user, "CHANGE_PASSWORD", "user", user.id)
    db.commit()
    return {"token": create_token(user)}


# ---------------- users (admin) ----------------
class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str = ""
    password: str | None = None
    role: str = Field(pattern="^(admin|manager|cashier)$")
    can_edit_price: bool = False
    can_discount: bool = True
    can_cancel_bill: bool = False
    is_active: bool = True


@users_router.get("")
def list_users(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.username))]


@users_router.post("")
def create_user(body: UserIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    name = body.username.strip().lower()
    if db.scalars(select(User).where(User.username == name)).first():
        raise HTTPException(400, "Username already exists")
    if not body.password or len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    u = User(username=name, full_name=body.full_name, password_hash=hash_password(body.password),
             role=body.role, can_edit_price=body.can_edit_price, can_discount=body.can_discount,
             can_cancel_bill=body.can_cancel_bill, is_active=body.is_active)
    db.add(u)
    audit(db, admin, "CREATE_USER", "user", name)
    db.commit()
    return user_out(u)


@users_router.put("/{user_id}")
def update_user(user_id: int, body: UserIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    u = get_or_404(db, User, user_id, "User")
    if u.id == admin.id and (body.role != "admin" or not body.is_active):
        raise HTTPException(400, "You cannot remove your own admin access")
    if body.password or body.role != u.role or not body.is_active:
        u.token_version += 1  # force re-login
    u.full_name, u.role, u.is_active = body.full_name, body.role, body.is_active
    u.can_edit_price, u.can_discount, u.can_cancel_bill = body.can_edit_price, body.can_discount, body.can_cancel_bill
    if body.password:
        if len(body.password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")
        u.password_hash = hash_password(body.password)
    audit(db, admin, "UPDATE_USER", "user", u.username)
    db.commit()
    return user_out(u)
