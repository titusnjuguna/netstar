from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from api.db.session import get_db
from api.models.payment import Payment, Subscription
from api.models.setup import RouterInfo
from api.schemas.dashboard import (
    DashboardSummaryResponse,
    DashboardMetrics,
    WeeklyChartEntry,
    TodaysSales,
    SmsStats,
    SystemStatus,
)

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"]
)


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(db: Session = Depends(get_db)):
    total_revenue = db.query(func.sum(Payment.amount)).scalar() or 0
    active_sessions = db.query(Subscription).filter(Subscription.is_active == True).count()
    total_routers = db.query(RouterInfo).count()
    vouchers_sold = db.query(Payment).filter(func.date(Payment.payment_date) == date.today()).count()

    return DashboardSummaryResponse(
        message="Dashboard summary fetched successfully",
        metrics=DashboardMetrics(
            totalRevenue=total_revenue,
            activeSessions=active_sessions,
            onlineRouters=0,
            totalRouters=total_routers,
            throughputMbps=0.0,
        ),
        # Placeholder until live router polling, hotspot session events, SMS
        # gateway and M-Pesa Daraja health checks are wired up.
        weeklyChart=[
            WeeklyChartEntry(day=day, revenue=0, users=0, load=0)
            for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        ],
        liveEvents=[],
        todaysSales=TodaysSales(vouchersSold=vouchers_sold),
        sms=SmsStats(sent=0, failed=0, deliveryRate=0.0),
        systemStatus=SystemStatus(mpesaDarajaUp=False, sysLoadPercent=0.0),
    )
