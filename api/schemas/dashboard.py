from pydantic import BaseModel
from typing import List
from datetime import datetime


class DashboardMetrics(BaseModel):
    totalRevenue: float
    activeSessions: int
    onlineRouters: int
    totalRouters: int
    throughputMbps: float


class WeeklyChartEntry(BaseModel):
    day: str
    revenue: float
    users: int
    load: int


class LiveEvent(BaseModel):
    mac: str
    phone: str
    action: str
    product: str
    ip: str
    timestamp: datetime


class TodaysSales(BaseModel):
    vouchersSold: int


class SmsStats(BaseModel):
    sent: int
    failed: int
    deliveryRate: float


class SystemStatus(BaseModel):
    mpesaDarajaUp: bool
    sysLoadPercent: float


class DashboardSummaryResponse(BaseModel):
    message: str
    metrics: DashboardMetrics
    weeklyChart: List[WeeklyChartEntry]
    liveEvents: List[LiveEvent]
    todaysSales: TodaysSales
    sms: SmsStats
    systemStatus: SystemStatus
