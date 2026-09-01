-- MACT Cooperative Manager -- Admin Identity Governance Controlled
-- Remediation (Governance Objective 1: Role-Based Member Link
-- Requirement).
--
-- Adds a single Boolean column to the existing `roles` table. No other
-- table is touched. Purely additive: every existing role defaults to
-- `false`, so no currently-active role assignment becomes invalid as a
-- result of this migration -- enforcement only applies going forward,
-- at role-ASSIGNMENT time and at unlink time (see
-- backend/app/routers/admin_users.py), never retroactively.
--
-- Cooperative administrators must explicitly opt a role INTO requiring
-- Member linkage afterward (via PUT /api/roles/{id} with
-- requires_member_link=true, or the Roles UI) -- e.g. for Treasurer,
-- President, Secretary, or other EXCO/office roles that represent a
-- cooperative member. Nothing in this migration itself marks any role
-- that way; role names are never hard-coded here or in application
-- code, per the remediation's explicit "do not hard-code role names"
-- instruction.
--
-- SAFE-MIGRATION PROCEDURE: this is a single, low-risk ADD COLUMN with
-- a NOT NULL + DEFAULT, safe to run directly (no pre-flight data check
-- needed, since a new column with a default cannot violate existing
-- rows). Verification query included at the bottom.

ALTER TABLE roles
    ADD COLUMN IF NOT EXISTS requires_member_link BOOLEAN NOT NULL DEFAULT false;

-- ---------------------------------------------------------------------
-- Verification
-- ---------------------------------------------------------------------
-- SELECT name, requires_member_link FROM roles ORDER BY name;
-- -- expect every existing role to show requires_member_link = false
-- -- until an administrator explicitly changes a specific role.
