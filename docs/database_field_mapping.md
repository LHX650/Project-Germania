# Database Field Mapping

This document maps every field from `docs/data_dictionary.md` to the Phase 4
database ER design. It is a design mapping only. No database, ORM model,
migration, SQL file, or data has been created.

Allowed `storage_status` values:

- `stored`
- `derived`
- `metadata`
- `not_applicable`
- `deferred`

| data_dictionary_field | Chinese meaning | target_table | target_column | storage_status | rationale |
| --- | --- | --- | --- | --- | --- |
| `record_id` | 记录唯一标识 | all physical entity tables | table-specific primary key | stored | Implemented as table-specific identifiers such as `vehicle_id`, `marketplace_listing_id`, or observation IDs. |
| `record_type` | 记录类型 | `collection_batches`; `data_quality_issues` | `record_type`; `entity_type` | stored | Batch and issue routing need a record/entity type. |
| `batch_id` | 批次标识 | `collection_batches` | `batch_id` | stored | Stable business key for import or future collection batches. |
| `region` | 业务分析区域 | `registration_observations` | `region` | stored | Registration analysis needs explicit business geography. |
| `country_code` | 国家代码 | `data_sources`; `marketplace_listings`; `registration_observations` | `country_code` | stored | Source and geography fields keep country context. |
| `state` | 州或省级地区 | `marketplace_listings`; `registration_observations` | `state` | stored | Listing geography and registration scope support regional analysis. |
| `city` | 城市 | `marketplace_listings` | `city` | stored | Marketplace and dealer data use city filters. |
| `postal_code` | 邮政编码 | `marketplace_listings` | `postal_code` | stored | Stored as text to preserve leading zeros. |
| `source_id` | 数据源标识 | `data_sources` | `source_id` | stored | Stable configured business key. |
| `source_name` | 数据源名称 | `data_sources` | `source_name` | stored | Human-readable source name. |
| `source_type` | 数据源类型 | `data_sources` | `source_type` | stored | Drives source authority and compliance behavior. |
| `source_url` | 具体页面或文件来源 | observation and listing tables | `source_url` | stored | Exact source traceability is stored with source-derived records. |
| `source_listing_id` | 来源平台挂牌ID | `marketplace_listings` | `source_listing_id` | stored | Stable platform listing identity. |
| `source_record_id` | 来源记录ID | `official_price_observations`; `registration_observations` | `source_record_id` | stored | Supports official/import row traceability when available. |
| `source_file_name` | 来源文件名 | `collection_batches`; `registration_observations` | `source_file_name` | stored | Links parsed records to source files. |
| `source_page_number` | 来源页码 | `registration_observations` | `source_page_number` | stored | Supports PDF/table extraction audit. |
| `canonical_brand` | 标准品牌 | `brands`; `registration_observations` | `canonical_brand` | stored | Master brand name and resolved registration context. |
| `canonical_model` | 标准车型 | `vehicles`; `registration_observations` | `canonical_model` | stored | Master model name and resolved registration context. |
| `raw_brand` | 原始品牌文本 | `official_price_observations`; `marketplace_listings`; `registration_observations` | `raw_brand` | stored | Raw source text is preserved outside master tables. |
| `raw_model` | 原始车型文本 | `official_price_observations`; `marketplace_listings`; `registration_observations` | `raw_model` | stored | Raw source text supports future remapping. |
| `manufacturer` | 制造商 | `brands` | `manufacturer` | stored | Manufacturer belongs to brand/master data. |
| `country_of_origin` | 品牌或车型来源国 | `brands` | `country_of_origin` | stored | Strategic segmentation field. |
| `vehicle_segment` | 车型级别 | `vehicles` | `vehicle_segment` | stored | Canonical vehicle segmentation. |
| `body_type` | 车身形式 | `vehicles` | `body_type` | stored | Canonical body-style dimension. |
| `powertrain` | 动力系统 | `vehicles`; `vehicle_variants` | `default_powertrain`; `powertrain` | stored | Vehicle stores default value; variants store specific value. |
| `fuel_type` | 燃料类型 | `vehicle_variants` | `fuel_type` | stored | Variant-specific technical detail. |
| `model_year` | 车型年款 | `vehicle_variants`; `marketplace_listings` | `model_year` | stored | Variant and listing records may each provide model-year context. |
| `generation` | 代际 | `vehicle_variants` | `generation` | stored | Variant-level model generation. |
| `trim_name` | 配置版本 | `vehicle_variants` | `trim_name` | stored | Kept distinct from variant and edition. |
| `variant_name` | 车型变体 | `vehicle_variants` | `variant_name` | stored | Kept distinct from trim and edition. |
| `edition_name` | 特别版名称 | `vehicle_variants` | `edition_name` | stored | Special-edition label. |
| `drivetrain` | 驱动形式 | `vehicle_variants` | `drivetrain` | stored | Variant-level technical detail. |
| `transmission` | 变速箱 | `vehicle_variants` | `transmission` | stored | Variant-level technical detail. |
| `battery_capacity_kwh` | 电池容量 | `vehicle_variants` | `battery_capacity_kwh` | stored | Decimal semantics; non-negative. |
| `engine_power_kw` | 功率千瓦 | `vehicle_variants` | `engine_power_kw` | stored | Decimal semantics; non-negative. |
| `engine_power_ps` | 公制马力 | `vehicle_variants` | `engine_power_ps` | stored | Decimal semantics; non-negative. |
| `condition` | 车辆状态 | `marketplace_listings` | `condition` | stored | Listing identity-level condition. |
| `first_registration_date` | 首次注册日期 | `marketplace_listings` | `first_registration_date` | stored | Used-car feature, separate from model year. |
| `mileage_km` | 里程公里数 | `marketplace_listings`; `marketplace_listing_observations` | `mileage_km` | stored | Stable and observed listing mileage can both be preserved. |
| `owner_count` | 车主数量 | `marketplace_listings` | `owner_count` | stored | Listing feature; non-negative. |
| `seller_type` | 卖家类型 | `marketplace_listings` | `seller_type` | stored | Listing channel classification. |
| `dealer_name` | 经销商名称 | `marketplace_listings` | `dealer_name` | stored | Dealer display name when permitted. |
| `registration_count` | 新车注册量 | `registration_observations` | `registration_count` | stored | Preferred German sales-trend proxy. |
| `registration_period` | 注册统计周期 | `registration_observations` | `registration_period` | stored | Period string such as `YYYY-MM` or `YYYY-Qn`. |
| `registration_scope` | 注册统计范围 | `registration_observations` | `registration_scope` | stored | Explicit geography such as Germany, state, or EU. |
| `sales_metric_type` | 销量口径类型 | `registration_observations` | `sales_metric_type` | stored | Prevents mixing registrations, deliveries, retail, and wholesale metrics. |
| `sales_value` | 其他销量口径数值 | `registration_observations` | `sales_value` | stored | Stored only with explicit `sales_metric_type`. |
| `official_price` | 官方指导价 | `official_price_observations` | `official_price` | stored | Official price is separated from listing and transaction prices. |
| `listed_price` | 市场挂牌价 | `marketplace_listing_observations` | `listed_price` | stored | Asking price history is stored separately from listing identity. |
| `estimated_transaction_price` | 估算成交价 | `estimated_transaction_prices` | `estimated_transaction_price` | stored | Derived estimate table; not confirmed transaction data. |
| `transaction_price` | 真实成交价 | none | none | deferred | No reliable confirmed transaction source exists; do not store fabricated values. |
| `discount_amount` | 折扣绝对金额 | analytics/query output | calculated from official, listed, or estimated price basis | derived | Must record calculation basis when materialized later. |
| `discount_rate` | 折扣率 | analytics/query output | calculated from documented denominator | derived | Not stored until a clear metric definition is implemented. |
| `price_min` | 价格下限 | analytics/query output | aggregate over relevant price table | derived | Range value depends on query scope and price type. |
| `price_max` | 价格上限 | analytics/query output | aggregate over relevant price table | derived | Range value depends on query scope and price type. |
| `price_includes_vat` | 价格是否含增值税 | `official_price_observations`; `marketplace_listing_observations` | `price_includes_vat` | stored | Needed for price comparability. |
| `price_status` | 价格状态 | table identity / analytics output | inferred from source table | derived | `official_price_observations`, `marketplace_listing_observations`, and `estimated_transaction_prices` imply status. |
| `currency` | 原始价格货币 | price and estimate tables | `currency` | stored | Must be stored with monetary values. |
| `exchange_rate` | 汇率 | `exchange_rate_observations` | `exchange_rate` | stored | Authoritative rate value with direction. |
| `exchange_rate_base_currency` | 汇率基准货币 | `exchange_rate_observations` | `base_currency` | stored | Column name shortened while preserving meaning. |
| `exchange_rate_quote_currency` | 汇率报价货币 | `exchange_rate_observations` | `quote_currency` | stored | Column name shortened while preserving meaning. |
| `exchange_rate_date` | 汇率适用日期 | `exchange_rate_observations` | `exchange_rate_date` | stored | Historical conversion date. |
| `price_eur` | 欧元换算价格 | query/export output | calculated from price, currency, and FX observation | derived | Not stored by default to avoid stale materialized conversions. |
| `observed_at` | 来源观察时间 | observation tables | `observed_at` | stored | Source observation timestamp. |
| `collected_at` | 系统采集时间 | observation tables | `collected_at` | stored | System collection timestamp when available. |
| `valid_date` | 业务有效日期 | official, registration, FX, estimate tables | `valid_date` / `exchange_rate_date` | stored | Business date is separate from collection time. |
| `effective_from` | 生效开始时间 | `vehicle_variants`; `official_price_observations` | `effective_from` | stored | Supports validity windows. |
| `effective_to` | 生效结束时间 | `vehicle_variants`; `official_price_observations` | `effective_to` | stored | Supports validity windows. |
| `first_seen_at` | 首次发现时间 | `marketplace_listings` | `first_seen_at` | stored | Listing lifecycle tracking. |
| `last_seen_at` | 最后发现时间 | `marketplace_listings` | `last_seen_at` | stored | Listing lifecycle tracking. |
| `created_at` | 记录创建时间 | all primary tables | `created_at` | stored | Audit timestamp. |
| `updated_at` | 记录更新时间 | mutable primary tables | `updated_at` | stored | Audit timestamp for mutable rows. |
| `data_quality_status` | 数据质量状态 | observation tables | `data_quality_status` | stored | High-level validation result. |
| `validation_status` | 校验状态 | observation tables; `collection_batches` | `validation_status`; `status` | stored | Validation or processing state. |
| `completeness_score` | 完整性评分 | analytics/quality output | calculated quality metric | derived | Score depends on dataset-level validation rules. |
| `confidence_level` | 置信度等级 | `estimated_transaction_prices`; quality outputs | `confidence_level` | stored | Required for estimates and uncertain matches. |
| `duplicate_key` | 去重键 | `marketplace_listing_observations` | `duplicate_key` | stored | Supports idempotent observation ingestion. |
| `is_duplicate` | 是否重复 | validation output | calculated from duplicate detection | derived | Duplicate status should be produced by quality checks, not blindly stored on all tables. |
| `rejection_reason` | 拒绝原因 | `data_quality_issues` | `issue_code`; `description` | stored | Structured issue code plus description captures rejected records. |
| `normalization_status` | 标准化状态 | quality output | issue/status from normalization process | deferred | Cleaning stage should define exact storage before implementation. |
| `raw_file_path` | 原始文件路径 | `collection_batches` | `raw_file_path` | stored | Points to immutable raw storage. |
| `raw_payload_reference` | 原始载荷引用 | `collection_batches` | `raw_payload_reference` | stored | References raw HTML, JSON, CSV, or row payload. |
| `parser_version` | 解析器版本 | `collection_batches` | `parser_version` | stored | Reproducibility for parsed records. |
| `collection_job_id` | 采集任务ID | `collection_batches` | `collection_job_id` | stored | Operational job identifier. |
| `checksum` | 校验哈希 | `collection_batches` | `checksum` | stored | Detects raw file changes. |
| `notes` | 备注 | all major tables | `notes` / `description` / `resolution_notes` | stored | Captures caveats without replacing structured fields. |
| `brand_id` | 品牌逻辑标识 | `brands` | `brand_id` | stored | Physical primary key. |
| `vehicle_id` | 车型逻辑标识 | `vehicles`; dependent tables | `vehicle_id` | stored | Physical primary key and foreign key. |
| `vehicle_variant_id` | 车型版本逻辑标识 | `vehicle_variants`; dependent tables | `vehicle_variant_id` | stored | Physical primary key and foreign key. |
| `official_price_observation_id` | 官方价格观察逻辑标识 | `official_price_observations` | `official_price_observation_id` | stored | Physical primary key. |
| `marketplace_listing_id` | 市场挂牌逻辑标识 | `marketplace_listings`; dependent tables | `marketplace_listing_id` | stored | Physical primary key and foreign key. |
| `registration_observation_id` | 注册量观察逻辑标识 | `registration_observations` | `registration_observation_id` | stored | Physical primary key. |
| `exchange_rate_observation_id` | 汇率观察逻辑标识 | `exchange_rate_observations` | `exchange_rate_observation_id` | stored | Physical primary key. |
| `estimated_transaction_price_id` | 估算成交价逻辑标识 | `estimated_transaction_prices` | `estimated_transaction_price_id` | stored | Physical primary key. |
| `issue_id` | 数据质量问题标识 | `data_quality_issues` | `data_quality_issue_id` | stored | Physical primary key uses a more explicit column name. |
| `base_url` | 数据源基础网址 | `data_sources` | `base_url` | stored | Public source base URL only. |
| `data_categories` | 数据类别列表 | `data_source_categories` | `data_category` | stored | Normalized association table instead of comma-separated text. |
| `update_frequency` | 更新频率 | `data_sources` | `update_frequency` | stored | Source planning metadata. |
| `authority_level` | 来源权威等级 | `data_sources` | `authority_level` | stored | Source conflict and trust routing. |
| `active` | 是否启用 | master/listing tables | `active` | stored | Soft-disable flag. |
| `collection_method` | 规划采集方式 | `data_sources`; `collection_batches` | `collection_method` | stored | Planned source method and batch method. |
| `chinese_brand` | 中文品牌名 | `brands` | `chinese_brand` | stored | Chinese display label. |
| `chinese_model` | 中文车型名 | `vehicles` | `chinese_model` | stored | Chinese display label. |
| `aliases` | 标准化别名列表 | `vehicle_aliases` | `alias_text`; `normalized_alias`; `alias_language`; `alias_type` | stored | Normalized alias table prevents unsafe cross-vehicle conflicts. |
| `input_record_reference` | 估算输入记录引用 | `estimated_transaction_prices` | `input_reference` | stored | Traceable input reference for estimates. |
| `estimation_method` | 估算方法 | `estimated_transaction_prices` | `estimation_method` | stored | Method is required for estimate auditability. |
