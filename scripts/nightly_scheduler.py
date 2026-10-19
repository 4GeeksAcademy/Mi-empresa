from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CRON_EXPRESSION = "30 2 * * *"
logger = logging.getLogger("nightly_scheduler")


class JobContext(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.target_date = os.getenv("TARGET_DATE") or str(
            datetime.now(timezone.utc).date() - timedelta(days=1)
        )
        if not hasattr(record, "job_status"):
            record.job_status = "scheduler"
        return True


def run_export(stopping: Event) -> int:
    if stopping.is_set():
        return 0
    command = [sys.executable, str(REPOSITORY_ROOT / "scripts/nightly_export.py")]
    logger.info("Launching independent export process", extra={"job_status": "processing"})
    try:
        process = subprocess.Popen(command, cwd=REPOSITORY_ROOT)
        try:
            while True:
                try:
                    returncode = process.wait(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    if stopping.is_set():
                        process.terminate()
                        try:
                            returncode = process.wait(timeout=25)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            returncode = process.wait()
                        break
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=25)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        logger.log(logging.INFO if returncode == 0 else logging.ERROR,
                   "Export process exited with code %s", returncode,
                   extra={"job_status": "completed" if returncode == 0 else "failed"})
        return returncode
    except Exception as error:
        logger.error("Cannot run export process: %s", str(error).replace("\n", " "),
                     extra={"job_status": "failed"})
        return 1


def create_scheduler(stopping: Event) -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=timezone.utc)
    scheduler.add_job(
        run_export,
        CronTrigger.from_crontab(CRON_EXPRESSION, timezone=timezone.utc),
        id="nightly_export", args=[stopping], coalesce=True,
        max_instances=2, misfire_grace_time=3600,
    )
    return scheduler


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone APScheduler for nightly telemetry")
    parser.add_argument("--check", action="store_true", help="Check schedule without executing a job")
    arguments = parser.parse_args()
    load_dotenv(REPOSITORY_ROOT / ".env")
    logging.Formatter.converter = time.gmtime
    handler = logging.StreamHandler()
    handler.addFilter(JobContext())
    handler.setFormatter(logging.Formatter(
        "%(asctime)sZ %(levelname)s job_name=nightly_export target_date=%(target_date)s "
        "status=%(job_status)s %(message)s"
    ))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    stopping = Event()
    scheduler = create_scheduler(stopping)
    if arguments.check:
        trigger = scheduler.get_job("nightly_export").trigger
        logger.info("cron=%s timezone=UTC next=%s", CRON_EXPRESSION,
                    trigger.get_next_fire_time(None, datetime.now(timezone.utc)))
        return 0
    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL is required", extra={"job_status": "failed"})
        return 1

    def stop(signum, frame):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        stopping.set()
        raise KeyboardInterrupt

    previous = {signum: signal.signal(signum, stop) for signum in (signal.SIGINT, signal.SIGTERM)}
    try:
        logger.info("Starting standalone scheduler cron=%s timezone=UTC", CRON_EXPRESSION)
        scheduler.start()
    except KeyboardInterrupt:
        pass
    finally:
        stopping.set()
        if scheduler.running:
            scheduler.shutdown(wait=True)
        for signum, previous_handler in previous.items():
            signal.signal(signum, previous_handler)
    return 0


if __name__ == "__main__":
    sys.exit(main())