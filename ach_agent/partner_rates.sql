-- ACH return counts by partner program: trailing 60 days plus today's returns.
-- Python turns these counts into rates and compares them with Nacha's limits.
-- In production this would run against the returns data warehouse.

SELECT
    p.partner,
    p.ach_debits_60d                                                                   AS debits,
    p.unauthorized_returns_60d   + COALESCE(SUM(t.nacha_rate = 'unauthorized'), 0)     AS unauthorized,
    p.administrative_returns_60d + COALESCE(SUM(t.nacha_rate = 'administrative'), 0)   AS administrative,
    p.total_returns_60d          + COUNT(t.return_id)                                  AS total
FROM partners AS p
LEFT JOIN todays_returns AS t
       ON t.partner = p.partner
GROUP BY p.partner
ORDER BY p.partner;
