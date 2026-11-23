with target_only as (
    select * from {{ ref('fct_mrr_movements') }} except select * from {{ ref('bridge_input') }}
), source_only as (
    select * from {{ ref('bridge_input') }} except select * from {{ ref('fct_mrr_movements') }}
)
select * from target_only union all select * from source_only
