from database import admin_users_collection
from bson import ObjectId
from datetime import datetime
from typing import Optional, List

class AdminRepository:
    def find_by_id(self, admin_id: str) -> Optional[dict]:
        """Find admin by ObjectId string."""
        try:
            admin = admin_users_collection.find_one({"_id": ObjectId(admin_id)})
            return admin
        except:
            return None

    def find_by_email(self, email: str) -> Optional[dict]:
        """Find admin by email."""
        return admin_users_collection.find_one({"email": email})

    def find_all(self) -> List[dict]:
        """Find all active admins."""
        return list(admin_users_collection.find({}))

    def create(self, admin_data: dict) -> str:
        """Create a new admin and return its ID."""
        admin_data["created_at"] = datetime.utcnow()
        admin_data["is_active"] = True
        result = admin_users_collection.insert_one(admin_data)
        return str(result.inserted_id)

    def update(self, admin_id: str, update_data: dict):
        """Update admin fields."""
        admin_users_collection.update_one(
            {"_id": ObjectId(admin_id)},
            {"$set": update_data}
        )