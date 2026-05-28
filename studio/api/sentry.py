"""Sentry integration for error tracking"""
import os
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

def init_sentry():
    """Initialize Sentry SDK"""
    sentry_dsn = os.getenv("SENTRY_DSN")
    if not sentry_dsn:
        return  # Sentry disabled if no DSN

    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        environment=os.getenv("ENV", "development"),
    )
