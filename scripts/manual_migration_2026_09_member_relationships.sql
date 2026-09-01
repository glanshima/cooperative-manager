-- MACT Cooperative Manager -- Member Relationship / Next-of-Kin
-- Controlled Remediation (2026-09).
--
-- Adds a single new table, member_relationships, plus its supporting
-- enum-backed columns, CHECK constraint, and partial unique index. No
-- existing table is modified -- purely additive, so this is safe to
-- run against the live database with zero impact on any pre-existing
-- row or endpoint until the corresponding backend code (which reads
-- and writes this table only) is also deployed. Per this project's
-- standing "migration ordering is not optional" lesson (see
-- PHASE1_IMPLEMENTATION_REPORT.md, Section N and the continuation
-- prompt's "Key learnings" list), run this BEFORE or IN THE SAME
-- deploy step as the backend code that references MemberRelationship
-- -- never after, since the API would otherwise 500 on any request
-- that reaches member_relationships.py before the table exists.
--
-- WHY A NEW TABLE, NOT A COLUMN ON members: see
-- backend/app/models.py's MemberRelationship docstring for the full
-- rationale (a generic, directed, typed relationship model rather than
-- a single next_of_kin_member_id FK on Member) -- summarized here as:
-- (1) the remediation prompt frames Next-of-Kin as the first of
-- potentially several member-to-member relationship types this
-- foundation needs to support, and (2) history must be retained when a
-- relationship changes or is removed (Financial-History-Protection-style
-- precedent applied to relationship history), which a single mutable FK
-- column cannot do on its own.
--
-- SAFE-MIGRATION PROCEDURE: this is a single CREATE TABLE plus its
-- indexes/constraints -- there is no existing data to migrate and
-- nothing pre-existing to violate, so no pre-flight data check is
-- needed. Verification queries are included at the bottom.

CREATE TABLE IF NOT EXISTS member_relationships (
    id UUID PRIMARY KEY,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    related_member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    relationship_type VARCHAR NOT NULL DEFAULT 'next_of_kin',
    conflict_of_interest BOOLEAN NOT NULL DEFAULT true,
    status VARCHAR NOT NULL DEFAULT 'active',
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    created_by_user_id UUID REFERENCES users(id),
    removed_at TIMESTAMP,
    removed_by_user_id UUID REFERENCES users(id),

    CONSTRAINT ck_member_relationships_no_self_reference CHECK (member_id != related_member_id),
    CONSTRAINT ck_member_relationships_type CHECK (relationship_type IN ('next_of_kin')),
    CONSTRAINT ck_member_relationships_status CHECK (status IN ('active', 'removed'))
);

CREATE INDEX IF NOT EXISTS ix_member_relationships_member_id ON member_relationships (member_id);
CREATE INDEX IF NOT EXISTS ix_member_relationships_related_member_id ON member_relationships (related_member_id);

-- At most one ACTIVE relationship of a given type per member_id (see
-- MemberRelationship's docstring: an inspection finding, not an
-- invented rule -- the pre-existing Member.next_of_kin* free-text
-- columns are a single set of fields, implying one Next of Kin per
-- member has always been this cooperative's model). Partial (WHERE
-- status = 'active') so a REMOVED historical row never blocks setting
-- a new active one.
CREATE UNIQUE INDEX IF NOT EXISTS ux_member_relationships_one_active_per_type
    ON member_relationships (member_id, relationship_type)
    WHERE status = 'active';

-- ---------------------------------------------------------------------
-- Verification
-- ---------------------------------------------------------------------
-- \d member_relationships
-- -- expect the table, both CHECK constraints, both plain indexes, and
-- -- the partial unique index all present.
--
-- SELECT count(*) FROM member_relationships;
-- -- expect 0 immediately after this migration (nothing pre-existing
-- -- is auto-converted into a relationship row -- see the Phase 1
-- -- report's "Existing Data" finding for why).
