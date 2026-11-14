const token = jwt.sign({ sub: partnerId }, SECRET, { expiresIn: "15m" });
