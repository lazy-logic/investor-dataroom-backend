from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

from repositories.admin_repository import AdminRepository
from repositories.audit_log_repository import (
    AuditLogRepository,
)  # Add AuditLogRepository to top-level imports
from admin import get_current_admin
from services.auth_service import AuthService
from utils.email_templates import (
    get_confirmation_email_template,
    get_approval_email_template,
    get_denial_email_template,
    get_admin_alert_template,
)

router = APIRouter(prefix="/api/admin/settings", tags=["Admin Settings"])

admin_repo = AdminRepository()

# ADMIN PROFILE MANAGEMENT


class AdminProfileUpdate(BaseModel):
    """Admin profile update model"""

    full_name: Optional[str] = None
    phone: Optional[str] = None


class PasswordChange(BaseModel):
    """Password change model"""

    current_password: str
    new_password: str


@router.get("/profile")
async def get_admin_profile(current_admin: dict = Depends(get_current_admin)):
    """
    Get current admin profile
    """
    return {
        "id": str(current_admin["_id"]),
        "email": current_admin["email"],
        "full_name": current_admin["full_name"],
        "phone": current_admin.get("phone"),
        "is_active": current_admin.get("is_active", True),
        "created_at": current_admin["created_at"],
    }


@router.patch("/profile")
async def update_admin_profile(
    update_data: AdminProfileUpdate, current_admin: dict = Depends(get_current_admin)
):
    """
    Update admin profile
    """
    admin_id = str(current_admin["_id"])

    update_dict = update_data.model_dump(exclude_unset=True)
    if update_dict:
        admin_repo.update(admin_id, update_dict)

    updated_admin = admin_repo.find_by_id(admin_id)

    return {
        "id": str(updated_admin["_id"]),
        "email": updated_admin["email"],
        "full_name": updated_admin["full_name"],
        "phone": updated_admin.get("phone"),
        "message": "Profile updated successfully",
    }


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange, current_admin: dict = Depends(get_current_admin)
):
    """
    Change admin password
    """
    # Verify current password
    if not AuthService.verify_password(
        password_data.current_password, current_admin["password_hash"]
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Update password
    new_password_hash = AuthService.hash_password(password_data.new_password)
    admin_repo.update(str(current_admin["_id"]), {"password_hash": new_password_hash})

    # Log action
    audit_repo = AuditLogRepository()
    audit_repo.create(
        {
            "access_request_id": None,
            "user_id": str(current_admin["_id"]),
            "user_type": "admin",
            "action_type": "password_changed",
            "description": "Admin password changed",
            "metadata": {},
            "ip_address": None,
        }
    )

    return {"message": "Password changed successfully"}


# SYSTEM SETTINGS


class SystemSettings(BaseModel):
    """System settings model"""

    invitation_expiry_days: int
    auto_approve_enabled: bool
    email_notifications_enabled: bool
    require_admin_notes: bool
    max_pending_requests_per_email: int


@router.get("/system", response_model=SystemSettings)
async def get_system_settings(current_admin: dict = Depends(get_current_admin)):
    """
    Get system settings
    """
    from database import system_settings_collection

    settings_doc = system_settings_collection.find_one({"_id": "default"})

    if not settings_doc:
        # Return defaults
        return SystemSettings(
            invitation_expiry_days=7,
            auto_approve_enabled=False,
            email_notifications_enabled=True,
            require_admin_notes=False,
            max_pending_requests_per_email=3,
        )

    return SystemSettings(**settings_doc)


@router.put("/system")
async def update_system_settings(
    settings: SystemSettings, current_admin: dict = Depends(get_current_admin)
):
    """
    Update system settings
    """
    from database import system_settings_collection

    settings_dict = settings.model_dump()
    settings_dict["_id"] = "default"
    settings_dict["updated_at"] = datetime.utcnow()
    settings_dict["updated_by"] = str(current_admin["_id"])

    system_settings_collection.update_one(
        {"_id": "default"}, {"$set": settings_dict}, upsert=True
    )

    # Log action
    from repositories.audit_log_repository import AuditLogRepository

    audit_repo = AuditLogRepository()
    audit_repo.create(
        {
            "access_request_id": None,
            "user_id": str(current_admin["_id"]),
            "user_type": "admin",
            "action_type": "system_settings_updated",
            "description": "System settings updated",
            "metadata": settings_dict,
            "ip_address": None,
        }
    )

    return {"message": "System settings updated successfully", "settings": settings}


# EMAIL TEMPLATE MANAGEMENT


class EmailTemplate(BaseModel):
    """Email template model"""

    template_type: str  # confirmation, approval, denial, admin_alert
    subject: str
    body: str


@router.get("/email-templates/{template_type}")
async def get_email_template(
    template_type: str, current_admin: dict = Depends(get_current_admin)
):
    """
    Get email template
    """
    from database import email_templates_collection

    template = email_templates_collection.find_one({"template_type": template_type})

    if not template:
        # Return default templates

        defaults = {
            "confirmation": {
                "subject": "Access Request Received - SAYeTECH DataRoom",
                "body": get_confirmation_email_template(),
            },
            "approval": {
                "subject": "Access Approved - SAYeTECH DataRoom",
                "body": get_approval_email_template(),
            },
            "denial": {
                "subject": "Access Request Update - SAYeTECH DataRoom",
                "body": get_denial_email_template(),
            },
            "admin_alert": {
                "subject": "New DataRoom Access Request",
                "body": get_admin_alert_template(),
            },
        }

        if template_type in defaults:
            return EmailTemplate(template_type=template_type, **defaults[template_type])

    return EmailTemplate(
        template_type=template["template_type"],
        subject=template["subject"],
        body=template["body"],
    )


@router.put("/email-templates/{template_type}")
async def update_email_template(
    template_type: str,
    template: EmailTemplate,
    current_admin: dict = Depends(get_current_admin),
):
    """
    Update email template
    """
    from database import email_templates_collection

    template_dict = template.model_dump()
    template_dict["updated_at"] = datetime.utcnow()
    template_dict["updated_by"] = str(current_admin["_id"])

    email_templates_collection.update_one(
        {"template_type": template_type}, {"$set": template_dict}, upsert=True
    )

    return {"message": "Email template updated successfully", "template": template}



# ADMIN MANAGEMENT (Super Admin Only)

class AdminCreate(BaseModel):
    """Create admin model"""

    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    password: str


@router.get("/admins")
async def list_admins(current_admin: dict = Depends(get_current_admin)):
    """
    List all admins
    """
    admins = admin_repo.find_all()

    return {
        "total": len(admins),
        "admins": [
            {
                "id": str(admin["_id"]),
                "email": admin["email"],
                "full_name": admin["full_name"],
                "phone": admin.get("phone"),
                "is_active": admin.get("is_active", True),
                "created_at": admin["created_at"],
            }
            for admin in admins
        ],
    }


@router.post("/admins")
async def create_admin(
    admin_data: AdminCreate, current_admin: dict = Depends(get_current_admin)
):
    """
    Create new admin (Super Admin only)
    """
    # Check if email already exists
    existing = admin_repo.find_by_email(admin_data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Create admin
    new_admin = {
        "email": admin_data.email,
        "password_hash": AuthService.hash_password(admin_data.password),
        "full_name": admin_data.full_name,
        "phone": admin_data.phone,
    }

    admin_id = admin_repo.create(new_admin)

    # Log action
    audit_repo = AuditLogRepository()
    audit_repo.create(
        {
            "access_request_id": None,
            "user_id": str(current_admin["_id"]),
            "user_type": "admin",
            "action_type": "admin_created",
            "description": f"New admin created: {admin_data.email}",
            "metadata": {"new_admin_id": admin_id},
            "ip_address": None,
        }
    )

    return {
        "admin_id": admin_id,
        "email": admin_data.email,
        "message": "Admin created successfully",
    }


@router.delete("/admins/{admin_id}")
async def delete_admin(admin_id: str, current_admin: dict = Depends(get_current_admin)):
    """
    Deactivate admin account
    """
    # Prevent self-deletion
    if str(current_admin["_id"]) == admin_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )

    admin = admin_repo.find_by_id(admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")

    # Deactivate instead of delete
    admin_repo.update(admin_id, {"is_active": False})

    # Log action
    audit_repo = AuditLogRepository()
    audit_repo.create(
        {
            "access_request_id": None,
            "user_id": str(current_admin["_id"]),
            "user_type": "admin",
            "action_type": "admin_deactivated",
            "description": f"Admin deactivated: {admin['email']}",
            "metadata": {"deactivated_admin_id": admin_id},
            "ip_address": None,
        }
    )

    return {"admin_id": admin_id, "message": "Admin deactivated successfully"}


# SYSTEM HEALTH & MONITORING


@router.get("/system/health")
async def system_health(current_admin: dict = Depends(get_current_admin)):
    """
    Get system health status
    """
    from database import db, client

    try:
        # Check MongoDB connection
        client.admin.command("ping")
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    # Get collection stats
    from database import (
        access_requests_collection,
        investors_collection,
        admin_users_collection,  
        audit_logs_collection,
        alert_logs_collection,
    )

    stats = {
        "database_status": db_status,
        "collections": {
            "access_requests": access_requests_collection.count_documents({}),
            "investors": investors_collection.count_documents({}),
            "admins": admin_users_collection.count_documents({}),
            "audit_logs": audit_logs_collection.count_documents({}),
            "notifications": alert_logs_collection.count_documents({}),
        },
        "indexes": {
            "access_requests": len(list(access_requests_collection.list_indexes())),
            "investors": len(list(investors_collection.list_indexes())),
            "admins": len(list(admin_users_collection.list_indexes())),
        },
        "timestamp": datetime.utcnow(),
    }

    return stats


@router.post("/system/cleanup")
async def cleanup_old_data(
    days: int = 90, current_admin: dict = Depends(get_current_admin)
):
    """
    Cleanup old audit logs and notifications
    """
    from database import (
        audit_logs_collection,
        alert_logs_collection,
    )  # Changed notifications_collection to alert_logs_collection
    from datetime import timedelta

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Delete old audit logs
    audit_result = audit_logs_collection.delete_many(
        {"created_at": {"$lt": cutoff_date}}
    )

    # Delete old notifications
    notif_result = alert_logs_collection.delete_many(
        {"created_at": {"$lt": cutoff_date}, "status": "sent"}
    )

    # Log action
    audit_repo = AuditLogRepository()
    audit_repo.create(
        {
            "access_request_id": None,
            "user_id": str(current_admin["_id"]),
            "user_type": "admin",
            "action_type": "system_cleanup",
            "description": f"Cleaned up data older than {days} days",
            "metadata": {
                "audit_logs_deleted": audit_result.deleted_count,
                "notifications_deleted": notif_result.deleted_count,
            },
            "ip_address": None,
        }
    )

    return {
        "audit_logs_deleted": audit_result.deleted_count,
        "notifications_deleted": notif_result.deleted_count,
        "message": f"Successfully cleaned up data older than {days} days",
    }
