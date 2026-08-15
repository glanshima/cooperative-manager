-- Run this once in Neon's SQL Editor before redeploying the backend.
-- Round 1 of the "flagged items" batch only adds one new column.

ALTER TABLE loan_types
    ADD COLUMN IF NOT EXISTS description VARCHAR;
