from datetime import datetime
from database import audit_logs_collection, db 

class AuditLogRepository:
    def create(self, log_data: dict):
        """Create a new audit log entry."""
        log_data["created_at"] = datetime.utcnow()
        audit_logs_collection.insert_one(log_data)