{# Use schema names exactly as configured (staging, analytics) instead of dbt's default
   "<target>_<custom>" prefixing, so Power BI always connects to `analytics`. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
