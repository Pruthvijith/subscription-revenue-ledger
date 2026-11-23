select * from {{ ref('fct_mrr_movements') }}
where opening_cents + starts_cents + expansion_cents - contraction_cents - churn_cents <> closing_cents
