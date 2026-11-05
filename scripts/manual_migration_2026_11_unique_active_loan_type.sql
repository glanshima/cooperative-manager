-- MACT Cooperative Manager -- one ACTIVE loan per member per loan type.
--
-- Business rule: a member cannot hold two active loans of the same loan
-- type at the same time (they may hold different types concurrently).
--
-- The DO block below refuses to run if existing rows already violate the
-- rule, naming the member and loans so they can be resolved deliberately
-- instead of failing later with an opaque unique-violation on a
-- disbursement.

DO $$
DECLARE
    conflict_member uuid;
    conflict_type uuid;
    conflict_count bigint;
    conflict_ids text;
BEGIN
    SELECT member_id, loan_type_id, count(*)
      INTO conflict_member, conflict_type, conflict_count
      FROM loans
     WHERE status = 'active'
     GROUP BY member_id, loan_type_id
    HAVING count(*) > 1
     LIMIT 1;

    IF conflict_member IS NOT NULL THEN
        SELECT string_agg(id::text, ', ')
          INTO conflict_ids
          FROM loans
         WHERE member_id = conflict_member
           AND loan_type_id = conflict_type
           AND status = 'active';

        RAISE EXCEPTION
            'Cannot enforce one active loan per loan type: member % has % active loans of type % (loan IDs: %). Close the extra loans first.',
            conflict_member, conflict_count, conflict_type, conflict_ids;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_loans_member_loan_type_active
    ON loans (member_id, loan_type_id)
    WHERE status = 'active';
