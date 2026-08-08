from datetime import UTC, datetime


def expire_stale_booking_holds_job() -> dict[str, int]:
    """RQ entry point that expires one bounded batch of stale holds."""

    from chargemate import create_app
    from chargemate.maintenance.service import expire_stale_booking_holds

    app = create_app()
    with app.app_context():
        expired = expire_stale_booking_holds(
            datetime.now(UTC),
            app.config["MAINTENANCE_BATCH_SIZE"],
        )
        app.logger.info("Expired %s stale booking holds.", expired)
        return {"expired": expired}


def reconcile_pending_refunds_job() -> dict[str, int]:
    """RQ entry point that refreshes unresolved Razorpay refund states."""

    from chargemate import create_app
    from chargemate.maintenance.service import reconcile_pending_refunds

    app = create_app()
    key_id = app.config.get("RAZORPAY_KEY_ID")
    key_secret = app.config.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise RuntimeError("Razorpay credentials are required for reconciliation.")

    with app.app_context():
        counts = reconcile_pending_refunds(
            key_id=key_id,
            key_secret=key_secret,
            batch_size=app.config["MAINTENANCE_BATCH_SIZE"],
        )
        app.logger.info("Refund reconciliation result: %s", counts)
        return counts
