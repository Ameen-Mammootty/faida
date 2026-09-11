-- 0021: conversion yields on a recipe component (plan.md §8 M12, WP-119, D13).
-- Appended per contract C7; the manager squashes periodically (plan.md §4 policy).
--
-- APPLY THIS BEFORE WP-119 MERGES TO MASTER. The column is nullable with no
-- default, so the build on master today does not select it and every existing
-- recipe keeps behaving byte-identically once it is there; but WP-119's build
-- selects `usable_share` in every recipe read, so deploying it first fails
-- those reads until the column exists. Migration first, then deploy.
-- Docs/apply_wp119_migration.sql is the paste-ready copy with a pre-flight.
--
-- WHY. A recipe is written for costing, so it says what goes in the pot: 500 g
-- of chicken means 500 g of chicken *in the curry*. What the storeroom issued
-- was more than that - trim, bone, peel, a cooking loss - and M12 compares a
-- recipe's quantities against what the invoices say was bought. Without a
-- share those two numbers describe different things and their difference is
-- noise, so the comparison would report a shortfall on every dish that loses
-- anything to preparation (the M12 engineering review's fourth finding, D13).
--
-- `usable_share` is the share of what is *bought* that reaches the pot:
-- chicken at 0.85 means 500 g in the pot cost 588 g off the shelf. The plate
-- and M12's usage divide by the same number, so cost and quantity always
-- describe the purchased amount and can never drift apart.
--
-- NULL MEANS AS-PURCHASED - the M6 convention every recipe already on file
-- was written under, kept exactly. There is no default and no backfill: a
-- share is a fact about a kitchen that only a person can state, and a guessed
-- 1.0000 written across every row would be indistinguishable from a stated
-- one afterwards.
--
-- The bounds are the constraint and not just the door: zero would divide the
-- plate by nothing, a negative would subtract cost, and above 1 would say the
-- pot receives more than the shelf issued. Four decimals matches `qty` above
-- it - 0.8500 is 85%, and a share is never more precise than a scale.

alter table recipe_components
  add column usable_share numeric(5,4) null
    check (usable_share > 0 and usable_share <= 1);

comment on column recipe_components.usable_share is
  'the share of what is bought that reaches the pot (M12 WP-119, D13): 0.85 '
  'means 500 g in the curry cost 588 g off the shelf. Null means the quantity '
  'is already as-purchased - the M6 convention, and what every recipe written '
  'before this column says. The plate and M12''s usage divide by it alike.';
