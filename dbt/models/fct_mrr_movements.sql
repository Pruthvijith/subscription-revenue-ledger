with prior_balance as (
    select account, month_end, cents,
           coalesce(lag(cents) over (partition by account order by month_end), 0) as opening
    from {{ ref('account_month_input') }}
)
select month_end, sum(opening) as opening_cents,
       sum(case when opening = 0 then cents else 0 end) as starts_cents,
       sum(case when opening > 0 and cents > opening then cents-opening else 0 end) as expansion_cents,
       sum(case when cents > 0 and cents < opening then opening-cents else 0 end) as contraction_cents,
       sum(case when cents = 0 then opening else 0 end) as churn_cents, sum(cents) as closing_cents
from prior_balance
group by month_end
