from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List
from datetime import datetime
import secrets
from bson import ObjectId

# Models
from models.admin import (
    AdminCreate, AdminLogin, AdminResponse, 
    AdminUpdate, ChangePassword, TokenResponse
)
from models.access_request import AccessRequestUpdate
from models.otp import OTPRequest, OTPVerify, OTPResponse
from models.user import UserResponse

# Services
from services.admin_service import AdminService
from services.auth_service import AuthService
from services.otp_service import OTPService
from services.email_service import EmailService

# Database
from database import (
    admin_users_collection,
    users_collection,
    access_requests_collection,
    access_tokens_collection,
    audit_logs_collection
)


# Router Setup

admin_auth_router = APIRouter(prefix="/api/admin-auth", tags=["Admin Authentication"])
admin_router = APIRouter(prefix="/api/admin", tags=["Admin Management"])
auth_router = APIRouter(prefix="/api/auth", tags=["User Authentication"])
security = HTTPBearer()



# Authentication Dependencies


def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current authenticated admin from token"""
    token = credentials.credentials
    payload = AuthService.verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    admin = AdminService.get_admin_by_id(payload["sub"])
    
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin not found"
        )
    
    if not admin.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    return admin


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current authenticated user (regular user) from token"""
    token = credentials.credentials
    payload = AuthService.verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    user = users_collection.find_one({"_id": ObjectId(payload["sub"])})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regular user not found"
        )
    
    if not user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    return user


def get_current_user_or_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get current authenticated user from token
    Works for both admins (including super admin) and regular users
    """
    token = credentials.credentials
    payload = AuthService.verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    # Check if in admin collection
    user = admin_users_collection.find_one({"_id": ObjectId(payload["sub"])})
    
    # Check if in user collection
    if not user:
        user = users_collection.find_one({"_id": ObjectId(payload["sub"])})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in system"
        )
    
    if not user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    return user



# Authorization Dependencies


def require_super_admin(current_admin: dict = Depends(get_current_admin)):
    """Require super admin role"""
    if not AdminService.is_super_admin(current_admin["role"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )
    return current_admin


def require_admin(current_admin: dict = Depends(get_current_admin)):
    """Require admin or super admin role"""
    if not AdminService.is_admin_or_above(current_admin["role"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_admin



# Admin Auth Routes - Public


@admin_auth_router.post("/register", response_model=dict)
def register_user(admin: AdminCreate):
    """Register a new user (public endpoint)"""
    try:
        result = AdminService.create_admin(
            email=admin.email,
            password=admin.password,
            full_name=admin.full_name,
            role="user"  
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@admin_auth_router.post("/login", response_model=TokenResponse)
def login(credentials: AdminLogin):
    """Login with username/email and password"""
    try:
        # Authenticate user
        user = AdminService.authenticate(credentials.username, credentials.password)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username/email or password"
            )
        
        # Create JWT token
        token_data = {
            "sub": user["id"],
            "email": user["email"],
            "role": user["role"],
            "is_super_admin": user.get("is_super_admin", False)
        }
        
        access_token = AuthService.create_access_token(token_data)
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user={
                "id": user["id"],
                "email": user["email"],
                "username": user.get("username"),
                "full_name": user["full_name"],
                "role": user["role"],
                "is_super_admin": user.get("is_super_admin", False)
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))



# Admin Auth Routes - Protected


@admin_auth_router.get("/me", response_model=AdminResponse)
def get_current_admin_info(current_admin: dict = Depends(get_current_admin)):
    """Get current admin information"""
    return AdminResponse(**current_admin)


@admin_auth_router.put("/me", response_model=dict)
def update_current_admin(
    update: AdminUpdate,
    current_admin: dict = Depends(get_current_admin)
):
    """Update current admin profile (except role)"""
    update_data = {}
    
    if update.full_name:
        update_data["full_name"] = update.full_name
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid fields to update"
        )
    
    success = AdminService.update_admin(current_admin["id"], update_data)
    
    if success:
        return {"message": "Profile updated successfully"}
    
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Update failed"
    )


@admin_auth_router.post("/change-password", response_model=dict)
def change_password(
    password_data: ChangePassword,
    current_admin: dict = Depends(get_current_admin)
):
    """Change password"""
    try:
        success = AdminService.change_password(
            current_admin["id"],
            password_data.current_password,
            password_data.new_password
        )
        
        if success:
            return {"message": "Password changed successfully"}
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password change failed"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))



# Admin Management Routes - Admin Only


@admin_router.get("/users", response_model=List[AdminResponse])
def list_all_users(current_admin: dict = Depends(require_admin)):
    """List all users (Admin+ only)"""
    users = AdminService.get_all_admins()
    return [AdminResponse(**user) for user in users]


@admin_router.get("/users/{user_id}", response_model=AdminResponse)
def get_user(user_id: str, current_admin: dict = Depends(require_admin)):
    """Get specific user details (Admin+ only)"""
    user = AdminService.get_admin_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return AdminResponse(**user)



# Admin Management Routes - Super Admin Only


@admin_router.post("/users", response_model=dict)
def create_user_or_admin(
    admin: AdminCreate,
    current_admin: dict = Depends(require_super_admin)
):
    """Create new user, admin, or super admin (Super Admin only)"""
    try:
        result = AdminService.create_admin(
            email=admin.email,
            password=admin.password,
            full_name=admin.full_name,
            role=admin.role
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@admin_router.put("/users/{user_id}", response_model=dict)
def update_user(
    user_id: str,
    update: AdminUpdate,
    current_admin: dict = Depends(require_super_admin)
):
    """Update any user including role (Super Admin only)"""
    update_data = {}
    
    if update.full_name:
        update_data["full_name"] = update.full_name
    if update.role:
        update_data["role"] = update.role
    if update.is_active is not None:
        update_data["is_active"] = update.is_active
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid fields to update"
        )
    
    success = AdminService.update_admin(user_id, update_data)
    
    if success:
        return {"message": "User updated successfully"}
    
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Update failed"
    )


@admin_router.delete("/users/{user_id}", response_model=dict)
def delete_user(
    user_id: str,
    current_admin: dict = Depends(require_super_admin)
):
    """Deactivate user account (Super Admin only)"""
    if user_id == current_admin["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )
    
    success = AdminService.delete_admin(user_id)
    
    if success:
        return {"message": "User deactivated successfully"}
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User not found"
    )


@admin_router.post("/users/{user_id}/activate", response_model=dict)
def activate_user(
    user_id: str,
    current_admin: dict = Depends(require_super_admin)
):
    """Reactivate user account (Super Admin only)"""
    success = AdminService.update_admin(user_id, {"is_active": True})
    
    if success:
        return {"message": "User activated successfully"}
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User not found"
    )



# Investor Management Routes

@admin_router.get("/investors", response_model=List[dict])
def list_investors(
    current_admin: dict = Depends(require_admin)
):
    """List all investors (Admin only)"""
    # First try to get investors with is_active=True
    investors = list(investors_collection.find({"is_active": True}).sort("full_name", 1))
    
    # If no active investors, try getting all investors (legacy support)
    if not investors:
        investors = list(investors_collection.find({}).sort("full_name", 1))
    
    # If still no investors, fall back to approved access requests
    if not investors:
        approved_requests = list(access_requests_collection.find({"status": "approved"}).sort("full_name", 1))
        for req in approved_requests:
            investors.append({
                "_id": req["_id"],
                "email": req.get("email", ""),
                "full_name": req.get("full_name", ""),
                "company": req.get("company", ""),
                "investor_id": req.get("investor_id", ""),
                "created_at": req.get("created_at") or req.get("requested_at"),
            })
    
    result = []
    for investor in investors:
        result.append({
            "id": str(investor["_id"]),
            "email": investor.get("email", ""),
            "full_name": investor.get("full_name", ""),
            "company": investor.get("company", ""),
            "investor_id": investor.get("investor_id", ""),
            "created_at": investor.get("created_at", "").isoformat() if investor.get("created_at") else None,
        })
    
    return result


# Access Request Management Routes


@admin_router.get("/access-requests", response_model=List[dict])
def list_access_requests(
    request_status: str = None,
    current_admin: dict = Depends(require_admin)
):
    """List access requests with optional status filter"""
    query = {"status": request_status} if request_status else {}
    requests = list(access_requests_collection.find(query))
    
    for req in requests:
        req["id"] = str(req.pop("_id"))
    
    return requests


@admin_router.put("/access-requests/{request_id}", response_model=dict)
def update_access_request(
    request_id: str,
    update: AccessRequestUpdate,
    current_admin: dict = Depends(require_admin)
):
    """Update access request status"""
    try:
        request = access_requests_collection.find_one({"_id": ObjectId(request_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request ID"
        )
    
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found"
        )
    
    previous_status = request["status"]
    update_data = {
        "status": update.status,
        "updated_at": datetime.utcnow()
    }
    
    if update.admin_notes:
        update_data["admin_notes"] = update.admin_notes
    
    access_requests_collection.update_one(
        {"_id": ObjectId(request_id)},
        {"$set": update_data}
    )
    
    # Log the action
    audit_logs_collection.insert_one({
        "access_request_id": request_id,
        "action": "status_change",
        "previous_status": previous_status,
        "new_status": update.status,
        "admin_id": current_admin["id"],
        "admin_email": current_admin["email"],
        "notes": update.admin_notes,
        "timestamp": datetime.utcnow()
    })
    
    # Handle status changes
    if update.status == "approved":
        token = secrets.token_urlsafe(32)
        access_tokens_collection.insert_one({
            "access_request_id": request_id,
            "token": token,
            "email": request["email"],
            "expires_at": update.expires_at,
            "is_active": True,
            "created_at": datetime.utcnow()
        })
        EmailService.send_access_approved(
            request["email"],
            request["full_name"],
            token
        )
    
    elif update.status == "denied":
        EmailService.send_access_denied(
            request["email"],
            request["full_name"],
            update.admin_notes or "No reason provided"
        )
    
    return {"message": "Access request updated successfully"}


@admin_router.delete("/access-requests/{request_id}", response_model=dict)
def delete_access_request(
    request_id: str,
    current_admin: dict = Depends(require_admin)
):
    """Delete an access request"""
    try:
        obj_id = ObjectId(request_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request ID"
        )
    
    result = access_requests_collection.delete_one({"_id": obj_id})
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found"
        )
        
    # Log the action
    audit_logs_collection.insert_one({
        "access_request_id": request_id,
        "action": "delete",
        "admin_id": current_admin["id"],
        "admin_email": current_admin["email"],
        "timestamp": datetime.utcnow()
    })
    
    return {"message": "Access request deleted successfully"}


# User Authentication Routes - OTP


# @auth_router.post("/request-otp", response_model=OTPResponse)
# def request_otp(otp_request: OTPRequest):
#     """Request OTP for user login"""
#     user = users_collection.find_one({"email": otp_request.email})
    
#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="User not found"
#         )
    
#     if not user.get("is_active", False):
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="User account is inactive"
#         )
    
#     success = OTPService.send_otp(otp_request.email)
    
#     if not success:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to send OTP"
#         )
    
#     return OTPResponse(
#         message="OTP sent successfully to your email",
#         expires_in_minutes=10
#     )


# @auth_router.post("/verify-otp", response_model=dict)
# def verify_otp(otp_verify: OTPVerify):
#     """Verify OTP and return access token"""
#     result = OTPService.verify_otp(otp_verify.email, otp_verify.otp_code)
    
#     if not result:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid or expired OTP"
#         )
    
#     # Create JWT access token
#     token_data = {
#         "sub": result["user_id"],
#         "email": result["email"],
#         "full_name": result["full_name"]
#     }
    
#     access_token = AuthService.create_access_token(token_data)
    
#     return {
#         "access_token": access_token,
#         "token_type": "bearer",
#         "user": {
#             "id": result["user_id"],
#             "email": result["email"],
#             "full_name": result["full_name"]
#         }
#     }


# @auth_router.get("/me", response_model=UserResponse)
# def get_current_user_info(user: dict = Depends(get_current_user)):
#     """Get current authenticated user information"""
#     user["id"] = str(user.pop("_id"))
#     return UserResponse(**user)
