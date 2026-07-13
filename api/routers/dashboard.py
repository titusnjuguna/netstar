from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, extract, cast, Date
from datetime import date, timedelta
from api.db.session import get_db
from api.models.payment import  Subscription,HotspotPayments
from api.models.setup import RouterInfo
from api.services.auth import verify_token
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


@router.get("/summary/{client}", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    client: int,
    db: Session = Depends(get_db),
    _: dict = Depends(verify_token),
):
    today = date.today()

    # --- Revenue & sessions scoped to THIS client ---
    total_revenue = (
        db.query(func.sum(HotspotPayments.amount))
        .filter(HotspotPayments.client_id == client)   # ← adjust col name to your schema
        .scalar()
    ) or 0

    active_sessions = (
        db.query(Subscription)
        .filter(
            Subscription.is_active.is_(True),
            Subscription.client_id == client,          # ← adjust if needed
        )
        .count()
    )

    total_routers = (
        db.query(RouterInfo)
        .filter(
            RouterInfo.is_active.is_(True),
            RouterInfo.client == client,
        )
        .count()
    )

    # --- Vouchers sold this calendar month (fixed precedence + extract) ---
    vouchers_sold = (
        db.query(HotspotPayments)
        .filter(
            (extract("month", HotspotPayments.payment_date) == today.month) &
            (extract("year",  HotspotPayments.payment_date) == today.year),
            HotspotPayments.client_id == client,       # ← if applicable
        )
        .count()
    )

    # --- Today's sales as REVENUE, not count ---
    today_sales = (
        db.query(func.sum(HotspotPayments.amount))
        .filter(
            cast(HotspotPayments.payment_date, Date) == today,
            HotspotPayments.client_id == client,
        )
        .scalar()
    ) or 0

    # --- Last 7 days (today inclusive) ---
    weekly_sales = (
        db.query(func.sum(HotspotPayments.amount))
        .filter(
            cast(HotspotPayments.payment_date, Date) >= today - timedelta(days=6),
            HotspotPayments.client_id == client,
        )
        .scalar()
    ) or 0

    return DashboardSummaryResponse(
        message="Dashboard summary fetched successfully",
        metrics=DashboardMetrics(
            totalRevenue=total_revenue,
            activeSessions=active_sessions,
            onlineRouters=0,
            totalRouters=total_routers,
            throughputMbps=0.0,
            todaySales=today_sales,
            weeklySales=weekly_sales,
        ),
        weeklyChart=[
            WeeklyChartEntry(day=d, revenue=0, users=0, load=0)
            for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        ],
        liveEvents=[],
        todaysSales=TodaysSales(vouchersSold=vouchers_sold),
        sms=SmsStats(sent=0, failed=0, deliveryRate=0.0),
        systemStatus=SystemStatus(mpesaDarajaUp=True, sysLoadPercent=0.0),
    )