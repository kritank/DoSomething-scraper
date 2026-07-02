import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services.dispatch_service import DispatchService
from app.queue.base import ScrapeJobMessage


@pytest.mark.asyncio
async def test_dispatch_scrape_job():
    influencer_id = uuid4()
    job_id = uuid4()
    
    mock_session = AsyncMock()
    
    with patch("app.services.dispatch_service.InfluencerRepo") as MockInfluencerRepo, \
         patch("app.services.dispatch_service.ScrapeJobRepo") as MockJobRepo, \
         patch("app.services.dispatch_service.get_queue") as mock_get_queue:
        
        # Setup mocks
        mock_influencer_repo = MockInfluencerRepo.return_value
        mock_influencer = AsyncMock()
        mock_influencer.id = influencer_id
        mock_influencer.handle = "testuser"
        mock_influencer_repo.get_by_id.return_value = mock_influencer
        
        mock_job_repo = MockJobRepo.return_value
        mock_job = AsyncMock()
        mock_job.id = job_id
        mock_job_repo.create.return_value = mock_job
        
        mock_queue = AsyncMock()
        mock_get_queue.return_value = mock_queue
        
        # Run service
        service = DispatchService(mock_session)
        result_job_id = await service.dispatch_scrape_job(influencer_id)
        
        # Verify
        assert result_job_id == job_id
        mock_influencer_repo.get_by_id.assert_called_once_with(influencer_id)
        mock_job_repo.create.assert_called_once_with(influencer_id)
        mock_queue.enqueue.assert_called_once()
        
        called_msg = mock_queue.enqueue.call_args[0][0]
        assert isinstance(called_msg, ScrapeJobMessage)
        assert called_msg.job_id == job_id
        assert called_msg.influencer_id == influencer_id
        assert called_msg.handle == "testuser"
