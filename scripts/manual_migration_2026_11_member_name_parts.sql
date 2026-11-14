-- Member names captured as parts (2026-11-14)
--
-- The registration form now captures Last Name, First Name and Other
-- Name(s) separately, and the stored `name` is the printed form
-- "Last, First Other(s)". This migration adds the three part columns and
-- rewrites existing free-text names into that printed order.
--
-- ADDITIVE + IDEMPOTENT:
--   * the columns are only added when missing;
--   * the backfill only touches rows where all three parts are still NULL,
--     so re-running the file (or a name captured after this change) is a
--     no-op.
--
-- Parsing rule for pre-split rows:
--   * with a comma: everything before it is the family name, the first
--     word after it the given name, the rest other names;
--   * without: the last word is the family name, the first word the given
--     name, anything between them other names;
--   * a single-word name keeps its text untouched (there is no given name
--     to split off).

ALTER TABLE members ADD COLUMN IF NOT EXISTS first_name VARCHAR;
ALTER TABLE members ADD COLUMN IF NOT EXISTS last_name VARCHAR;
ALTER TABLE members ADD COLUMN IF NOT EXISTS other_names VARCHAR;

DO $$
DECLARE
    rec RECORD;
    clean TEXT;
    family TEXT;
    given_name TEXT;
    others TEXT;
    rest TEXT;
    tokens TEXT[];
    n INTEGER;
BEGIN
    FOR rec IN
        SELECT id, name
        FROM members
        WHERE name IS NOT NULL
          AND btrim(name) <> ''
          AND first_name IS NULL
          AND last_name IS NULL
          AND other_names IS NULL
    LOOP
        clean := btrim(rec.name);
        family := NULL;
        given_name := NULL;
        others := NULL;

        IF position(',' IN clean) > 0 THEN
            family := btrim(regexp_replace(clean, ',.*$', ''));
            rest := btrim(regexp_replace(clean, '^[^,]*,', ''));
            IF rest <> '' THEN
                tokens := regexp_split_to_array(rest, '\s+');
                given_name := tokens[1];
                n := array_length(tokens, 1);
                IF n > 1 THEN
                    others := array_to_string(tokens[2:n], ' ');
                END IF;
            END IF;
        ELSE
            tokens := regexp_split_to_array(clean, '\s+');
            n := array_length(tokens, 1);
            family := tokens[n];
            IF n >= 2 THEN
                given_name := tokens[1];
            END IF;
            IF n > 2 THEN
                others := array_to_string(tokens[2:n - 1], ' ');
            END IF;
        END IF;

        UPDATE members
           SET last_name = NULLIF(family, ''),
               first_name = NULLIF(given_name, ''),
               other_names = NULLIF(others, ''),
               name = CASE
                          WHEN NULLIF(family, '') IS NULL OR NULLIF(given_name, '') IS NULL
                              THEN clean
                          WHEN NULLIF(others, '') IS NULL
                              THEN family || ', ' || given_name
                          ELSE family || ', ' || given_name || ' ' || others
                      END
         WHERE id = rec.id;
    END LOOP;
END $$;
