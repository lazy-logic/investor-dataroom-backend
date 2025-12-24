import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from config import settings
import requests

class EmailService:
    BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
    
    @staticmethod
    def send_email(to_email: str, subject: str, body: str):
        """Send email using Brevo API (primary) with SMTP fallback"""
        
        # Try Brevo API first (works on cloud platforms)
        if settings.BREVO_API_KEY:
            try:
                result = EmailService._send_via_brevo(to_email, subject, body)
                if result:
                    return True
            except Exception as e:
                print(f"Brevo API failed: {e}")
        
        # Fall back to SMTP if Brevo fails
        return EmailService._send_via_smtp(to_email, subject, body)
    
    @staticmethod
    def _send_via_brevo(to_email: str, subject: str, body: str) -> bool:
        """Send email using Brevo (Sendinblue) API"""
        headers = {
            "accept": "application/json",
            "api-key": settings.BREVO_API_KEY,
            "content-type": "application/json"
        }
        
        payload = {
            "sender": {
                "name": settings.BREVO_SENDER_NAME,
                "email": settings.BREVO_SENDER_EMAIL
            },
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": body
        }
        
        print(f"Sending email via Brevo to {to_email}...")
        response = requests.post(
            EmailService.BREVO_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            print(f"Email sent successfully via Brevo to {to_email}")
            return True
        else:
            print(f"Brevo API error: {response.status_code} - {response.text}")
            return False
    
    @staticmethod
    def _send_via_smtp(to_email: str, subject: str, body: str) -> bool:
        """Send email using SMTP (fallback)"""
        msg = MIMEMultipart()
        msg['From'] = settings.FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        
        # Check if SSL is preferred (use port 465)
        if settings.SMTP_USE_SSL:
            try:
                import ssl
                context = ssl.create_default_context()
                ssl_port = 465
                print(f"Attempting SSL connection to {settings.SMTP_HOST}:{ssl_port}")
                with smtplib.SMTP_SSL(settings.SMTP_HOST, ssl_port, context=context, timeout=30) as server:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                    server.send_message(msg)
                print(f"Email sent successfully via SMTP SSL to {to_email}")
                return True
            except Exception as e:
                print(f"SMTP SSL connection failed: {e}")
        
        # Try TLS connection (port 587 with STARTTLS)
        try:
            print(f"Attempting TLS connection to {settings.SMTP_HOST}:{settings.SMTP_PORT}")
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
                server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
            print(f"Email sent successfully via SMTP TLS to {to_email}")
            return True
        except Exception as e:
            print(f"SMTP TLS connection failed: {e}")
            return False
    
    @staticmethod
    def send_access_request_confirmation(email: str, name: str):
        subject = "Access Request Received - SAYeTECH Dataroom"
        body = f"""
        <h2>Thank you for your interest, {name}</h2>
        <p>We have received your access request to the SAYeTECH investor dataroom.</p>
        <p>Our team will review your request and respond within 24-48 hours.</p>
        """
        return EmailService.send_email(email, subject, body)
    
    @staticmethod
    def send_admin_notification(request_data: dict):
        subject = "New Dataroom Access Request"
        body = f"""
        <h2>New Access Request</h2>
        <p><strong>Name:</strong> {request_data['full_name']}</p>
        <p><strong>Email:</strong> {request_data['email']}</p>
        <p><strong>Company:</strong> {request_data['company']}</p>
        <p><strong>Phone:</strong> {request_data.get('phone', 'N/A')}</p>
        <p><strong>Message:</strong> {request_data.get('message', 'N/A')}</p>
        """
        return EmailService.send_email(settings.ADMIN_EMAIL, subject, body)
    
    @staticmethod
    def send_access_approved(email: str, name: str, token: str):
        subject = "Access Approved - SAYeTECH Dataroom"
        link = f"https://investor-dataroom-frontend.vercel.app/login"
        body = f"""
        <h2>Welcome, {name}!</h2>
        <p>Your access to the SAYeTECH investor dataroom has been approved.</p>
        <p><a href="{link}">Click here to access the dataroom</a></p>
        <p>This link is valid until the expiration date set by our team.</p>
        """
        return EmailService.send_email(email, subject, body)
    
    @staticmethod
    def send_access_denied(email: str, name: str, reason: str = ""):
        subject = "Access Request Update - SAYeTECH Dataroom"
        body = f"""
        <h2>Hello {name},</h2>
        <p>Thank you for your interest in SAYeTECH.</p>
        <p>Unfortunately, we are unable to grant access to the dataroom at this time.</p>
        <p>{reason}</p>
        """
        return EmailService.send_email(email, subject, body)
    
    @staticmethod
    def send_access_request_status(email: str, name: str, status: str, admin_notes: str = None):
        """Send status update email for access request"""
        subject = f"Your Data Room Access Request Status: {status.upper()}"
        
        body = f"""
        <h2>Dear {name},</h2>
        <p>Your data room access request status has been updated to: <strong>{status.upper()}</strong></p>
        """
        
        if admin_notes:
            body += f"<p><strong>Admin Notes:</strong> {admin_notes}</p>"
        
        if status.lower() == "approved":
            body += "<p>Congratulations! Your access request has been approved. You can now access the data room.</p>"
        elif status.lower() == "denied":
            body += "<p>Unfortunately, your access request has been denied. Please contact us if you have questions.</p>"
        else:
            body += "<p>Your request is still under review.</p>"
        
        body += "<p>Thank you for your interest in SAYeTECH.</p>"
        
        return EmailService.send_email(email, subject, body)
    
    @staticmethod
    def send_otp_email(email: str, otp: str):
        """Send OTP email to user"""
        subject = "Your OTP Code for SAYeTECH Data Room"
        
        body = f"""
        <h2>Dear User,</h2>
        <p>Your OTP code for accessing SAYeTECH Data Room is: <strong>{otp}</strong></p>
        <p>This code is valid for 10 minutes.</p>
        <p>Thank you for using SAYeTECH Data Room.</p>
        """
        
        return EmailService.send_email(email, subject, body)
    
    @staticmethod
    def send_approval_email(email: str, name: str, investor_id: str):
        """Send approval email with investor ID"""
        subject = "Access Request Approved - SAYeTECH Dataroom"
        login_link = "https://investor-dataroom-frontend.vercel.app/login"
        
        body = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #4CAF50; margin-bottom: 20px;">Access Request Approved</h2>
                <p style="font-size: 16px;">Hello {name},</p>
                <p>Congratulations! Your access request to the SAYeTECH investor dataroom has been approved.</p>
                
                <div style="background: #f0f8ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #4CAF50;">
                    <p style="margin: 10px 0;"><strong>Your Investor ID:</strong> <code style="background: #e8e8e8; padding: 5px 10px; border-radius: 4px; font-size: 14px;">{investor_id}</code></p>
                    <p style="margin: 10px 0;">Please keep this ID safe for future reference.</p>
                </div>
                
                <div style="margin: 30px 0;">
                    <a href="{login_link}" style="background: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                        Access Dataroom
                    </a>
                </div>
                
                <p style="margin-top: 20px;">If you have any questions, please contact us at:</p>
                <p style="margin: 5px 0;"><a href="mailto:dataroom@sayetech.io" style="color: #4CAF50;">dataroom@sayetech.io</a></p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #666; font-size: 12px; text-align: center;">
                    2024 SAYeTECH. All rights reserved.
                </p>
            </div>
        </body>
        </html>
        """
        
        return EmailService.send_email(email, subject, body)
    
    @staticmethod
    def send_denial_email(email: str, name: str, reason: str):
        """Send denial email with reason"""
        subject = "Access Request Update - SAYeTECH Dataroom"
        
        body = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #f44336; margin-bottom: 20px;">Access Request Update</h2>
                <p style="font-size: 16px;">Hello {name},</p>
                <p>Thank you for your interest in the SAYeTECH investor dataroom.</p>
                
                <div style="background: #ffebee; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #f44336;">
                    <p style="margin: 10px 0;">Unfortunately, we are unable to grant access at this time.</p>
                    <p style="margin: 10px 0;"><strong>Reason:</strong> {reason}</p>
                </div>
                
                <p style="margin-top: 20px;">If you have any questions or would like to discuss this decision, please contact us at:</p>
                <p style="margin: 5px 0;"><a href="mailto:dataroom@sayetech.io" style="color: #4CAF50;">dataroom@sayetech.io</a></p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #666; font-size: 12px; text-align: center;">
                    2024 SAYeTECH. All rights reserved.
                </p>
            </div>
        </body>
        </html>
        """
        
        return EmailService.send_email(email, subject, body)
    
    @staticmethod
    def send_meeting_confirmation_to_investor(email: str, name: str, scheduled_at: datetime, duration: int, link: str):
        """Send meeting confirmation email to investor"""
        subject = "Meeting Scheduled - SAYeTECH"
        
        # Format datetime properly
        scheduled_time = scheduled_at.strftime("%B %d, %Y at %I:%M %p UTC")
        
        body = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #4CAF50; margin-bottom: 20px;">Meeting Confirmed</h2>
                <p style="font-size: 16px;">Hello {name},</p>
                <p>Your meeting with SAYeTECH has been successfully scheduled!</p>
                
                <div style="background: #f0f8ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #4CAF50;">
                    <p style="margin: 10px 0;"><strong>Date & Time:</strong> {scheduled_time}</p>
                    <p style="margin: 10px 0;"><strong>Duration:</strong> {duration} minutes</p>
                    <p style="margin: 10px 0;"><strong>Meeting Link:</strong></p>
                    <a href="{link}" style="background: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin-top: 10px; font-weight: bold;">
                        Join Meeting
                    </a>
                </div>
                
                <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107;">
                    <p style="margin: 0; color: #856404;">
                        <strong>Reminder:</strong> You will receive a reminder email 24 hours before the meeting.
                    </p>
                </div>
                
                <p style="margin-top: 20px;">If you need to reschedule or cancel, please contact us at:</p>
                <p style="margin: 5px 0;"><a href="mailto:dataroom@sayetech.io" style="color: #4CAF50;">dataroom@sayetech.io</a></p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #666; font-size: 12px; text-align: center;">
                    2024 SAYeTECH. All rights reserved.
                </p>
            </div>
        </body>
        </html>
        """
        
        return EmailService.send_email(email, subject, body)

    @staticmethod
    def send_meeting_notification_to_admin(investor_name: str, investor_email: str, scheduled_at: datetime, duration: int):
        """Send meeting notification to admin"""
        subject = f"New Meeting Scheduled with {investor_name}"
        
        scheduled_time = scheduled_at.strftime("%B %d, %Y at %I:%M %p UTC")
        
        body = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px;">
                <h2 style="color: #2196F3;">New Meeting Scheduled</h2>
                
                <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 10px 0;"><strong>Investor:</strong> {investor_name}</p>
                    <p style="margin: 10px 0;"><strong>Email:</strong> {investor_email}</p>
                    <p style="margin: 10px 0;"><strong>Scheduled:</strong> {scheduled_time}</p>
                    <p style="margin: 10px 0;"><strong>Duration:</strong> {duration} minutes</p>
                </div>
                
                <p style="color: #666;">Please check your admin dashboard for more details.</p>
            </div>
        </body>
        </html>
        """
        
        return EmailService.send_email(settings.ADMIN_EMAIL, subject, body)

    @staticmethod
    def send_meeting_rescheduled_email(email: str, name: str, old_time: datetime, new_time: datetime, link: str):
        """Send email when meeting is rescheduled"""
        subject = "Meeting Rescheduled - SAYeTECH"
        
        old_time_str = old_time.strftime("%B %d, %Y at %I:%M %p UTC")
        new_time_str = new_time.strftime("%B %d, %Y at %I:%M %p UTC")
        
        body = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #FF9800;">Meeting Rescheduled</h2>
                <p>Hello {name},</p>
                <p>Your meeting has been rescheduled to a new time.</p>
                
                <div style="background: #fff3e0; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 10px 0;"><strong>Previous Time:</strong></p>
                    <p style="margin: 10px 0; text-decoration: line-through; color: #666;">{old_time_str}</p>
                    
                    <p style="margin: 20px 0 10px 0;"><strong>New Time:</strong></p>
                    <p style="margin: 10px 0; color: #4CAF50; font-weight: bold; font-size: 16px;">{new_time_str}</p>
                </div>
                
                <a href="{link}" style="background: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin-top: 10px; font-weight: bold;">
                    Join Meeting
                </a>
                
                <p style="margin-top: 20px;">If you have any questions, please contact us at <a href="mailto:dataroom@sayetech.io">dataroom@sayetech.io</a></p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #666; font-size: 12px; text-align: center;">
                    2024 SAYeTECH. All rights reserved.
                </p>
            </div>
        </body>
        </html>
        """
        
        return EmailService.send_email(email, subject, body)

    @staticmethod
    def send_meeting_cancelled_email(email: str, name: str, scheduled_at: datetime, reason: str):
        """Send email when meeting is cancelled"""
        subject = "Meeting Cancelled - SAYeTECH"
        
        scheduled_time = scheduled_at.strftime("%B %d, %Y at %I:%M %p UTC")
        
        body = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #f44336;">Meeting Cancelled</h2>
                <p>Hello {name},</p>
                <p>Unfortunately, your meeting has been cancelled.</p>
                
                <div style="background: #ffebee; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #f44336;">
                    <p style="margin: 10px 0;"><strong>Cancelled Meeting:</strong> {scheduled_time}</p>
                    <p style="margin: 10px 0;"><strong>Reason:</strong> {reason}</p>
                </div>
                
                <p>To schedule a new meeting, please contact us at:</p>
                <p style="margin: 5px 0;"><a href="mailto:dataroom@sayetech.io" style="color: #4CAF50;">dataroom@sayetech.io</a></p>
                
                <p style="margin-top: 20px; color: #666;">We apologize for any inconvenience this may have caused.</p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #666; font-size: 12px; text-align: center;">
                    2024 SAYeTECH. All rights reserved.
                </p>
            </div>
        </body>
        </html>
        """
        
        return EmailService.send_email(email, subject, body) 