"""Authentication API router with JWT, Role-Based Access Control, and Phone OTP."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.security import (
    create_access_token,
    get_current_active_user,
    get_password_hash,
    oauth2_scheme,
    decode_access_token,
    verify_password,
)
from ..db import get_db
from ..models.user import User, UserRole
from ..schemas.auth import PhoneOtpRequest, PhoneOtpVerify, TokenResponse, UserLogin, UserRegister, UserResponse
from ..services.audit import record_audit
from ..services.sms import send_sms

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserRegister,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    """Register a new user account.

    Protected: Only Admin users can register new users.
    Bootstrap exception: If no users exist in the database, initial admin creation is allowed.
    """
    total_users = db.query(User).count()
    current_admin = None

    if total_users > 0:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Admin authentication required to register users.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token_payload = decode_access_token(token)
        admin_id = token_payload.get("sub")
        current_admin = db.query(User).filter(User.id == int(admin_id)).first()
        if not current_admin or current_admin.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators are permitted to register users."
            )

    # Check if email is already registered (if provided)
    if payload.email:
        existing = db.query(User).filter(User.email == payload.email).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address already exists."
            )

    # Check if phone is already registered (if provided)
    if payload.phone:
        existing_phone = db.query(User).filter(User.phone == payload.phone).first()
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this phone number already exists."
            )

    # Create new user
    hashed_pwd = get_password_hash(payload.password) if payload.password else None
    new_user = User(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        hashed_password=hashed_pwd,
        role=payload.role,
        centre_id=payload.centre_id,
        preferred_language=payload.preferred_language,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Record audit log
    record_audit(
        db=db,
        action="create_user",
        entity_type="user",
        entity_id=new_user.id,
        actor_id=current_admin.id if current_admin else new_user.id,
        before=None,
        after={
            "id": new_user.id,
            "name": new_user.name,
            "email": new_user.email,
            "phone": new_user.phone,
            "role": new_user.role.value if hasattr(new_user.role, "value") else str(new_user.role),
            "centre_id": new_user.centre_id,
        },
        reason="User registration",
    )
    db.commit()

    return UserResponse(
        id=new_user.id,
        name=new_user.name,
        email=new_user.email,
        phone=new_user.phone,
        role=new_user.role.value if hasattr(new_user.role, "value") else str(new_user.role),
        centre_id=new_user.centre_id,
        preferred_language=new_user.preferred_language,
        is_active=new_user.is_active,
        created_at=new_user.created_at,
    )


@router.post("/login", response_model=TokenResponse)
def login(
    payload: UserLogin,
    db: Session = Depends(get_db),
):
    """Authenticate with email and password and receive a JWT access token (Staff / Admin)."""
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
    token = create_access_token(data={"sub": str(user.id), "role": role_str, "email": user.email})

    # Record audit log
    record_audit(
        db=db,
        action="login",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        before=None,
        after={"email": user.email, "role": role_str},
        reason="User login via email/password",
    )
    db.commit()

    user_resp = UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        role=role_str,
        centre_id=user.centre_id,
        preferred_language=user.preferred_language,
        is_active=user.is_active,
        created_at=user.created_at,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=user_resp,
    )


@router.post("/phone-otp/request")
def request_phone_otp(
    payload: PhoneOtpRequest,
    db: Session = Depends(get_db)
):
    """Request a login OTP for a farmer's mobile phone number."""
    phone = payload.phone.strip()
    dev_mock_otp = "123456"
    
    # Try sending via SMS service (in mock mode logs clearly)
    message_text = f"Your Kisan Setu login OTP is: {dev_mock_otp}. Valid for 10 minutes. (MOCK OTP)"
    send_sms(to_phone=phone, message=message_text)

    return {
        "status": "otp_sent",
        "phone": phone,
        "dev_mock_otp": dev_mock_otp,
        "message": "OTP sent successfully. (In dev mode, use OTP 123456)"
    }


@router.post("/phone-otp/verify", response_model=TokenResponse)
def verify_phone_otp(
    payload: PhoneOtpVerify,
    db: Session = Depends(get_db)
):
    """Verify phone OTP and authenticate farmer."""
    phone = payload.phone.strip()
    otp = payload.otp.strip()

    # Dev OTP check (always 123456)
    if otp != "123456":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP. In dev mode, please use '123456'."
        )

    # Find or auto-provision farmer user
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        user = User(
            name=f"Farmer {phone[-4:]}",
            phone=phone,
            role=UserRole.FARMER,
            is_active=True,
            preferred_language="en"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        record_audit(
            db=db,
            action="farmer_auto_register",
            entity_type="user",
            entity_id=user.id,
            actor_id=user.id,
            before=None,
            after={"phone": phone, "role": "farmer"},
            reason="Farmer phone OTP first-time login"
        )
        db.commit()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
    token = create_access_token(data={"sub": str(user.id), "role": role_str, "phone": user.phone})

    record_audit(
        db=db,
        action="login_otp",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        before=None,
        after={"phone": user.phone, "role": role_str},
        reason="User login via phone OTP",
    )
    db.commit()

    user_resp = UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        role=role_str,
        centre_id=user.centre_id,
        preferred_language=user.preferred_language,
        is_active=user.is_active,
        created_at=user.created_at,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=user_resp,
    )


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_active_user)
):
    """Fetch profile and role of currently authenticated user."""
    role_str = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    return UserResponse(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        phone=current_user.phone,
        role=role_str,
        centre_id=current_user.centre_id,
        preferred_language=current_user.preferred_language,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )
