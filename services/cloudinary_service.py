# services/cloudinary_service.py
import cloudinary
import cloudinary.uploader
import cloudinary.api
from typing import Optional
import os
from fastapi import HTTPException, status
import mimetypes

class CloudinaryService:
    @staticmethod
    def upload_file(
        file_path: str,
        folder: str = "dataroom_documents",
        public_id: Optional[str] = None,
        overwrite: bool = False,
        resource_type: str = "auto"  # auto, image, raw, video
    ) -> dict:
        """
        Upload a file to Cloudinary.
        
        Args:
            file_path: Local path to the file to upload
            folder: Cloudinary folder to upload to
            public_id: Optional custom public ID for the file
            overwrite: Whether to overwrite if file exists
            resource_type: Type of resource (auto, image, raw, video)
        
        Returns:
            Cloudinary upload result dictionary
        """
        try:
            result = cloudinary.uploader.upload(
                file_path,
                folder=folder,
                public_id=public_id,
                overwrite=overwrite,
                resource_type=resource_type
            )
            return result
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Cloudinary upload failed: {str(e)}"
            )

    @staticmethod
    def delete_file(public_id: str, resource_type: str = "auto") -> dict:
        """
        Delete a file from Cloudinary.
        
        Args:
            public_id: Public ID of the file to delete
            resource_type: Type of resource (auto, image, raw, video)
        
        Returns:
            Cloudinary delete result dictionary
        """
        try:
            result = cloudinary.uploader.destroy(
                public_id,
                resource_type=resource_type
            )
            return result
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Cloudinary delete failed: {str(e)}"
            )

    @staticmethod
    def get_file_url(public_id: str, resource_type: str = "auto", transformation: Optional[dict] = None) -> str:
        """
        Generate a URL for a Cloudinary file.
        
        Args:
            public_id: Public ID of the file
            resource_type: Type of resource (auto, image, raw, video)
            transformation: Optional transformation parameters
        
        Returns:
            Public URL of the file
        """
        try:
            url = cloudinary.utils.cloudinary_url(
                public_id,
                resource_type=resource_type,
                transformation=transformation
            )[0]
            return url
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Cloudinary URL generation failed: {str(e)}"
            )

    @staticmethod
    def get_download_url(public_id: str, filename: str, resource_type: str = "auto") -> str:
        """
        Generate a download URL for a Cloudinary file with attachment flag.

        Args:
            public_id: Public ID of the file
            filename: Desired download filename
            resource_type: Type of resource (auto, image, raw, video)

        Returns:
            Download URL with attachment flag
        """
        try:
            import urllib.parse

            # Get base URL
            base_url = cloudinary.utils.cloudinary_url(
                public_id,
                resource_type=resource_type
            )[0]

            # Prepare filename for attachment flag
            safe_filename = filename.replace(' ', '_')
            encoded_filename = urllib.parse.quote(safe_filename, safe='.-_')

            # Add attachment flag to URL
            # Cloudinary format: /upload/fl_attachment:filename/v123456/path
            if "/raw/upload/" in base_url:
                download_url = base_url.replace("/raw/upload/", f"/raw/upload/fl_attachment:{encoded_filename}/")
            elif "/image/upload/" in base_url:
                download_url = base_url.replace("/image/upload/", f"/image/upload/fl_attachment:{encoded_filename}/")
            elif "/upload/" in base_url:
                download_url = base_url.replace("/upload/", f"/upload/fl_attachment:{encoded_filename}/")
            else:
                download_url = base_url

            return download_url
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Cloudinary download URL generation failed: {str(e)}"
            )

    @staticmethod
    def get_file_info(public_id: str, resource_type: str = "auto") -> dict:
        """
        Get detailed information about a Cloudinary file.
        
        Args:
            public_id: Public ID of the file
            resource_type: Type of resource (auto, image, raw, video)
        
        Returns:
            Cloudinary resource info dictionary
        """
        try:
            info = cloudinary.api.resource(
                public_id,
                resource_type=resource_type
            )
            return info
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Cloudinary info retrieval failed: {str(e)}"
            )

    @staticmethod
    def upload_file_from_bytes(
        file_bytes: bytes,
        filename: str,
        folder: str = "dataroom_documents",
        public_id: Optional[str] = None,
        overwrite: bool = False,
        resource_type: str = "auto"
    ) -> dict:
        """
        Upload a file directly from bytes to Cloudinary.
        
        Args:
            file_bytes: File content as bytes
            filename: Original filename (used to determine resource type)
            folder: Cloudinary folder to upload to
            public_id: Optional custom public ID for the file
            overwrite: Whether to overwrite if file exists
            resource_type: Type of resource (auto, image, raw, video)
        
        Returns:
            Cloudinary upload result dictionary
        """
        try:
            # Determine resource type based on file extension
            if resource_type == "auto":
                mime_type, _ = mimetypes.guess_type(filename)
                if mime_type and mime_type.startswith('image'):
                    resource_type = 'image'
                elif mime_type and mime_type.startswith('video'):
                    resource_type = 'video'
                else:
                    resource_type = 'raw'

            result = cloudinary.uploader.upload(
                file_bytes,
                folder=folder,
                public_id=public_id,
                overwrite=overwrite,
                resource_type=resource_type
            )
            return result
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Cloudinary upload from bytes failed: {str(e)}"
            )