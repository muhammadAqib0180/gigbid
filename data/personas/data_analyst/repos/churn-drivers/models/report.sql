select date_trunc('week', order_date) as week, sum(revenue) as revenue
from {{ ref("fct_orders") }}
group by 1
