SELECT
  q.customer_id,
  c.phone_number AS phone,
  MAX(c.first_name) AS first_name,         -- take any non-null name
  COUNT(*) FILTER (
    WHERE q.win_date IS NOT NULL
      AND q.region_id = 2
  ) AS scans,
  COUNT(*) FILTER (
    WHERE q.win_date IS NOT NULL
      AND q.prize_id IS NOT NULL
      AND q.region_id = 2
      AND q.is_win_received = FALSE
  ) AS pending_cnt,
  MAX(
    CASE
      WHEN q.win_date IS NOT NULL
       AND q.prize_id IS NOT NULL
       AND q.region_id = 2
      THEN q.win_date
    END
  ) AS last_prize_at           -- last prize date in region 2
FROM public.qr_code AS q
LEFT JOIN public.customer AS c
  ON c.id = q.customer_id
GROUP BY q.customer_id, c.phone_number
HAVING
  -- есть хотя бы один реальный приз в регионе 2
  COUNT(*) FILTER (
    WHERE q.win_date IS NOT NULL
      AND q.prize_id IS NOT NULL
      AND q.region_id = 2
  ) > 0
  AND
  -- ни одного полученного приза в регионе 2
  COUNT(*) FILTER (
    WHERE q.win_date IS NOT NULL
      AND q.prize_id IS NOT NULL
      AND q.region_id = 2
      AND q.is_win_received = TRUE
  ) = 0
  AND
  -- последний реальный приз в регионе 2 был более 15 дней назад
  MAX(
    CASE
      WHEN q.win_date IS NOT NULL
       AND q.prize_id IS NOT NULL
       AND q.region_id = 2
      THEN q.win_date
    END
  ) < CURRENT_DATE - INTERVAL '15 days'
ORDER BY pending_cnt DESC, q.customer_id;
