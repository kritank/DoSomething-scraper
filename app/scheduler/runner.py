import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.database import get_session, init_db, close_db
from app.services.dispatch_service import DispatchService
from app.repositories.influencer_repo import InfluencerRepo

logger = logging.getLogger(__name__)

async def run_daily_scrapes():
    async with get_session() as session:
        dispatch_service = DispatchService(session)
        influencer_repo = InfluencerRepo(session)
        
        influencers = await influencer_repo.get_all()
        count = 0
        for influencer in influencers:
            if influencer.is_active:
                await dispatch_service.dispatch_scrape_job(influencer.id)
                count += 1
        logger.info(f"Dispatched scrapes for {count} influencers")

async def main():
    await init_db()
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_daily_scrapes, CronTrigger(hour=0, minute=0))
    scheduler.start()
    
    logger.info("Scheduler started. Running daily scrapes at midnight UTC.")
    
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down...")
    finally:
        await close_db()

if __name__ == "__main__":
    asyncio.run(main())
