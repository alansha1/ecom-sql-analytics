-- ============================================================
-- E-Commerce Customer Analytics — SQL Query Library
-- Alan Sha | github.com/alansha1
-- ============================================================
-- All queries run against the ecommerce.db SQLite database.
-- Completed orders only (status = 'Completed') unless noted.
-- ============================================================


-- ── Q1: Monthly Revenue Trend with MoM Growth ─────────────────────────────
-- Window function: LAG to compare each month to the previous one.
WITH monthly AS (
    SELECT
        strftime('%Y-%m', o.order_date)          AS month,
        ROUND(SUM(oi.quantity * oi.unit_price),2) AS revenue
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.status = 'Completed'
    GROUP BY month
    ORDER BY month
)
SELECT
    month,
    revenue,
    LAG(revenue) OVER (ORDER BY month)                                          AS prev_month_revenue,
    ROUND(
        (revenue - LAG(revenue) OVER (ORDER BY month))
        / LAG(revenue) OVER (ORDER BY month) * 100, 1
    )                                                                            AS mom_growth_pct
FROM monthly;


-- ── Q2: Cumulative (Running Total) Revenue ────────────────────────────────
-- Window function: SUM OVER to build a running total across months.
WITH monthly AS (
    SELECT
        strftime('%Y-%m', o.order_date)          AS month,
        ROUND(SUM(oi.quantity * oi.unit_price),2) AS revenue
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.status = 'Completed'
    GROUP BY month
    ORDER BY month
)
SELECT
    month,
    revenue,
    ROUND(SUM(revenue) OVER (ORDER BY month), 2) AS cumulative_revenue
FROM monthly;


-- ── Q3: Customer Lifetime Value (CLV) by Segment ─────────────────────────
-- Total spend per customer, averaged by segment; ranks segments.
WITH customer_spend AS (
    SELECT
        c.customer_id,
        c.segment,
        ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_spend,
        COUNT(DISTINCT o.order_id)                  AS orders_placed
    FROM customers c
    JOIN orders o     ON c.customer_id = o.customer_id
    JOIN order_items oi ON o.order_id  = oi.order_id
    WHERE o.status = 'Completed'
    GROUP BY c.customer_id, c.segment
)
SELECT
    segment,
    COUNT(*)                                    AS customers,
    ROUND(AVG(total_spend), 2)                  AS avg_clv,
    ROUND(AVG(orders_placed), 1)                AS avg_orders,
    ROUND(SUM(total_spend), 2)                  AS total_segment_revenue,
    RANK() OVER (ORDER BY AVG(total_spend) DESC) AS clv_rank
FROM customer_spend
GROUP BY segment
ORDER BY avg_clv DESC;


-- ── Q4: Top 20 Customers by Lifetime Value ────────────────────────────────
-- RANK window function to rank every customer; filter top 20.
WITH ranked AS (
    SELECT
        c.customer_id,
        c.first_name || ' ' || c.last_name AS customer_name,
        c.segment,
        c.region,
        ROUND(SUM(oi.quantity * oi.unit_price), 2) AS lifetime_value,
        COUNT(DISTINCT o.order_id)                  AS total_orders,
        RANK() OVER (ORDER BY SUM(oi.quantity * oi.unit_price) DESC) AS rnk
    FROM customers c
    JOIN orders o      ON c.customer_id = o.customer_id
    JOIN order_items oi ON o.order_id   = oi.order_id
    WHERE o.status = 'Completed'
    GROUP BY c.customer_id
)
SELECT * FROM ranked WHERE rnk <= 20;


-- ── Q5: Pareto Analysis — Do Top 20% of Customers Drive 80% of Revenue? ──
-- Subquery + CTE to test the 80/20 rule on this dataset.
WITH customer_revenue AS (
    SELECT
        c.customer_id,
        ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
    FROM customers c
    JOIN orders o      ON c.customer_id = o.customer_id
    JOIN order_items oi ON o.order_id   = oi.order_id
    WHERE o.status = 'Completed'
    GROUP BY c.customer_id
),
ranked AS (
    SELECT
        customer_id,
        revenue,
        ROW_NUMBER() OVER (ORDER BY revenue DESC) AS row_num,
        COUNT(*) OVER ()                           AS total_customers,
        SUM(revenue) OVER ()                       AS total_revenue
    FROM customer_revenue
)
SELECT
    CASE
        WHEN row_num <= CAST(total_customers * 0.20 AS INT) THEN 'Top 20%'
        ELSE 'Bottom 80%'
    END                                           AS customer_group,
    COUNT(*)                                      AS customer_count,
    ROUND(SUM(revenue), 2)                        AS group_revenue,
    ROUND(SUM(revenue) / MAX(total_revenue) * 100, 1) AS pct_of_total_revenue
FROM ranked
GROUP BY customer_group;


-- ── Q6: Customer Cohort Retention (Acquisition Month) ────────────────────
-- For each acquisition cohort, counts how many customers placed ≥1 order
-- in their first month vs subsequent months. Shows retention drop-off.
WITH cohorts AS (
    SELECT
        c.customer_id,
        strftime('%Y-%m', c.acquired_date)   AS cohort_month,
        strftime('%Y-%m', o.order_date)      AS order_month
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    WHERE o.status = 'Completed'
),
cohort_size AS (
    SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_customers
    FROM cohorts
    GROUP BY cohort_month
),
activity AS (
    SELECT
        cohort_month,
        order_month,
        COUNT(DISTINCT customer_id) AS active_customers
    FROM cohorts
    GROUP BY cohort_month, order_month
)
SELECT
    a.cohort_month,
    a.order_month,
    cs.cohort_customers,
    a.active_customers,
    ROUND(a.active_customers * 100.0 / cs.cohort_customers, 1) AS retention_pct
FROM activity a
JOIN cohort_size cs ON a.cohort_month = cs.cohort_month
ORDER BY a.cohort_month, a.order_month;


-- ── Q7: Product Performance — Revenue, Units Sold, Ranking ───────────────
SELECT
    p.product_id,
    p.name                                          AS product_name,
    p.category,
    SUM(oi.quantity)                                AS units_sold,
    ROUND(SUM(oi.quantity * oi.unit_price), 2)      AS total_revenue,
    ROUND(AVG(oi.unit_price), 2)                    AS avg_selling_price,
    RANK() OVER (ORDER BY SUM(oi.quantity * oi.unit_price) DESC) AS revenue_rank
FROM products p
JOIN order_items oi ON p.product_id = oi.product_id
JOIN orders o       ON oi.order_id  = o.order_id
WHERE o.status = 'Completed'
GROUP BY p.product_id
ORDER BY total_revenue DESC;


-- ── Q8: Repeat vs One-Time Buyers ────────────────────────────────────────
-- Segments the customer base by purchase frequency.
WITH order_counts AS (
    SELECT
        c.customer_id,
        c.segment,
        COUNT(DISTINCT o.order_id) AS order_count
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    WHERE o.status = 'Completed'
    GROUP BY c.customer_id
)
SELECT
    CASE
        WHEN order_count = 1 THEN '1 — One-time buyer'
        WHEN order_count BETWEEN 2 AND 3 THEN '2-3 — Occasional'
        WHEN order_count BETWEEN 4 AND 6 THEN '4-6 — Regular'
        ELSE '7+ — Loyal'
    END                          AS buyer_tier,
    COUNT(*)                     AS customers,
    ROUND(AVG(order_count), 1)   AS avg_orders
FROM order_counts
GROUP BY buyer_tier
ORDER BY buyer_tier;


-- ── Q9: Churn Risk — Customers Inactive for 90+ Days ─────────────────────
-- Flags customers whose last order was more than 90 days ago.
WITH last_order AS (
    SELECT
        c.customer_id,
        c.first_name || ' ' || c.last_name AS customer_name,
        c.segment,
        c.region,
        MAX(o.order_date)                   AS last_order_date,
        COUNT(DISTINCT o.order_id)          AS total_orders,
        ROUND(SUM(oi.quantity * oi.unit_price), 2) AS lifetime_value
    FROM customers c
    JOIN orders o      ON c.customer_id = o.customer_id
    JOIN order_items oi ON o.order_id   = oi.order_id
    WHERE o.status = 'Completed'
    GROUP BY c.customer_id
)
SELECT
    customer_id,
    customer_name,
    segment,
    region,
    last_order_date,
    total_orders,
    lifetime_value,
    CAST(julianday('2025-01-01') - julianday(last_order_date) AS INT) AS days_since_order,
    CASE
        WHEN julianday('2025-01-01') - julianday(last_order_date) > 180 THEN 'High Risk'
        WHEN julianday('2025-01-01') - julianday(last_order_date) > 90  THEN 'Medium Risk'
        ELSE 'Active'
    END AS churn_risk
FROM last_order
WHERE julianday('2025-01-01') - julianday(last_order_date) > 90
ORDER BY days_since_order DESC;


-- ── Q10: Revenue by Acquisition Channel ──────────────────────────────────
-- Which marketing channel brings in the highest-value customers?
SELECT
    c.channel,
    COUNT(DISTINCT c.customer_id)               AS customers_acquired,
    COUNT(DISTINCT o.order_id)                  AS total_orders,
    ROUND(SUM(oi.quantity * oi.unit_price), 2)  AS total_revenue,
    ROUND(SUM(oi.quantity * oi.unit_price)
          / COUNT(DISTINCT c.customer_id), 2)   AS revenue_per_customer,
    RANK() OVER (
        ORDER BY SUM(oi.quantity * oi.unit_price) / COUNT(DISTINCT c.customer_id) DESC
    )                                            AS value_rank
FROM customers c
JOIN orders o      ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id   = oi.order_id
WHERE o.status = 'Completed'
GROUP BY c.channel
ORDER BY revenue_per_customer DESC;


-- ── Q11: Average Order Value (AOV) Trend by Month ────────────────────────
SELECT
    strftime('%Y-%m', o.order_date)                        AS month,
    COUNT(DISTINCT o.order_id)                             AS orders,
    ROUND(SUM(oi.quantity * oi.unit_price), 2)             AS revenue,
    ROUND(SUM(oi.quantity * oi.unit_price)
          / COUNT(DISTINCT o.order_id), 2)                 AS avg_order_value,
    ROUND(
        AVG(SUM(oi.quantity * oi.unit_price) / COUNT(DISTINCT o.order_id))
        OVER (ORDER BY strftime('%Y-%m', o.order_date) ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),
        2
    )                                                       AS rolling_3m_aov
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'Completed'
GROUP BY month
ORDER BY month;


-- ── Q12: Category Revenue Mix with Running Share ──────────────────────────
-- What percentage of revenue each product category contributes,
-- with a running cumulative share (useful for ABC analysis).
WITH cat_rev AS (
    SELECT
        p.category,
        ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
    FROM products p
    JOIN order_items oi ON p.product_id = oi.product_id
    JOIN orders o       ON oi.order_id  = o.order_id
    WHERE o.status = 'Completed'
    GROUP BY p.category
)
SELECT
    category,
    revenue,
    ROUND(revenue / SUM(revenue) OVER () * 100, 1)          AS pct_of_total,
    ROUND(SUM(revenue) OVER (ORDER BY revenue DESC)
          / SUM(revenue) OVER () * 100, 1)                   AS cumulative_pct
FROM cat_rev
ORDER BY revenue DESC;
