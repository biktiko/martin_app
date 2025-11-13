-- Пользователи региона 2, у которых НИ ОДИН реальный приз в регионе 2 не был получен
SELECT
  Distinct(q.customer_id),
  Distinct(c.phone_number) AS phone74),
  COUNT(*) FILTER (
    WHERE q.win_date IS NOT NULL
      AND q.prize_id IS NOT NULL
      AND q.region_id = 2
      AND q.is_win_received = FALSE
  ) AS pending_cnt,
  COUNT(*) FILTER (
    WHERE q.win_date IS NOT NULL
      AND q.prize_id IS NOT NULL
      AND q.region_id = 2
      AND q.is_win_received = TRUE
  ) AS received_cnt,
  MAX(
    CASE
      WHEN q.win_date IS NOT NULL
       AND q.prize_id IS NOT NULL
       AND q.region_id = 2
       AND q.is_win_received = TRUE
      THEN q.win_date
    END
  ) AS last_received_at
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
  -- и ни одного полученного в регионе 2
  COUNT(*) FILTER (
    WHERE q.win_date IS NOT NULL
      AND q.prize_id IS NOT NULL
      AND q.region_id = 2
      AND q.is_win_received = TRUE
  ) = 0
ORDER BY pending_cnt DESC, q.customer_id;