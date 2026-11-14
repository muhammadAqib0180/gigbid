CREATE INDEX CONCURRENTLY idx_txn_account_date ON transactions (account_id, booked_at);
