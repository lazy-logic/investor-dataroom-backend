import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import authentication routers
from routers.admin_auth import admin_auth_router, admin_router, auth_router
from routers.access_requests import router as access_requests_router
from routers.nda import router as nda_router
from routers.permissions import router as permissions_router
from routers.documents import router as documents_router
from routers.search import router as search_router
from routers.qa import router as qa_router
from routers.company_info import router as company_info_router
from routers.otp import router as otp_router
from config import settings
from routers.meetings import router as meetings_router
from routers.admin_dashboard_router import router as admin_settings_router

app = FastAPI(
    title=settings.APP_NAME,
    description="Secure investor dataroom with advanced search, Q&A, document preview, and company information",
    version="2.1.0",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500, content={"detail": "Internal server error occurred"}
    )


# Public Routes
app.include_router(access_requests_router)  # /api/access-requests/*

# Authentication Routes
app.include_router(admin_auth_router)       # /api/admin-auth/* - Admin authentication
app.include_router(admin_router)            # /api/admin/* - Admin management
app.include_router(auth_router)             # /api/auth/* - User OTP authentication

# Core Feature Routes
app.include_router(nda_router)              # /api/nda/*
app.include_router(permissions_router)      # /api/permissions/*
app.include_router(documents_router)        # /api/documents/*

# Optional Feature Routes
app.include_router(search_router)           # /api/search/* - Document search
app.include_router(qa_router)               # /api/qa/* - Q&A system
app.include_router(company_info_router)     # /api/company/* - Company information
app.include_router(otp_router) 
app.include_router(meetings_router)
app.include_router(admin_settings_router)  # /api/admin/settings/* - Admin dashboard settings, health, cleanup

@app.get("/")
def root():
    return {
        "message": "SAYeTECH Investor Dataroom API",
        "version": "2.1.0",
        "features": [
            " Advanced Document Search with Auto-suggestions",
            " In-Browser Document Preview (PDF, Office, Video)",
            " Document Version Control & History",
            " Investor Q&A System with Email Notifications",
            " Executive Summary & Key Metrics Dashboard",
            " Awards, Testimonials & Media Coverage",
            " Access Request Management",
            " Admin & User Authentication (JWT + OTP)",
            " NDA Digital Signature",
            " Role-Based Access Control",
            " Document Category Management",
            " Audit Logging & Analytics",
        ],
    }

@app.get("/health")
def health():
    return {"status": "healthy", "version": "2.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)