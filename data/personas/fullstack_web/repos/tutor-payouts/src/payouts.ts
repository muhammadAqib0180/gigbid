await stripe.transfers.create({ amount, destination }, { idempotencyKey: `payout-${sessionId}` });
