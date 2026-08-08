import click
from datetime import UTC, datetime
from flask import current_app
from flask.cli import with_appcontext
from rq.exceptions import DuplicateJobError

from chargemate.maintenance.tasks import (
    expire_stale_booking_holds_job,
    reconcile_pending_refunds_job,
)


@click.group("maintenance")
def maintenance_cli() -> None:
    """Enqueue recurring maintenance work for an RQ worker."""


@maintenance_cli.command("enqueue")
@with_appcontext
def enqueue_maintenance_jobs() -> None:
    """Enqueue one deduplicated run of every maintenance task."""

    queue = current_app.extensions["maintenance_queue"]
    minute_bucket = datetime.now(UTC).strftime("%Y%m%dT%H%M")
    jobs = (
        (
            expire_stale_booking_holds_job,
            f"maintenance-expire-holds-{minute_bucket}",
        ),
        (
            reconcile_pending_refunds_job,
            f"maintenance-reconcile-refunds-{minute_bucket}",
        ),
    )
    for task, job_id in jobs:
        try:
            queue.enqueue(
                task,
                job_id=job_id,
                unique=True,
                result_ttl=30,
                failure_ttl=3600,
            )
            click.echo(f"Enqueued {job_id}.")
        except DuplicateJobError:
            click.echo(f"Skipped duplicate {job_id}.")
