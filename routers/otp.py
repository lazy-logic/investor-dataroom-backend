from fastapi import APIRouter, HTTPException, BackgroundTasks
from database import access_requests_collection, users_collection, investors_collection
from services.email_service import EmailService
from services.auth_service import AuthService
from datetime import datetime, timedelta
import random
import string
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/otp", tags=["OTP"])

class OTPRequest(BaseModel):
    email: EmailStr
    purpose: str = "access_request"

class OTPVerify(BaseModel):
    email: EmailStr
    otp_code: str
    purpose: str = "access_request"

def generate_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))

@router.post("/request")
async def request_otp(request: OTPRequest, background_tasks: BackgroundTasks):
    """Request OTP for email verification or login"""
    try:
        email = request.email
        purpose = request.purpose
        
        print(f"OTP requested for {email} - Purpose: {purpose}")
        
        if purpose == "access_request":
            access_request = access_requests_collection.find_one({"email": email})
            
            if not access_request:
                raise HTTPException(
                    status_code=404, 
                    detail="No access request found. Please submit an access request first."
                )
            
            if access_request.get("email_verified"):
                return {
                    "success": True,
                    "message": "Email already verified",
                    "already_verified": True
                }
            
            otp = generate_otp()
            otp_expiry = datetime.utcnow() + timedelta(minutes=10)
            
            access_requests_collection.update_one(
                {"_id": access_request["_id"]},
                {
                    "$set": {
                        "otp": otp,
                        "otp_expiry": otp_expiry,
                        "otp_attempts": 0,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            target_name = access_request.get("full_name", "there")
            
        elif purpose == "login":
            # First check investors_collection (where approved access requests create records)
            user = investors_collection.find_one({"email": email, "is_active": True})
            
            # If not found in investors, check users_collection as fallback
            if not user:
                user = users_collection.find_one({"email": email})
            
            # If still not found, check if there's an approved access request
            if not user:
                approved_request = access_requests_collection.find_one({
                    "email": email,
                    "status": "approved"
                })
                if approved_request:
                    # Create investor record from approved access request
                    user = {
                        "email": email,
                        "full_name": approved_request.get("full_name", ""),
                        "company": approved_request.get("company", ""),
                        "_id": approved_request["_id"]
                    }
                    # Also insert into investors collection for future logins
                    investors_collection.update_one(
                        {"email": email},
                        {
                            "$set": {
                                "email": email,
                                "full_name": approved_request.get("full_name", ""),
                                "company": approved_request.get("company", ""),
                                "phone": approved_request.get("phone", ""),
                                "is_active": True,
                                "access_request_id": str(approved_request["_id"]),
                                "created_at": datetime.utcnow(),
                                "updated_at": datetime.utcnow()
                            }
                        },
                        upsert=True
                    )
                    # Refresh user from investors collection to get the proper _id
                    user = investors_collection.find_one({"email": email})
            
            if not user:
                raise HTTPException(
                    status_code=404, 
                    detail="No approved account found. Please request access first."
                )
            
            otp = generate_otp()
            otp_expiry = datetime.utcnow() + timedelta(minutes=10)
            
            # Update OTP in investors collection
            investors_collection.update_one(
                {"email": email},
                {
                    "$set": {
                        "otp": otp,
                        "otp_expiry": otp_expiry,
                        "otp_attempts": 0,
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            target_name = user.get("full_name", user.get("email", "there"))
            
        else:
            raise HTTPException(status_code=400, detail="Invalid purpose")
        
        # Send OTP email
        subject = "Your Verification Code - SAYeTECH Dataroom"
        body = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #4CAF50; margin-top: 0;">Email Verification</h2>
                <p>Hello {target_name},</p>
                <p>Your verification code for SAYeTECH Investor Dataroom is:</p>
                
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 25px; text-align: center; border-radius: 10px; margin: 30px 0;">
                    <div style="background: white; display: inline-block; padding: 15px 40px; border-radius: 8px;">
                        <h1 style="color: #4CAF50; font-size: 42px; letter-spacing: 10px; font-family: 'Courier New', monospace; margin: 0;">{otp}</h1>
                    </div>
                </div>
                
                <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; border-radius: 4px;">
                    <p style="margin: 0;"><strong>Important:</strong></p>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>This code expires in <strong>10 minutes</strong></li>
                        <li>Do not share this code with anyone</li>
                        <li>If you didn't request this, please ignore this email</li>
                    </ul>
                </div>
                
                <p style="color: #666; font-size: 14px; margin-top: 30px;">
                    Need help? Contact us at <a href="mailto:dataroom@sayetech.io" style="color: #4CAF50;">dataroom@sayetech.io</a>
                </p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                
                <p style="color: #999; font-size: 12px; text-align: center; margin: 0;">
                    2025 SAYeTECH. All rights reserved.
                </p>
            </div>
        </body>
        </html>
        """
        
        email_sent = EmailService.send_email(email, subject, body)
        
        if not email_sent:
            raise HTTPException(status_code=500, detail="Failed to send OTP email")
        
        print(f"OTP sent to {email}")
        
        return {
            "success": True,
            "message": f"OTP sent successfully to {email}",
            "expires_in_minutes": 10,
            "purpose": purpose
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in request_otp: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify")
async def verify_otp(request: OTPVerify):
    """Verify OTP code"""
    try:
        email = request.email
        otp_code = request.otp_code.strip()
        purpose = request.purpose
        
        print(f"Verifying OTP for {email} - Purpose: {purpose}")
        
        if purpose == "access_request":
            access_request = access_requests_collection.find_one({"email": email})
            
            if not access_request:
                raise HTTPException(status_code=404, detail="Access request not found")
            
            if access_request.get("email_verified"):
                return {
                    "success": True,
                    "message": "Email already verified",
                    "already_verified": True
                }
            
            if "otp" not in access_request:
                raise HTTPException(status_code=400, detail="No OTP found. Please request a new one.")
            
            if datetime.utcnow() > access_request.get("otp_expiry", datetime.utcnow()):
                raise HTTPException(status_code=400, detail="OTP expired. Please request a new one.")
            
            max_attempts = 3
            attempts = access_request.get("otp_attempts", 0)
            
            if attempts >= max_attempts:
                access_requests_collection.update_one(
                    {"_id": access_request["_id"]},
                    {"$unset": {"otp": "", "otp_expiry": ""}}
                )
                raise HTTPException(status_code=400, detail="Too many attempts. Please request a new OTP.")
            
            if access_request["otp"] != otp_code:
                access_requests_collection.update_one(
                    {"_id": access_request["_id"]},
                    {"$inc": {"otp_attempts": 1}}
                )
                remaining = max_attempts - attempts - 1
                raise HTTPException(status_code=400, detail=f"Invalid OTP. {remaining} attempts remaining.")
            
            access_requests_collection.update_one(
                {"_id": access_request["_id"]},
                {
                    "$set": {
                        "email_verified": True,
                        "verified_at": datetime.utcnow()
                    },
                    "$unset": {"otp": "", "otp_expiry": "", "otp_attempts": ""}
                }
            )
            
            user_name = access_request.get("full_name", "")
            
            print(f"Email verified for {email}")
            
            return {
                "success": True,
                "message": f"Welcome {user_name}! Your email has been verified.",
                "access_request_id": str(access_request["_id"])
            }
            
        elif purpose == "login":
            # Check investors_collection (where login OTPs are now stored)
            user = investors_collection.find_one({"email": email})
            
            # Fallback to users_collection if not found
            if not user:
                user = users_collection.find_one({"email": email})
                collection_to_update = users_collection
            else:
                collection_to_update = investors_collection
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            if "otp" not in user:
                raise HTTPException(status_code=400, detail="No OTP found. Please request a new one.")
            
            if datetime.utcnow() > user.get("otp_expiry", datetime.utcnow()):
                raise HTTPException(status_code=400, detail="OTP expired. Please request a new one.")
            
            max_attempts = 3
            attempts = user.get("otp_attempts", 0)
            
            if attempts >= max_attempts:
                collection_to_update.update_one(
                    {"_id": user["_id"]},
                    {"$unset": {"otp": "", "otp_expiry": ""}}
                )
                raise HTTPException(status_code=400, detail="Too many attempts. Please request a new OTP.")
            
            if user["otp"] != otp_code:
                collection_to_update.update_one(
                    {"_id": user["_id"]},
                    {"$inc": {"otp_attempts": 1}}
                )
                remaining = max_attempts - attempts - 1
                raise HTTPException(status_code=400, detail=f"Invalid OTP. {remaining} attempts remaining.")
            
            collection_to_update.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {"last_login": datetime.utcnow()},
                    "$unset": {"otp": "", "otp_expiry": "", "otp_attempts": ""}
                }
            )
            
            print(f"User logged in: {email}")
            
            # Create JWT access token for investor
            token_data = {
                "sub": str(user["_id"]),
                "email": user["email"],
                "full_name": user.get("full_name", ""),
                "role": "investor",
                "is_investor": True
            }
            access_token = AuthService.create_access_token(token_data)
            
            return {
                "success": True,
                "message": "Login successful",
                "access_token": access_token,
                "token_type": "bearer",
                "user_id": str(user["_id"]),
                "user_email": user["email"],
                "user": {
                    "id": str(user["_id"]),
                    "email": user["email"],
                    "full_name": user.get("full_name", ""),
                    "company": user.get("company", ""),
                    "phone": user.get("phone", ""),
                    "role": "investor",
                    "is_active": user.get("is_active", True)
                }
            }
        
        else:
            raise HTTPException(status_code=400, detail="Invalid purpose")
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in verify_otp: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resend")
async def resend_otp(request: OTPRequest, background_tasks: BackgroundTasks):
    """Resend OTP"""
    return await request_otp(request, background_tasks)


# Investor Authentication Endpoints

from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bson import ObjectId

security = HTTPBearer()


def get_current_investor(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current authenticated investor from token"""
    token = credentials.credentials
    payload = AuthService.verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
    
    # Check if this is an investor token
    if not payload.get("is_investor"):
        raise HTTPException(
            status_code=403,
            detail="Not an investor token"
        )
    
    # Get investor from database
    investor = investors_collection.find_one({"_id": ObjectId(payload["sub"])})
    
    if not investor:
        raise HTTPException(
            status_code=404,
            detail="Investor not found"
        )
    
    if not investor.get("is_active", True):
        raise HTTPException(
            status_code=403,
            detail="Account is inactive"
        )
    
    return investor


@router.get("/me")
async def get_current_investor_info(investor: dict = Depends(get_current_investor)):
    """Get current authenticated investor information"""
    return {
        "id": str(investor["_id"]),
        "email": investor.get("email", ""),
        "full_name": investor.get("full_name", ""),
        "company": investor.get("company", ""),
        "phone": investor.get("phone", ""),
        "role": "investor",
        "is_active": investor.get("is_active", True),
        "is_super_admin": False,
        "created_at": investor.get("created_at", datetime.utcnow()).isoformat(),
        "updated_at": investor.get("updated_at", datetime.utcnow()).isoformat()
    }


@router.post("/logout")
async def logout():
    """Logout investor (client should clear token)"""
    return {"success": True, "message": "Logged out successfully"}