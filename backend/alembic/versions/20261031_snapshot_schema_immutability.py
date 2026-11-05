"""Enforce immutable snapshot membership after a run is frozen.

Revision ID: 20261031_snapshot_immutability
Revises: 20261030_research_v11
Create Date: 2026-10-31 11:27:00+00:00

Author: Damon Li
"""

from __future__ import annotations

from alembic import op

revision = "20261031_snapshot_immutability"
down_revision = "20261030_research_v11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Install row-locking guards for frozen runs and their membership rows."""
    op.execute(
        """
        CREATE FUNCTION research_guard_snapshot_member_insert()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE run_state text;
        BEGIN
            SELECT snapshot_state INTO run_state
              FROM research_run WHERE run_id = NEW.run_id FOR UPDATE;
            IF run_state IS DISTINCT FROM 'materialized' THEN
                RAISE EXCEPTION 'snapshot membership requires materialized run'
                    USING ERRCODE = '55000';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION research_guard_snapshot_member_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE run_key uuid;
                run_state text;
        BEGIN
            IF TG_OP = 'UPDATE' AND NEW.run_id <> OLD.run_id THEN
                -- Acquire all parent locks in stable order when rewriting membership.
                PERFORM run_id FROM research_run
                 WHERE run_id IN (OLD.run_id, NEW.run_id)
                 ORDER BY run_id FOR UPDATE;
                FOREACH run_key IN ARRAY ARRAY[OLD.run_id, NEW.run_id] LOOP
                    SELECT snapshot_state INTO run_state
                      FROM research_run WHERE run_id = run_key;
                    IF run_state = 'frozen' THEN
                        RAISE EXCEPTION 'snapshot membership is frozen'
                            USING ERRCODE = '55000';
                    END IF;
                END LOOP;
            ELSE
                run_key := OLD.run_id;
                SELECT snapshot_state INTO run_state
                  FROM research_run WHERE run_id = run_key FOR UPDATE;
                IF run_state = 'frozen' THEN
                    RAISE EXCEPTION 'snapshot membership is frozen'
                        USING ERRCODE = '55000';
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION research_guard_frozen_run_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.snapshot_state = 'frozen' AND
               (NEW.snapshot_state IS DISTINCT FROM OLD.snapshot_state OR
                NEW.snapshot_frozen_at IS DISTINCT FROM OLD.snapshot_frozen_at) THEN
                RAISE EXCEPTION 'frozen run snapshot state is immutable'
                    USING ERRCODE = '55000';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER research_snapshot_member_insert_guard "
        "BEFORE INSERT ON research_snapshot_member "
        "FOR EACH ROW EXECUTE FUNCTION research_guard_snapshot_member_insert()"
    )
    op.execute(
        "CREATE TRIGGER research_snapshot_member_mutation_guard "
        "BEFORE UPDATE OR DELETE ON research_snapshot_member "
        "FOR EACH ROW EXECUTE FUNCTION research_guard_snapshot_member_mutation()"
    )
    op.execute(
        "CREATE TRIGGER research_run_frozen_state_guard "
        "BEFORE UPDATE ON research_run "
        "FOR EACH ROW EXECUTE FUNCTION research_guard_frozen_run_update()"
    )


def downgrade() -> None:
    """Remove trigger code only; leave all research data and tables intact."""
    op.execute("DROP TRIGGER research_run_frozen_state_guard ON research_run")
    op.execute(
        "DROP TRIGGER research_snapshot_member_mutation_guard "
        "ON research_snapshot_member"
    )
    op.execute(
        "DROP TRIGGER research_snapshot_member_insert_guard ON research_snapshot_member"
    )
    op.execute("DROP FUNCTION research_guard_frozen_run_update()")
    op.execute("DROP FUNCTION research_guard_snapshot_member_mutation()")
    op.execute("DROP FUNCTION research_guard_snapshot_member_insert()")
