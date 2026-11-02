{# Every (scoped) row satisfies `expression`; used for range checks and fan-out guards. #}
{% test expression_is_true(model, expression) %}
select * from {{ model }} where not ({{ expression }})
{% endtest %}
