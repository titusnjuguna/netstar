from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, cast, Date
from datetime import date, timedelta
from api.db.session import get_db
from api.models.payment import Subscription, HotspotPayments
from api.models.setup import RouterInfo, Products
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

    # HotspotPayments scoped to this client via Products → RouterInfo
    def _hp_for_client(q):
        return (
            q.join(Products, HotspotPayments.product_id == Products.id)
             .join(RouterInfo, Products.router_id == RouterInfo.id)
             .filter(RouterInfo.client_id == client)
        )

    total_revenue = (
        _hp_for_client(db.query(func.sum(HotspotPayments.amount)))
        .scalar()
    ) or 0

    active_sessions = (
        db.query(Subscription)
        .join(HotspotPayments, Subscription.payment_id == HotspotPayments.id)
        .join(Products, HotspotPayments.product_id == Products.id)
        .join(RouterInfo, Products.router_id == RouterInfo.id)
        .filter(Subscription.is_active.is_(True), RouterInfo.client_id == client)
        .count()
    )

    total_routers = (
        db.query(RouterInfo)
        .filter(RouterInfo.client_id == client)
        .count()
    )

    vouchers_sold = (
        _hp_for_client(db.query(HotspotPayments))
        .filter(
            extract("month", HotspotPayments.payment_date) == today.month,
            extract("year", HotspotPayments.payment_date) == today.year,
        )
        .count()
    )

    today_sales = (
        _hp_for_client(db.query(func.sum(HotspotPayments.amount)))
        .filter(cast(HotspotPayments.payment_date, Date) == today)
        .scalar()
    ) or 0

    weekly_sales = (
        _hp_for_client(db.query(func.sum(HotspotPayments.amount)))
        .filter(cast(HotspotPayments.payment_date, Date) >= today - timedelta(days=6))
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
