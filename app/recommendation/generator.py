from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.influencer import Influencer
from app.models.benchmark import CategoryBenchmark
from app.models.recommendation import Recommendation

class RecommendationGenerator:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_for_influencer(self, influencer_id: UUID) -> list[Recommendation]:
        influencer = await self.session.get(Influencer, influencer_id)
        if not influencer:
            return []
            
        stmt = select(CategoryBenchmark).where(
            CategoryBenchmark.category_id == influencer.category_id
        ).order_by(CategoryBenchmark.computed_at.desc()).limit(1)
        
        benchmark = (await self.session.execute(stmt)).scalar_one_or_none()
        
        recs = []
        if benchmark:
            # Placeholder for recommendation logic
            rec = Recommendation(
                influencer_id=influencer.id,
                category_id=benchmark.category_id,
                priority="high",
                recommendation_type="posting_frequency",
                title="Increase Posting Frequency",
                body=f"Top creators in your category post {benchmark.avg_posting_freq_week} times a week.",
                metric_value="2.0",
                benchmark_value=str(benchmark.avg_posting_freq_week),
            )
            self.session.add(rec)
            recs.append(rec)
            await self.session.commit()
            
        return recs
