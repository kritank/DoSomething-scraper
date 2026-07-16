import os
import socket

# One per worker process -- attached to whichever ScrapeJob/account this
# process is currently holding, so a stuck lease/lease reaper log line can
# be traced back to the process that held it.
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


class JobCancelledError(Exception):
    """Internal control-flow signal only -- raised inside a processor's
    _run_scrape when its cancel event fires, caught in process() to route
    the job to a "cancelled" outcome. Never surfaces as an HTTP response
    (unlike the ViralyticBaseError hierarchy in app.core.exceptions),
    since nothing outside the worker process ever sees it directly.
    Shared by JobProcessor (Instagram) and YouTubeJobProcessor."""
