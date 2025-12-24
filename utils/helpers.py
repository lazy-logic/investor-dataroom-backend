from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from bson import ObjectId
import re
import secrets
from database import access_tokens_collection

class Helpers:
    @staticmethod
    def is_valid_email(email: str) -> bool:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def is_valid_phone(phone: str) -> bool:
        """Validate phone number format."""
        pattern = r'^\+?1?\d{9,15}$'
        return re.match(pattern, phone.replace(" ", "").replace("-", "")) is not None
    
    @staticmethod
    def sanitize_string(text: str, max_length: int = 500) -> str:
        """Sanitize user input string."""
        if not text:
            return ""
        # Remove any potentially harmful characters
        sanitized = re.sub(r'[<>\"\';&]', '', text)
        return sanitized[:max_length].strip()
    
    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def is_token_valid(token: str) -> bool:
        """Check if access token is valid and not expired."""
        token_doc = access_tokens_collection.find_one({"token": token})
        
        if not token_doc:
            return False
        
        if not token_doc.get("is_active", False):
            return False
        
        expires_at = token_doc.get("expires_at")
        if expires_at and datetime.utcnow() > expires_at:
            # Mark token as inactive
            access_tokens_collection.update_one(
                {"token": token},
                {"$set": {"is_active": False}}
            )
            return False
        
        # Update last accessed time
        access_tokens_collection.update_one(
            {"token": token},
            {"$set": {"last_accessed": datetime.utcnow()}}
        )
        
        return True
    
    @staticmethod
    def serialize_mongo_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert MongoDB document to JSON-serializable dict."""
        if not doc:
            return {}
        
        doc_copy = doc.copy()
        if "_id" in doc_copy:
            doc_copy["id"] = str(doc_copy.pop("_id"))
        
        # Convert datetime objects to ISO format strings
        for key, value in doc_copy.items():
            if isinstance(value, datetime):
                doc_copy[key] = value.isoformat()
            elif isinstance(value, ObjectId):
                doc_copy[key] = str(value)
        
        return doc_copy
    
    @staticmethod
    def calculate_expiry_date(days: int = 30) -> datetime:
        """Calculate expiry date from now."""
        return datetime.utcnow() + timedelta(days=days)
    
    @staticmethod
    def format_datetime(dt: Optional[datetime], format: str = "%Y-%m-%d %H:%M:%S") -> str:
        """Format datetime object to string."""
        if not dt:
            return "N/A"
        return dt.strftime(format)
    
    @staticmethod
    def parse_datetime(date_str: str) -> Optional[datetime]:
        """Parse datetime string to datetime object."""
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            return None
    
    @staticmethod
    def get_status_color(status: str) -> str:
        """Get color code for status (for UI)."""
        status_colors = {
            "pending": "#FFA500",    # Orange
            "approved": "#00FF00",   # Green
            "denied": "#FF0000",     # Red
            "expired": "#808080",    # Gray
            "revoked": "#8B0000"     # Dark Red
        }
        return status_colors.get(status.lower(), "#000000")
    
    @staticmethod
    def mask_email(email: str) -> str:
        """Mask email for privacy (e.g., j***n@example.com)."""
        if not email or "@" not in email:
            return email
        
        local, domain = email.split("@")
        if len(local) <= 2:
            masked_local = local[0] + "*"
        else:
            masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
        
        return f"{masked_local}@{domain}"
    
    @staticmethod
    def validate_access_request_data(data: dict) -> tuple[bool, Optional[str]]:
        """Validate access request data."""
        required_fields = ["email", "full_name", "company"]
        
        for field in required_fields:
            if not data.get(field):
                return False, f"Missing required field: {field}"
        
        if not Helpers.is_valid_email(data["email"]):
            return False, "Invalid email format"
        
        if data.get("phone") and not Helpers.is_valid_phone(data["phone"]):
            return False, "Invalid phone number format"
        
        return True, None
    
    @staticmethod
    def get_request_stats(requests: list) -> dict:
        """Calculate statistics from access requests."""
        total = len(requests)
        if total == 0:
            return {
                "total": 0,
                "pending": 0,
                "approved": 0,
                "denied": 0,
                "approval_rate": 0
            }
        
        pending = sum(1 for r in requests if r.get("status") == "pending")
        approved = sum(1 for r in requests if r.get("status") == "approved")
        denied = sum(1 for r in requests if r.get("status") == "denied")
        
        processed = approved + denied
        approval_rate = (approved / processed * 100) if processed > 0 else 0
        
        return {
            "total": total,
            "pending": pending,
            "approved": approved,
            "denied": denied,
            "approval_rate": round(approval_rate, 2)
        }
    
    @staticmethod
    def create_notification_message(action: str, data: dict) -> str:
        """Create notification message for different actions."""
        messages = {
            "new_request": f"New access request from {data.get('full_name')} ({data.get('company')})",
            "approved": f"Access approved for {data.get('email')}",
            "denied": f"Access denied for {data.get('email')}",
            "expired": f"Access expired for {data.get('email')}",
            "revoked": f"Access revoked for {data.get('email')}"
        }
        return messages.get(action, f"Action performed: {action}")
    
    @staticmethod
    def log_activity(collection, action: str, details: dict):
        """Generic activity logger."""
        log_entry = {
            "action": action,
            "details": details,
            "timestamp": datetime.utcnow()
        }
        collection.insert_one(log_entry)
        return log_entry