import uuid
import os
import mimetypes
from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from fastapi import HTTPException, status

from services.cloudinary_service import CloudinaryService
from utils.cloudinary_config import initialize_cloudinary
from database import documents_collection, document_access_logs_collection

# Initialize Cloudinary once
initialize_cloudinary()


class DocumentService:
    @staticmethod
    async def upload_document(
        file,
        categories: List[str],
        user_id: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        title: Optional[str] = None,
    ):
        # Ensure tags is a list
        if tags is None:
            tags = []

        filename = file.filename
        title = title or filename
        
        # Extract file extension and MIME type
        file_extension = os.path.splitext(filename)[1].lower() if filename else ""
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = "application/octet-stream"

        # Read file bytes
        file_bytes = await file.read()

        # Generate unique public ID - preserve the file extension
        name_part, ext_part = os.path.splitext(filename)
        # Only sanitize the name part, keep the extension intact
        safe_name = name_part.replace(" ", "_").replace(".", "_")
        safe_filename = f"{safe_name}{ext_part}"  # e.g., "My_Document.pdf"
        public_id = f"dataroom_documents/{user_id}/{uuid.uuid4()}_{safe_name}"

        # Upload to Cloudinary
        upload_result = CloudinaryService.upload_file_from_bytes(
            file_bytes=file_bytes,
            filename=filename,
            public_id=public_id,
            folder="dataroom_documents",
        )

        # Prepare document data for MongoDB
        document_data = {
            "title": title,
            "description": description or "",
            "categories": categories,
            "file_path": upload_result["secure_url"],
            "file_url": upload_result["secure_url"],  
            "file_type": file_extension,  # Store actual file extension
            "file_extension": file_extension,
            "mime_type": mime_type,
            "original_filename": filename,
            "file_size": upload_result["bytes"],
            "uploaded_at": datetime.utcnow(),
            "uploaded_by": user_id,
            "tags": tags,
            "view_count": 0,
            "download_count": 0,
            "cloudinary_public_id": upload_result["public_id"],
            "cloudinary_resource_type": upload_result.get("resource_type", "raw"),
        }

        # Insert into MongoDB
        result = documents_collection.insert_one(document_data)
        document_data["id"] = str(result.inserted_id)
        return document_data

    @staticmethod
    def list_documents(
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        search: Optional[str] = None,
    ):
        """List documents with optional filters"""
        query = {}
        
        if categories:
            query["categories"] = {"$in": categories}
        
        if tags:
            query["tags"] = {"$in": tags}
        
        if search:
            query["$or"] = [
                {"title": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}},
            ]
        
        documents = list(documents_collection.find(query))
        
        # Convert ObjectId to string and ensure file_url exists
        for doc in documents:
            doc["id"] = str(doc["_id"])
            if "file_url" not in doc and "file_path" in doc:
                doc["file_url"] = doc["file_path"]
        
        return documents

    @staticmethod
    def get_document_by_id(document_id: str):
        """Get a single document by ID"""
        try:
            document = documents_collection.find_one({"_id": ObjectId(document_id)})
            if not document:
                return None
            
            document["id"] = str(document["_id"])
            if "file_url" not in document and "file_path" in document:
                document["file_url"] = document["file_path"]
            
            return document
        except Exception:
            return None

    @staticmethod
    def get_document_url(document_id: str):
        document = documents_collection.find_one({"_id": ObjectId(document_id)})
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return document.get("file_url") or document.get("file_path")

    @staticmethod
    def delete_document(document_id: str):
        document = documents_collection.find_one({"_id": ObjectId(document_id)})
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        CloudinaryService.delete_file(
            public_id=document["cloudinary_public_id"],
            resource_type=document["cloudinary_resource_type"],
        )

        documents_collection.delete_one({"_id": ObjectId(document_id)})
        return {"message": "Document deleted successfully"}

    @staticmethod
    def get_category_stats():
        """Get document count by category"""
        pipeline = [
            {"$unwind": "$categories"},
            {"$group": {"_id": "$categories", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        
        results = list(documents_collection.aggregate(pipeline))
        
        stats = {
            "total_documents": documents_collection.count_documents({}),
            "by_category": [
                {"category": r["_id"], "count": r["count"]} for r in results
            ],
        }
        
        return stats

    @staticmethod
    def log_document_access(
        document_id: str,
        user_id: str,
        action: str,
        ip_address: str = None,
        user_agent: str = None
    ):
        """Log document access (view/download) for analytics"""
        from database import investors_collection
        
        # Try to get user email for display
        user_email = None
        try:
            user = investors_collection.find_one({"_id": ObjectId(user_id)})
            if user:
                user_email = user.get("email", user.get("full_name", user_id))
        except:
            user_email = user_id
        
        log_entry = {
            "document_id": document_id,
            "user_id": user_id,
            "user_email": user_email,
            "action": action,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "accessed_at": datetime.utcnow(),
        }
        
        document_access_logs_collection.insert_one(log_entry)
        
        # Also increment the view/download count on the document
        if action == "view":
            documents_collection.update_one(
                {"_id": ObjectId(document_id)},
                {"$inc": {"view_count": 1}}
            )
        elif action == "download":
            documents_collection.update_one(
                {"_id": ObjectId(document_id)},
                {"$inc": {"download_count": 1}}
            )