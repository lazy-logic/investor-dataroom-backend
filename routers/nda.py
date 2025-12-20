
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from models.nda import NDAAcceptance, NDAResponse, NDAContent
from services.nda_service import NDAService
from services.auth_service import AuthService

router = APIRouter(prefix="/api/nda", tags=["NDA"])
security = HTTPBearer()

def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Extract user ID from JWT token"""
    token = credentials.credentials
    payload = AuthService.verify_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload["sub"]

@router.get("/content", response_model=NDAContent)
def get_nda_content():
    """Get current NDA content"""
    return NDAService.get_nda_content()

@router.post("/accept")
def accept_nda(
    nda_acceptance: NDAAcceptance,
    request: Request,
    user_id: str = Depends(get_current_user_id)
):
    """Accept NDA agreement"""
    try:
        result = NDAService.accept_nda(
            user_id=user_id,
            digital_signature=nda_acceptance.digital_signature,
            ip_address=nda_acceptance.ip_address or request.client.host,
            user_agent=nda_acceptance.user_agent or request.headers.get("user-agent", "")
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/status")
def check_nda_status(user_id: str = Depends(get_current_user_id)):
    """Check if user has accepted NDA"""
    has_accepted = NDAService.has_accepted_nda(user_id)
    acceptance = NDAService.get_user_nda_acceptance(user_id) if has_accepted else None
    
    # Return format matching frontend NDAStatus type
    return {
        "accepted": has_accepted,
        "accepted_at": acceptance.get("accepted_at") if acceptance else None,
        "version": acceptance.get("nda_version") if acceptance else None,
        "nda_id": acceptance.get("id") if acceptance else None
    }