from __future__ import annotations
import os
import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import tempfile
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from backend import db, config
from backend.pipeline import analyze_media_file
from backend.forensics import ARTIFACT_DIR
from backend.utils import sha256_file
import jwt
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from backend.report import build_pdf_report

ADMIN_HEADER = "x-admin-key"

JWT_SECRET = config.JWT_SECRET
JWT_ALG = config.JWT_ALG
JWT_EXPIRE_HOURS = config.JWT_EXPIRE_HOURS

bearer = HTTPBearer(auto_error=False)


def make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=JWT_EXPIRE_HOURS)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def require_user(
    pool,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await db.get_user_by_id(pool, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="User disabled")

    if not user.get("is_approved", False):
        # frontend clears token on 401; we prefer 403 so it can show a message if you want
        raise HTTPException(status_code=403, detail="User not approved yet")

    return user

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def require_admin(request: Request) -> None:
    expected = config.ADMIN_API_KEY
    got = request.headers.get(ADMIN_HEADER, "")
    if not expected or got != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


class EnableByEmail(BaseModel):
    email: EmailStr
    is_active: Optional[bool] = None
    is_approved: Optional[bool] = None


class SendTempPasswordReq(BaseModel):
    email: EmailStr

class RegisterReq(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    occupation: Optional[str] = None
    company: Optional[str] = None
    use_case: Optional[str] = None
    role: Optional[str] = None
    notes: Optional[str] = None


class LoginReq(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordReq(BaseModel):
    old_password: Optional[str] = None
    new_password: str

class CreateCaseReq(BaseModel):
    title: str
    description: Optional[str] = None

class ReportReq(BaseModel):
    case_id: str


app = FastAPI(title="TruthSig API", version="1.0.0")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, env: str) -> None:
        super().__init__(app)
        self.env = env.lower()

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "geolocation=()")
        if self.env == "production":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or secrets.token_hex(12)
        response: Response = await call_next(request)
        response.headers.setdefault("X-Request-ID", request_id)
        return response



# CORS

origins = config.CORS_ORIGINS
allow_credentials = False  # because we are not using cookies

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.TRUSTED_HOSTS)
app.add_middleware(SecurityHeadersMiddleware, env=config.TRUTHSIG_ENV)
app.add_middleware(RequestIdMiddleware)

@app.on_event("startup")
async def _startup():
    config.validate_production_settings()
    app.state.pool = await db.create_pool()
    await db.init_db(app.state.pool)


@app.on_event("shutdown")
async def _shutdown():
    pool = getattr(app.state, "pool", None)
    if pool:
        await pool.close()


async def get_pool():
    pool = getattr(app.state, "pool", None)
    if not pool:
        raise HTTPException(status_code=500, detail="DB pool not initialized")
    return pool


@app.get("/health")
async def health():
    return {"ok": True}


# -----------------------
# Admin endpoints
# -----------------------

@app.get("/admin/overview")
async def admin_overview(request: Request, pool=Depends(get_pool)):
    require_admin(request)
    counts = await db.counts_overview(pool)
    return {"ok": True, "counts": counts}


@app.get("/admin/pending-users")
async def admin_pending_users(request: Request, pool=Depends(get_pool)):
    require_admin(request)
    return await db.list_pending_users(pool, limit=500)


@app.get("/admin/users")
async def admin_users(request: Request, status: str = "all", pool=Depends(get_pool)):
    require_admin(request)
    return await db.list_users(pool, status=status, limit=500)


@app.get("/admin/cases")
async def admin_cases(request: Request, pool=Depends(get_pool)):
    require_admin(request)
    return await db.list_cases(pool, user_id=None, limit=500)


@app.post("/admin/users/enable-by-email")
async def admin_enable_user_by_email(
    request: Request,
    req: EnableByEmail,
    pool=Depends(get_pool),
):
    require_admin(request)

    user = await db.get_user_by_email(pool, req.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update flags if provided
    if req.is_active is not None:
        await db.set_user_active(pool, user["id"], bool(req.is_active))

    if req.is_approved is not None:
        await db.set_user_approved(pool, user["id"], bool(req.is_approved))

    return {"ok": True}


@app.post("/admin/users/send-temp-password")
async def admin_send_temp_password(
    request: Request,
    req: SendTempPasswordReq,
    pool=Depends(get_pool),
):
    """
    Generates a temporary password, sets must_change_password=true,
    updates password_hash, and emails it (if SMTP configured).

    If SMTP is not configured, returns temp_password in response
    (so you can manually send it).
    """
    require_admin(request)

    user = await db.get_user_by_email(pool, req.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    temp_password = db.generate_temp_password()
    await db.set_user_temp_password(pool, user_id=user["id"], temp_password=temp_password)

    # Try email (optional)
    sent, err = db.try_send_email(
    to_email=req.email,
    subject="TruthSig: Your temporary password",
    body=(
        "Your TruthSig account has a temporary password.\n\n"
        f"Email: {req.email}\n"
        f"Temporary password: {temp_password}\n\n"
        "Please log in and change your password immediately.\n"
    ),
    )

    if not sent:
        # IMPORTANT: don't crash; return temp password + error so admin can act
        sent, err = db.try_send_email_http(
        to_email=req.email,
        subject="TruthSig: Your temporary password",
        body=(
            "Your TruthSig account has a temporary password.\n\n"
            f"Email: {req.email}\n"
            f"Temporary password: {temp_password}\n\n"
            "Please log in and change your password immediately.\n"
        ),
        )

    return {"ok": True,
    "temp_password": temp_password,
    "email_sent": bool(sent),
    "email_error": err,}


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    # FastAPI's default handler can crash if `exc.errors()` contains raw bytes (e.g., multipart body)
    safe_errors = []
    for e in exc.errors():
        e2 = dict(e)
        # "input" can be bytes when body isn't JSON; make it JSON-safe
        if isinstance(e2.get("input"), (bytes, bytearray)):
            e2["input"] = "<binary body omitted>"
        safe_errors.append(e2)

    # Optional: give a helpful hint when someone uploads a file to /report
    if request.url.path == "/report":
        return JSONResponse(
            status_code=422,
            content={
                "detail": safe_errors,
                "hint": "POST /report expects JSON like {'case_id': '...'}; upload files to POST /cases/{case_id}/evidence as multipart/form-data with field name 'file'."
            },
        )

    return JSONResponse(status_code=422, content={"detail": safe_errors})

# -----------------------
# (Optional) Auth endpoints
# -----------------------
# Keep your existing auth routes if you already have them in your project.
# This file focuses on fixing deploy + admin + temp password workflow.

@app.post("/analyze")
async def analyze(request: Request, file: UploadFile = File(...), pool=Depends(get_pool)):
    # Save upload to a temp file (engine functions expect a filesystem path)
    suffix = ""
    if file.filename:
        _, ext = os.path.splitext(file.filename)
        suffix = ext or ""

    tmp_path = None
    start = time.monotonic()
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            content = await file.read()
            tmp.write(content)

        analysis = analyze_media_file(tmp_path, file.filename or "upload")

        latency_ms = int((time.monotonic() - start) * 1000)
        await db.insert_event(
            pool,
            case_id=None,
            evidence_id=None,
            event_type="SCAN_CREATED",
            actor="public",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details={
                "latency_ms": latency_ms,
                "trust_score": analysis.get("trust_score"),
                "provenance_state": analysis.get("provenance_state"),
            },
        )

        return {
            "trust_score": analysis.get("trust_score"),
            "label": analysis.get("label"),
            "one_line_rationale": analysis.get("one_line_rationale"),
            "top_reasons": analysis.get("top_reasons"),
            "provenance": {
                "state": analysis.get("provenance_state"),
                "summary": analysis.get("summary"),
                "flags": analysis.get("provenance_flags"),
                "c2pa_summary": analysis.get("c2pa_summary"),
            },
            "forensics": analysis.get("forensics"),
            "timeline": analysis.get("derived_timeline"),
            "signals": analysis.get("signals"),
            "raw_extracts": analysis.get("raw_extracts"),
        }

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            

@app.post("/auth/register")
async def auth_register(req: RegisterReq, pool=Depends(get_pool)):
    # prevent duplicates
    existing = await db.get_user_by_email(pool, req.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    extras = {
        "use_case": req.use_case,
        "role": req.role,
        "notes": req.notes,
    }

    _ = await db.create_user_request(
        pool,
        name=req.name,
        email=req.email,
        phone=req.phone,
        occupation=req.occupation,
        company=req.company,
        extras=extras,
    )

    # frontend just needs ok: true
    return {"ok": True}


@app.post("/auth/login")
async def auth_login(req: LoginReq, pool=Depends(get_pool)):
    user = await db.get_user_by_email(pool, req.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="User disabled")

    if not user.get("is_approved", False):
        raise HTTPException(status_code=403, detail="Not approved yet")

    if not db.verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = make_token(str(user["id"]))
    # match frontend expectation: {token, user}
    return {
        "token": token,
        "user": {
            "id": str(user["id"]),
            "email": user["email"],
            "name": user.get("name"),
            "must_change_password": bool(user.get("must_change_password")),
            "is_approved": bool(user.get("is_approved")),
            "is_active": bool(user.get("is_active")),
        },
    }


@app.get("/auth/me")
async def auth_me(pool=Depends(get_pool), creds: HTTPAuthorizationCredentials | None = Depends(bearer)):
    user = await require_user(pool, creds)
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "name": user.get("name"),
        "must_change_password": bool(user.get("must_change_password")),
        "is_approved": bool(user.get("is_approved")),
        "is_active": bool(user.get("is_active")),
    }

@app.post("/auth/change-password")
async def auth_change_password(
    req: ChangePasswordReq,
    pool=Depends(get_pool),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    user = await require_user(pool, creds)

    # If user is not in "must change" mode, require old password
    if not user.get("must_change_password", False):
        if not req.old_password:
            raise HTTPException(status_code=400, detail="Old password required")
        if not db.verify_password(req.old_password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

    await db.set_user_password(pool, str(user["id"]), req.new_password)
    return {"ok": True}


@app.get("/cases")
async def my_cases(
    pool=Depends(get_pool),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    user = await require_user(pool, creds)
    return await db.list_cases(pool, user_id=str(user["id"]), limit=200)


@app.post("/cases")
async def create_case(
    req: CreateCaseReq,
    pool=Depends(get_pool),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    user = await require_user(pool, creds)
    return await db.create_case(
        pool,
        user_id=str(user["id"]),
        title=req.title,
        description=req.description,
    )


@app.get("/cases/{case_id}")
async def get_case(
    case_id: str,
    pool=Depends(get_pool),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    user = await require_user(pool, creds)
    c = await db.get_case(pool, case_id=case_id, user_id=str(user["id"]))
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    return c

@app.get("/cases/{case_id}/evidence")
async def list_case_evidence(
    case_id: str,
    pool=Depends(get_pool),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),

):
    user = await require_user(pool, creds)

    c = await db.get_case(pool, case_id=case_id, user_id=str(user["id"]))
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")

    return await db.list_case_evidence(pool, case_id)

@app.post("/cases/{case_id}/evidence")
async def upload_case_evidence(
    case_id: str,
    file: UploadFile = File(...),
    request: Request,
    pool=Depends(get_pool),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    user = await require_user(pool, creds)

    c = await db.get_case(pool, case_id=case_id, user_id=str(user["id"]))
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")

    # Save upload to temp file
    suffix = ""
    if file.filename:
        _, ext = os.path.splitext(file.filename)
        suffix = ext or ""

    tmp_path = None
    start = time.monotonic()
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            content = await file.read()
            tmp.write(content)

        
        analysis_json = analyze_media_file(tmp_path, file.filename or "upload")
        bytes_ = analysis_json.get("bytes") or os.path.getsize(tmp_path)
        sha256 = analysis_json.get("sha256") or sha256_file(tmp_path)
        media_type = analysis_json.get("media_type") or "unknown"
        provenance_state = analysis_json.get("provenance_state") or "UNKNOWN"
        summary = analysis_json.get("one_line_rationale") or analysis_json.get("summary") or ""

        row = await db.insert_evidence(
            pool,
            case_id=case_id,
            filename=file.filename or "upload",
            sha256=sha256,
            media_type=media_type,
            bytes_=bytes_,
            provenance_state=provenance_state,
            summary=summary,
            analysis_json=analysis_json,
        )

        latency_ms = int((time.monotonic() - start) * 1000)
        await db.insert_event(
            pool,
            case_id=case_id,
            evidence_id=str(row["id"]),
            event_type="SCAN_CREATED",
            actor=str(user["id"]),
            ip=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent") if request else None,
            details={
                "latency_ms": latency_ms,
                "trust_score": analysis_json.get("trust_score"),
                "provenance_state": provenance_state,
            },
        )

        return row

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@app.get("/cases/{case_id}/evidence/{evidence_id}")
async def get_evidence(
    case_id: str,
    evidence_id: str,
    pool=Depends(get_pool),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    user = await require_user(pool, creds)
    c = await db.get_case(pool, case_id=case_id, user_id=str(user["id"]))
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    evidence = await db.get_case_evidence(pool, case_id=case_id, evidence_id=evidence_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return evidence
            
@app.get("/cases/{case_id}/events")
async def get_case_events(
    case_id: str,
    limit: int = 50,
    pool=Depends(get_pool),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    user = await require_user(pool, creds)

    c = await db.get_case(pool, case_id=case_id, user_id=str(user["id"]))
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")

    return await db.list_case_events(pool, case_id=case_id, limit=limit)


@app.get("/cases/{case_id}/evidence/{evidence_id}/artifact")
async def get_evidence_artifact(
    case_id: str,
    evidence_id: str,
    kind: str,
    index: int | None = None,
    pool=Depends(get_pool),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    user = await require_user(pool, creds)
    c = await db.get_case(pool, case_id=case_id, user_id=str(user["id"]))
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    evidence = await db.get_case_evidence(pool, case_id=case_id, evidence_id=evidence_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    analysis = evidence.get("analysis_json") or {}
    forensics = analysis.get("forensics") or {}
    path = None
    if kind == "heatmap":
        path = ((forensics.get("results") or {}).get("heatmap_path"))
    elif kind == "frame" and index is not None:
        frames = (forensics.get("results") or {}).get("frame_thumbnails") or []
        if 0 <= index < len(frames):
            path = frames[index]
    elif kind == "frame_heatmap" and index is not None:
        markers = (forensics.get("results") or {}).get("timeline_markers") or []
        if 0 <= index < len(markers):
            path = markers[index].get("heatmap_path")

    if not path:
        raise HTTPException(status_code=404, detail="Artifact not found")

    safe_root = os.path.abspath(ARTIFACT_DIR)
    abs_path = os.path.abspath(path)
    if os.path.commonpath([safe_root, abs_path]) != safe_root:
        raise HTTPException(status_code=400, detail="Invalid artifact path")

    return FileResponse(abs_path)


@app.post("/cases/{case_id}/evidence/{evidence_id}/report")
async def generate_evidence_report(
    case_id: str,
    evidence_id: str,
    request: Request,
    pool=Depends(get_pool),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    start = time.monotonic()
    user = await require_user(pool, creds)
    c = await db.get_case(pool, case_id=case_id, user_id=str(user["id"]))
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    evidence = await db.get_case_evidence(pool, case_id=case_id, evidence_id=evidence_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    events = await db.list_evidence_events(pool, evidence_id, limit=30)
    analysis = evidence.get("analysis_json") or {}
    analysis["report_integrity"] = {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }
    analysis["chain_of_custody"] = events

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf_path = tmp.name

    build_pdf_report(analysis, pdf_path)

    latency_ms = int((time.monotonic() - start) * 1000)
    await db.insert_event(
        pool,
        case_id=case_id,
        evidence_id=evidence_id,
        event_type="PDF_EXPORTED",
        actor=str(user["id"]),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"latency_ms": latency_ms},
    )

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"TruthSig-evidence-{evidence_id}.pdf",
    )


@app.post("/cases/{case_id}/evidence/{evidence_id}/share")
async def share_evidence(
    case_id: str,
    evidence_id: str,
    request: Request,
    pool=Depends(get_pool),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    user = await require_user(pool, creds)
    c = await db.get_case(pool, case_id=case_id, user_id=str(user["id"]))
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    evidence = await db.get_case_evidence(pool, case_id=case_id, evidence_id=evidence_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    token = secrets.token_urlsafe(16)
    link = await db.create_evidence_public_link(pool, evidence_id=evidence_id, token=token)
    public_url = str(request.base_url) + f"public/evidence/{token}"
    return {"token": link["token"], "public_url": public_url}


@app.get("/public/evidence/{token}")
async def public_evidence(token: str, pool=Depends(get_pool)):
    link = await db.get_public_link(pool, token)
    if not link or link.get("revoked_at"):
        raise HTTPException(status_code=404, detail="Link not found")

    evidence = await db.get_evidence_by_id(pool, evidence_id=str(link["evidence_id"]))
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    analysis = evidence.get("analysis_json") or {}
    public_forensics = analysis.get("forensics") or {}
    if isinstance(public_forensics, dict):
        public_forensics = dict(public_forensics)
        results = public_forensics.get("results")
        if isinstance(results, dict):
            sanitized = {
                k: v
                for k, v in results.items()
                if k not in {"heatmap_path", "thumbnail_path", "frame_thumbnails", "flagged_frames", "timeline_markers"}
            }
            public_forensics["results"] = sanitized

    return {
        "evidence_id": str(evidence.get("id")),
        "filename": evidence.get("filename"),
        "created_at": evidence.get("created_at"),
        "trust_score": analysis.get("trust_score"),
        "label": analysis.get("label"),
        "one_line_rationale": analysis.get("one_line_rationale"),
        "top_reasons": analysis.get("top_reasons"),
        "provenance": {
            "state": analysis.get("provenance_state"),
            "summary": analysis.get("summary"),
            "flags": analysis.get("provenance_flags"),
            "c2pa_summary": analysis.get("c2pa_summary"),
        },
        "forensics": public_forensics,
        "timeline": analysis.get("derived_timeline"),
        "signals": analysis.get("signals"),
    }

@app.post("/report")
async def generate_report(
    req: ReportReq,
    pool=Depends(get_pool),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    user = await require_user(pool, creds)

    c = await db.get_case(pool, case_id=req.case_id, user_id=str(user["id"]))
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")

    evidence = await db.list_case_evidence(pool, req.case_id)

    # Build structured result for PDF
    result = {
        "filename": c.get("title"),
        "media_type": "case",
        "sha256": "",
        "bytes": "",
        "provenance_state": c.get("status"),
        "metadata": {},
        "c2pa": {},
        "derived_timeline": {},
        "metadata_consistency": {},
@@ -678,26 +810,37 @@ async def generate_report(
        "what_would_make_verifiable": [],
        "decision_context": {
            "purpose": "Legal and forensic documentation of digital evidence."
        },
        "report_integrity": {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        },
        )
    }

    # Attach evidence
    result["evidence"] = evidence

    # Create temporary PDF file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf_path = tmp.name

    # Generate PDF using your ReportLab logic
    build_pdf_report(result, pdf_path)

    # Return the PDF file
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"TruthSig-report-{req.case_id}.pdf",
    
    )
    


@app.get("/admin/metrics/summary")
async def admin_metrics_summary(
    request: Request,
    days: int = 7,
    pool=Depends(get_pool),
):
    require_admin(request)
    days = max(1, min(days, 90))
    return await db.metrics_summary(pool, days=days)