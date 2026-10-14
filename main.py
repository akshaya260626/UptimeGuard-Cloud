import os
import socket
import ipaddress
import logging
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl, Field
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, desc
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("uptimeguard")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./uptimeguard.db")
# Render and some providers supply postgres://; SQLAlchemy expects postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class Website(Base):
    __tablename__ = "websites"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    url = Column(String(2048), nullable=False)
    interval_minutes = Column(Integer, default=5, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    checks = relationship("CheckResult", back_populates="website", cascade="all, delete-orphan")

class CheckResult(Base):
    __tablename__ = "check_results"
    id = Column(Integer, primary_key=True, index=True)
    website_id = Column(Integer, ForeignKey("websites.id"), nullable=False, index=True)
    checked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    is_up = Column(Boolean, nullable=False)
    status_code = Column(Integer, nullable=True)
    response_ms = Column(Float, nullable=True)
    error = Column(String(500), nullable=True)
    website = relationship("Website", back_populates="checks")

Base.metadata.create_all(bind=engine)

class WebsiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: HttpUrl
    interval_minutes: int = Field(default=5, ge=1, le=60)

def validate_public_url(raw_url: str):
    """Block local/private targets to reduce SSRF risk. Redirects are disabled."""
    parsed = urlparse(raw_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Only valid HTTP/HTTPS URLs are allowed.")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain", "metadata.google.internal"}:
        raise ValueError("Local and metadata hosts cannot be monitored.")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError("Hostname could not be resolved.")
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0].split("%")[0])
        if not ip.is_global:
            raise ValueError("Private, loopback, link-local, and reserved IP addresses are blocked.")
    return raw_url

def run_check(website_id: int):
    db = SessionLocal()
    try:
        website = db.query(Website).filter(Website.id == website_id, Website.enabled == True).first()
        if not website:
            return
        started = datetime.now(timezone.utc)
        is_up, status_code, response_ms, error = False, None, None, None
        try:
            validate_public_url(website.url)
            start = __import__("time").perf_counter()
            with httpx.Client(timeout=10.0, follow_redirects=False, headers={"User-Agent": "UptimeGuardCloud/1.0"}) as client:
                response = client.get(website.url)
            response_ms = round((__import__("time").perf_counter() - start) * 1000, 2)
            status_code = response.status_code
            is_up = 200 <= status_code < 400
            if not is_up:
                error = f"HTTP {status_code}"
        except Exception as exc:
            error = str(exc)[:490]
        previous = db.query(CheckResult).filter(
            CheckResult.website_id == website_id
        ).order_by(desc(CheckResult.checked_at)).first()
        previous_state = previous.is_up if previous else None
        result = CheckResult(
            website_id=website_id, checked_at=started, is_up=is_up,
            status_code=status_code, response_ms=response_ms, error=error
        )
        db.add(result)
        db.commit()
        log.info("check website_id=%s up=%s status=%s latency_ms=%s", website_id, is_up, status_code, response_ms)
        if previous_state is not None and previous_state != is_up:
            send_transition_alert(website, is_up, status_code, error, response_ms)
    except Exception:
        log.exception("Monitoring check failed")
        db.rollback()
    finally:
        db.close()

def send_transition_alert(website, is_up, status_code, error, response_ms):
    """Send email only when a monitor changes between UP and DOWN."""
    host = os.getenv("SMTP_HOST")
    recipient = os.getenv("ALERT_EMAIL_TO")
    sender = os.getenv("ALERT_EMAIL_FROM", os.getenv("SMTP_USER", ""))
    if not host or not recipient or not sender:
        log.info("Email alert skipped: SMTP settings are not configured.")
        return
    state = "RECOVERED" if is_up else "DOWN"
    msg = EmailMessage()
    msg["Subject"] = f"[UptimeGuard] {website.name} is {state}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(
        f"Website: {website.name}\nURL: {website.url}\nStatus: {state}\n"
        f"HTTP status: {status_code}\nResponse time: {response_ms} ms\nError: {error or 'None'}"
    )
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=10) as smtp:
            smtp.starttls()
            user, password = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
        log.info("Transition alert sent for website_id=%s state=%s", website.id, state)
    except Exception:
        log.exception("Email alert delivery failed")

def check_all():
    """Run only monitors whose configured interval has elapsed."""
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    due_ids = []
    try:
        websites = db.query(Website).filter(Website.enabled == True).all()
        for website in websites:
            latest = db.query(CheckResult).filter(
                CheckResult.website_id == website.id
            ).order_by(desc(CheckResult.checked_at)).first()
            due_after = timedelta(minutes=website.interval_minutes)
            if latest is None or (now - latest.checked_at) >= due_after:
                due_ids.append(website.id)
    finally:
        db.close()
    for website_id in due_ids:
        run_check(website_id)

scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(check_all, "interval", minutes=1, id="monitor_all", replace_existing=True, max_instances=1)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)

app = FastAPI(title="UptimeGuard Cloud", version="1.0.0", description="Cloud-based website uptime monitoring system", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/health")
def health():
    return {"status": "ok", "service": "UptimeGuard Cloud", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/api/websites")
def list_websites():
    db = SessionLocal()
    try:
        websites = db.query(Website).order_by(desc(Website.created_at)).all()
        output = []
        for w in websites:
            latest = db.query(CheckResult).filter(CheckResult.website_id == w.id).order_by(desc(CheckResult.checked_at)).first()
            recent = db.query(CheckResult).filter(CheckResult.website_id == w.id, CheckResult.checked_at >= datetime.now(timezone.utc)-timedelta(days=30)).all()
            uptime = round(100 * sum(1 for c in recent if c.is_up) / len(recent), 2) if recent else None
            output.append({
                "id": w.id, "name": w.name, "url": w.url, "interval_minutes": w.interval_minutes,
                "enabled": w.enabled, "status": ("UP" if latest and latest.is_up else "DOWN" if latest else "PENDING"),
                "last_checked": latest.checked_at.isoformat() if latest else None,
                "status_code": latest.status_code if latest else None,
                "response_ms": latest.response_ms if latest else None,
                "last_error": latest.error if latest else None, "uptime_30d": uptime,
                "checks_count": len(recent)
            })
        return output
    finally:
        db.close()

@app.post("/api/websites", status_code=201)
def add_website(payload: WebsiteCreate):
    url = str(payload.url)
    try:
        validate_public_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db = SessionLocal()
    try:
        existing = db.query(Website).filter(Website.url == url).first()
        if existing:
            raise HTTPException(status_code=409, detail="This URL is already being monitored.")
        website = Website(name=payload.name.strip(), url=url, interval_minutes=payload.interval_minutes)
        db.add(website)
        db.commit()
        db.refresh(website)
        website_id = website.id
    finally:
        db.close()
    run_check(website_id)
    return {"message": "Website added and initial check completed.", "id": website_id}

@app.post("/api/websites/{website_id}/check")
def check_now(website_id: int):
    db = SessionLocal()
    try:
        website = db.query(Website).filter(Website.id == website_id).first()
        if not website:
            raise HTTPException(status_code=404, detail="Website not found.")
    finally:
        db.close()
    run_check(website_id)
    return {"message": "Check completed."}

@app.patch("/api/websites/{website_id}/toggle")
def toggle_website(website_id: int):
    db = SessionLocal()
    try:
        website = db.query(Website).filter(Website.id == website_id).first()
        if not website:
            raise HTTPException(status_code=404, detail="Website not found.")
        website.enabled = not website.enabled
        db.commit()
        return {"id": website.id, "enabled": website.enabled}
    finally:
        db.close()

@app.delete("/api/websites/{website_id}")
def delete_website(website_id: int):
    db = SessionLocal()
    try:
        website = db.query(Website).filter(Website.id == website_id).first()
        if not website:
            raise HTTPException(status_code=404, detail="Website not found.")
        db.delete(website)
        db.commit()
        return {"message": "Website and its history deleted."}
    finally:
        db.close()

@app.get("/api/websites/{website_id}/history")
def website_history(website_id: int, limit: int = 100):
    db = SessionLocal()
    try:
        website = db.query(Website).filter(Website.id == website_id).first()
        if not website:
            raise HTTPException(status_code=404, detail="Website not found.")
        rows = db.query(CheckResult).filter(CheckResult.website_id == website_id).order_by(desc(CheckResult.checked_at)).limit(max(1, min(limit, 500))).all()
        return [{"checked_at": r.checked_at.isoformat(), "is_up": r.is_up, "status_code": r.status_code, "response_ms": r.response_ms, "error": r.error} for r in reversed(rows)]
    finally:
        db.close()

@app.get("/api/summary")
def summary():
    db = SessionLocal()
    try:
        websites = db.query(Website).all()
        latest_results = []
        for w in websites:
            latest = db.query(CheckResult).filter(CheckResult.website_id == w.id).order_by(desc(CheckResult.checked_at)).first()
            if latest:
                latest_results.append(latest)
        return {
            "websites_total": len(websites),
            "websites_up": sum(1 for r in latest_results if r.is_up),
            "websites_down": sum(1 for r in latest_results if not r.is_up),
            "avg_response_ms": round(sum(r.response_ms for r in latest_results if r.response_ms is not None) / max(1, sum(1 for r in latest_results if r.response_ms is not None)), 2) if any(r.response_ms is not None for r in latest_results) else None,
            "checks_total": db.query(CheckResult).count()
        }
    finally:
        db.close()
