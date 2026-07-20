"""backfill creator groups + account_type for pre-existing influencers

Revision ID: a785e9a1b792
Revises: cc24e0805c5d
Create Date: 2026-07-19 05:00:00.000000+00:00

Data migration, not a schema change. Two independent cleanups for rows that
predate features added after they were created:

1. InfluencerRepo.create() now auto-links every new influencer to its own
   Creator group (defaulting the name to its handle when none is given),
   but rows created before that change still have creator_id = NULL -- with
   no combined creator profile page as a result (the dashboard only shows
   "linked across N platforms" for a row that has a creator_id at all).
   scripts/backfill_creator_groups.py does the same thing for a one-off
   manual run; this migration exists so the fix applies automatically on
   every environment via the normal `alembic upgrade head` that already
   runs on deploy (see infra/user_data.sh), not just wherever someone
   remembered to run the script by hand.

2. Defensive account_type cleanup -- see the comment at its UPDATE
   statement below.

Idempotent and safe to re-run against a database that's already been
backfilled -- only touches creator_id IS NULL / account_type IS NULL rows.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a785e9a1b792'
down_revision: Union[str, None] = 'cc24e0805c5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Defensive belt-and-suspenders: account_type is NOT NULL with a
    # server_default, so a normal `ADD COLUMN ... DEFAULT 'individual' NOT
    # NULL` should never leave an existing row NULL -- but api/worker/
    # scheduler each run `alembic upgrade head` independently on every
    # Watchtower rolling deploy (see infra/user_data.sh), so this cleans up
    # after that possibility instead of assuming it can't happen. A NULL
    # account_type here would otherwise 500 the entire
    # GET /admin/dashboard/status response (DashboardStatusRow.account_type
    # is a required field), which is what actually breaks the Influencers
    # page -- not a missing value per row, a missing value ANYWHERE in the
    # list taking the whole response down.
    bind.execute(sa.text("UPDATE influencers SET account_type = 'individual' WHERE account_type IS NULL"))

    unlinked = bind.execute(
        sa.text("SELECT id, handle FROM influencers WHERE creator_id IS NULL ORDER BY handle")
    ).fetchall()

    # Case-insensitive name -> creator_id, seeded from creators that already
    # exist -- mirrors CreatorRepo.get_or_create_by_name's matching so two
    # unlinked influencers sharing the exact same handle (e.g. the same
    # person's Instagram and YouTube both literally "mrbeast") merge into
    # one Creator here too, same as an explicit creator_name link would.
    existing = bind.execute(sa.text("SELECT id, name FROM creators")).fetchall()
    creators_by_name = {row.name.lower(): row.id for row in existing}

    for influencer_id, handle in unlinked:
        name = handle.lstrip("@")
        creator_id = creators_by_name.get(name.lower())
        if creator_id is None:
            creator_id = bind.execute(
                sa.text(
                    "INSERT INTO creators (id, name, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :name, now(), now()) "
                    "RETURNING id"
                ),
                {"name": name},
            ).scalar_one()
            creators_by_name[name.lower()] = creator_id
        bind.execute(
            sa.text("UPDATE influencers SET creator_id = :creator_id WHERE id = :influencer_id"),
            {"creator_id": creator_id, "influencer_id": influencer_id},
        )


def downgrade() -> None:
    # Not reversible -- unlinking every influencer this touched would also
    # unlink any creator groups a user has since edited/merged further by
    # hand, which isn't recoverable from this migration alone.
    pass
