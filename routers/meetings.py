from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from models.meeting import MeetingCreate, MeetingResponse
from services.email_service import EmailService
from database import meetings_collection, investors_collection, admin_users_collection, access_requests_collection
from routers.admin_auth import get_current_user_or_admin, get_current_admin
from bson import ObjectId
import secrets

router = APIRouter(prefix="/api/meetings", tags=["Meetings"])


def get_utc_now():
    """Get current UTC time with timezone awareness"""
    return datetime.now(timezone.utc)


def make_timezone_aware(dt: datetime) -> datetime:
    """Convert naive datetime to timezone-aware UTC"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def generate_meeting_link() -> str:
    """
    Generate a meeting link.
    
    Priority:
    1. Use Brevo booking page URL if configured (BREVO_BOOKING_URL env var)
    2. Fall back to Jitsi Meet for instant video conferencing
    
    Jitsi is free, open-source, and requires no API keys.
    Brevo provides a booking page where investors can schedule meetings.
    """
    import os
    
    # Check for Brevo booking URL
    brevo_url = os.environ.get("BREVO_BOOKING_URL")
    if brevo_url:
        return brevo_url
    
    # Fall back to Jitsi Meet - generate unique room
    room_id = secrets.token_urlsafe(12)
    room_name = f"SAYeTECH-{room_id}"
    return f"https://meet.jit.si/{room_name}"


@router.post("/", response_model=dict)
async def schedule_meeting(
    meeting: MeetingCreate,
    investor_id: str,
    current_user: dict = Depends(get_current_user_or_admin)
):
    """
    Schedule a new meeting
    Can be created by admin or investor themselves
    """
    try:
        # Verify investor exists - search by multiple methods
        investor = None
        
        # Try by investor_id field first (e.g., "INV-20250112-A7B3C9")
        investor = investors_collection.find_one({"investor_id": investor_id})
        
        # Try by MongoDB _id
        if not investor:
            try:
                investor = investors_collection.find_one({"_id": ObjectId(investor_id)})
            except:
                pass
        
        # Try in access_requests collection (approved requests)
        if not investor:
            try:
                investor = access_requests_collection.find_one({
                    "_id": ObjectId(investor_id),
                    "status": "approved"
                })
            except:
                pass
        
        # Fallback to admin users
        if not investor:
            try:
                investor = admin_users_collection.find_one({"_id": ObjectId(investor_id)})
            except:
                pass
        
        if not investor:
            raise HTTPException(
                status_code=404,
                detail="Investor not found"
            )
        
        # Make scheduled_at timezone-aware
        scheduled_at = make_timezone_aware(meeting.scheduled_at)
        
        # Check if scheduled time is in the past
        if scheduled_at < get_utc_now():
            raise HTTPException(
                status_code=400,
                detail="Cannot schedule meetings in the past"
            )
        
        # Check if time slot is available
        existing_meeting = meetings_collection.find_one({
            "scheduled_at": scheduled_at,
            "status": {"$ne": "cancelled"}
        })
        
        if existing_meeting:
            raise HTTPException(
                status_code=400,
                detail="This time slot is already booked"
            )
        
        # Generate meeting link
        meeting_link = generate_meeting_link()
        
        # Create meeting data
        meeting_data = {
            "investor_id": investor_id,
            "investor_name": investor.get("full_name", "Unknown"),
            "investor_email": investor.get("email", ""),
            "scheduled_at": scheduled_at,
            "duration_minutes": meeting.duration_minutes,
            "meeting_link": meeting_link,
            "status": "scheduled",
            "notes": meeting.notes,
            "created_at": get_utc_now(),
            "created_by": str(current_user.get("_id", current_user.get("id"))),
            "updated_at": get_utc_now()
        }
        
        # Insert into database
        result = meetings_collection.insert_one(meeting_data)
        
        # Send confirmation emails
        try:
            EmailService.send_meeting_confirmation_to_investor(
                investor.get("email"),
                investor.get("full_name", "Investor"),
                scheduled_at,
                meeting.duration_minutes,
                meeting_link
            )
            
            EmailService.send_meeting_notification_to_admin(
                investor.get("full_name", "Unknown"),
                investor.get("email", ""),
                scheduled_at,
                meeting.duration_minutes
            )
        except Exception as e:
            print(f"Failed to send meeting emails: {e}")
        
        return {
            "success": True,
            "message": "Meeting scheduled successfully",
            "meeting_id": str(result.inserted_id),
            "meeting_link": meeting_link,
            "scheduled_at": scheduled_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error scheduling meeting: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to schedule meeting: {str(e)}"
        )


@router.get("/", response_model=List[dict])
async def list_meetings(
    status_filter: Optional[str] = None,
    investor_id: Optional[str] = None,
    current_user: dict = Depends(get_current_admin)
):
    """
    List all meetings (Admin only)
    Optional filters: status, investor_id
    """
    try:
        query = {}
        
        if status_filter:
            query["status"] = status_filter
        
        if investor_id:
            query["investor_id"] = investor_id
        
        meetings = list(meetings_collection.find(query).sort("scheduled_at", -1))
        
        # Convert ObjectId to string
        for meeting in meetings:
            meeting["id"] = str(meeting.pop("_id"))
            # Convert datetime to ISO string
            if "scheduled_at" in meeting and isinstance(meeting["scheduled_at"], datetime):
                meeting["scheduled_at"] = meeting["scheduled_at"].isoformat()
            if "created_at" in meeting and isinstance(meeting["created_at"], datetime):
                meeting["created_at"] = meeting["created_at"].isoformat()
        
        return meetings
        
    except Exception as e:
        print(f"Error listing meetings: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve meetings"
        )


@router.get("/my-meetings", response_model=List[dict])
async def get_my_meetings(
    current_user: dict = Depends(get_current_user_or_admin)
):
    """Get meetings for the current logged-in user"""
    try:
        user_id = str(current_user.get("_id", current_user.get("id")))
        
        meetings = list(meetings_collection.find({
            "investor_id": user_id
        }).sort("scheduled_at", -1))
        
        for meeting in meetings:
            meeting["id"] = str(meeting.pop("_id"))
            if "scheduled_at" in meeting and isinstance(meeting["scheduled_at"], datetime):
                meeting["scheduled_at"] = meeting["scheduled_at"].isoformat()
        
        return meetings
        
    except Exception as e:
        print(f"Error getting user meetings: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve your meetings"
        )


@router.get("/upcoming", response_model=List[dict])
async def get_upcoming_meetings(
    current_user: dict = Depends(get_current_admin)
):
    """Get all upcoming meetings (Admin only)"""
    try:
        now = get_utc_now()
        
        meetings = list(meetings_collection.find({
            "scheduled_at": {"$gte": now},
            "status": "scheduled"
        }).sort("scheduled_at", 1))
        
        for meeting in meetings:
            meeting["id"] = str(meeting.pop("_id"))
            if "scheduled_at" in meeting and isinstance(meeting["scheduled_at"], datetime):
                meeting["scheduled_at"] = meeting["scheduled_at"].isoformat()
        
        return meetings
        
    except Exception as e:
        print(f"Error getting upcoming meetings: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve upcoming meetings"
        )


@router.get("/available-slots")
async def get_available_slots(
    date: str,
    current_user: dict = Depends(get_current_user_or_admin)
):
    """
    Get available time slots for a specific date
    Date format: YYYY-MM-DD
    """
    try:
        # Parse date
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
        
        # Check if date is in the past
        if target_date.date() < get_utc_now().date():
            raise HTTPException(
                status_code=400,
                detail="Cannot check availability for past dates"
            )
        
        # Business hours: 9 AM - 5 PM
        start_hour = 9
        end_hour = 17
        slot_duration = 30  # minutes
        
        available_slots = []
        
        # Generate all possible slots
        current_slot = target_date.replace(hour=start_hour, minute=0, second=0)
        end_time = target_date.replace(hour=end_hour, minute=0, second=0)
        
        while current_slot < end_time:
            # Check if slot is available
            existing = meetings_collection.find_one({
                "scheduled_at": current_slot,
                "status": {"$ne": "cancelled"}
            })
            
            if not existing:
                available_slots.append({
                    "datetime": current_slot.isoformat(),
                    "time": current_slot.strftime("%I:%M %p"),
                    "available": True
                })
            
            # Move to next slot
            current_slot += timedelta(minutes=slot_duration)
        
        return {
            "date": date,
            "available_slots": available_slots,
            "total_available": len(available_slots)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting available slots: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get available slots"
        )


@router.get("/{meeting_id}", response_model=dict)
async def get_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user_or_admin)
):
    """Get specific meeting details"""
    try:
        meeting = meetings_collection.find_one({"_id": ObjectId(meeting_id)})
        
        if not meeting:
            raise HTTPException(
                status_code=404,
                detail="Meeting not found"
            )
        
        # Check if user has access to this meeting
        user_id = str(current_user.get("_id", current_user.get("id")))
        user_role = current_user.get("role", "user")
        
        # Allow access if user is admin or the meeting is theirs
        if user_role not in ["admin", "super_admin"] and meeting["investor_id"] != user_id:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to view this meeting"
            )
        
        meeting["id"] = str(meeting.pop("_id"))
        
        # Convert datetimes to ISO strings
        if "scheduled_at" in meeting and isinstance(meeting["scheduled_at"], datetime):
            meeting["scheduled_at"] = meeting["scheduled_at"].isoformat()
        if "created_at" in meeting and isinstance(meeting["created_at"], datetime):
            meeting["created_at"] = meeting["created_at"].isoformat()
        
        return meeting
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting meeting: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve meeting"
        )


@router.put("/{meeting_id}/reschedule")
async def reschedule_meeting(
    meeting_id: str,
    new_scheduled_at: datetime,
    current_user: dict = Depends(get_current_user_or_admin)
):
    """Reschedule a meeting"""
    try:
        meeting = meetings_collection.find_one({"_id": ObjectId(meeting_id)})
        
        if not meeting:
            raise HTTPException(
                status_code=404,
                detail="Meeting not found"
            )
        
        # Make new time timezone-aware
        new_scheduled_at = make_timezone_aware(new_scheduled_at)
        
        # Check if new time is in the past
        if new_scheduled_at < get_utc_now():
            raise HTTPException(
                status_code=400,
                detail="Cannot reschedule to a past time"
            )
        
        # Check if new time slot is available
        existing = meetings_collection.find_one({
            "scheduled_at": new_scheduled_at,
            "status": {"$ne": "cancelled"},
            "_id": {"$ne": ObjectId(meeting_id)}
        })
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail="This time slot is already booked"
            )
        
        old_time = make_timezone_aware(meeting["scheduled_at"])
        
        # Update meeting
        meetings_collection.update_one(
            {"_id": ObjectId(meeting_id)},
            {
                "$set": {
                    "scheduled_at": new_scheduled_at,
                    "updated_at": get_utc_now()
                }
            }
        )
        
        # Send notification emails
        try:
            EmailService.send_meeting_rescheduled_email(
                meeting["investor_email"],
                meeting["investor_name"],
                old_time,
                new_scheduled_at,
                meeting["meeting_link"]
            )
        except Exception as e:
            print(f"Failed to send reschedule email: {e}")
        
        return {
            "success": True,
            "message": "Meeting rescheduled successfully",
            "new_time": new_scheduled_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error rescheduling meeting: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to reschedule meeting"
        )


@router.put("/{meeting_id}/cancel")
async def cancel_meeting(
    meeting_id: str,
    reason: Optional[str] = None,
    current_user: dict = Depends(get_current_user_or_admin)
):
    """Cancel a meeting"""
    try:
        meeting = meetings_collection.find_one({"_id": ObjectId(meeting_id)})
        
        if not meeting:
            raise HTTPException(
                status_code=404,
                detail="Meeting not found"
            )
        
        if meeting["status"] == "cancelled":
            raise HTTPException(
                status_code=400,
                detail="Meeting is already cancelled"
            )
        
        # Update meeting status
        meetings_collection.update_one(
            {"_id": ObjectId(meeting_id)},
            {
                "$set": {
                    "status": "cancelled",
                    "cancelled_at": get_utc_now(),
                    "cancellation_reason": reason,
                    "updated_at": get_utc_now()
                }
            }
        )
        
        # Send cancellation email
        try:
            scheduled_at = make_timezone_aware(meeting["scheduled_at"])
            EmailService.send_meeting_cancelled_email(
                meeting["investor_email"],
                meeting["investor_name"],
                scheduled_at,
                reason or "No reason provided"
            )
        except Exception as e:
            print(f"Failed to send cancellation email: {e}")
        
        return {
            "success": True,
            "message": "Meeting cancelled successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error cancelling meeting: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to cancel meeting"
        )


@router.put("/{meeting_id}/complete")
async def mark_meeting_completed(
    meeting_id: str,
    meeting_notes: Optional[str] = None,
    current_user: dict = Depends(get_current_admin)
):
    """Mark a meeting as completed (Admin only)"""
    try:
        meeting = meetings_collection.find_one({"_id": ObjectId(meeting_id)})
        
        if not meeting:
            raise HTTPException(
                status_code=404,
                detail="Meeting not found"
            )
        
        meetings_collection.update_one(
            {"_id": ObjectId(meeting_id)},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": get_utc_now(),
                    "meeting_notes": meeting_notes,
                    "updated_at": get_utc_now()
                }
            }
        )
        
        return {
            "success": True,
            "message": "Meeting marked as completed"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error completing meeting: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to mark meeting as completed"
        )


@router.delete("/{meeting_id}")
async def delete_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_admin)
):
    """Delete a meeting (Admin only)"""
    try:
        result = meetings_collection.delete_one({"_id": ObjectId(meeting_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=404,
                detail="Meeting not found"
            )
        
        return {
            "success": True,
            "message": "Meeting deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting meeting: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete meeting"
        )


# ==================== Brevo Webhook Endpoints ====================

@router.post("/webhooks/brevo")
async def brevo_meeting_webhook(payload: dict):
    """
    Webhook endpoint for Brevo meeting notifications.
    
    Brevo sends webhooks for the following events:
    - meeting_booked: When a meeting is scheduled through the booking page
    - meeting_started: When a meeting begins
    - meeting_cancelled: When a meeting is cancelled
    
    To set up:
    1. Go to Brevo Dashboard > Meetings > Settings > Webhooks
    2. Add this URL: https://your-domain.com/api/meetings/webhooks/brevo
    3. Select the events you want to receive
    """
    try:
        event_type = payload.get("event")
        meeting_data = payload.get("data", {})
        
        print(f"Received Brevo webhook: {event_type}")
        print(f"Meeting data: {meeting_data}")
        
        if event_type == "meeting_booked":
            # Create a new meeting record from Brevo booking
            meeting_record = {
                "investor_name": meeting_data.get("attendee_name", "Unknown"),
                "investor_email": meeting_data.get("attendee_email", ""),
                "scheduled_at": meeting_data.get("meeting_start_timestamp"),
                "duration_minutes": meeting_data.get("duration_minutes", 30),
                "meeting_link": meeting_data.get("meeting_url", ""),
                "status": "scheduled",
                "notes": meeting_data.get("notes", ""),
                "source": "brevo",
                "brevo_meeting_id": meeting_data.get("meeting_id"),
                "created_at": get_utc_now(),
                "updated_at": get_utc_now()
            }
            
            meetings_collection.insert_one(meeting_record)
            print(f"Created meeting from Brevo: {meeting_record['investor_email']}")
            
        elif event_type == "meeting_cancelled":
            # Update meeting status if we have it
            brevo_id = meeting_data.get("meeting_id")
            if brevo_id:
                meetings_collection.update_one(
                    {"brevo_meeting_id": brevo_id},
                    {
                        "$set": {
                            "status": "cancelled",
                            "cancelled_at": get_utc_now(),
                            "cancellation_reason": "Cancelled via Brevo",
                            "updated_at": get_utc_now()
                        }
                    }
                )
                print(f"Cancelled Brevo meeting: {brevo_id}")
                
        elif event_type == "meeting_started":
            # Log that meeting started
            brevo_id = meeting_data.get("meeting_id")
            if brevo_id:
                meetings_collection.update_one(
                    {"brevo_meeting_id": brevo_id},
                    {
                        "$set": {
                            "started_at": get_utc_now(),
                            "updated_at": get_utc_now()
                        }
                    }
                )
                print(f"Brevo meeting started: {brevo_id}")
        
        return {"status": "ok", "event": event_type}
        
    except Exception as e:
        print(f"Error processing Brevo webhook: {e}")
        # Return 200 to prevent Brevo from retrying
        return {"status": "error", "message": str(e)}


@router.get("/booking-url")
async def get_booking_url():
    """
    Get the configured booking URL (Brevo or Jitsi).
    This can be used by the frontend to display a "Book a Meeting" button.
    """
    import os
    
    brevo_url = os.environ.get("BREVO_BOOKING_URL")
    
    if brevo_url:
        return {
            "provider": "brevo",
            "url": brevo_url,
            "message": "Book a meeting using our Brevo booking page"
        }
    else:
        return {
            "provider": "jitsi",
            "url": None,
            "message": "Meetings use Jitsi Meet - links are generated when scheduling"
        }