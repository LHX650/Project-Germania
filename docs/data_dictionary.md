# Project Germania Data Dictionary

This file is a logical data specification for Project Germania. It is not a
database implementation.

Important scope notes:

- Database tables, SQLAlchemy models, and Alembic migrations have not been
  created.
- Different data sources will not provide every field.
- Field nullability must be decided for each business dataset and source
  integration.
- Listing prices are asking prices, not transaction prices.
- KBA new vehicle registrations are the project's preferred proxy for German
  market sales trends, but they are not the same as automotive company revenue,
  retail sales, wholesale sales, or deliveries.
- Unknown values must remain unknown or null; they must not be silently guessed.

## A. Record Identity Fields

| Field | 中文含义 | Recommended Type | Nullable | Example | Recommended Source | Cleaning or Validation Rules | Business Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `record_id` | 记录唯一标识 | string / UUID | No | `rec_01H...` | System generated | Must be stable and unique within its dataset. | Logical record identifier; database primary keys may differ later. |
| `record_type` | 记录类型 | enum string | No | `marketplace_listing` | System generated | Use controlled values such as `official_price`, `listing`, `registration`, `exchange_rate`. | Allows mixed exports to distinguish record categories. |
| `batch_id` | 批次标识 | string / UUID | Yes | `batch_2026_07_18_001` | Collection process | Link to a collection or import batch when available. | Supports audit and rollback analysis. |

## B. Region Fields

`region` is the business analysis area, such as Germany or EU. `country_code`
should use ISO 3166-1 alpha-2 when applicable. `state` is intended for German
federal states. `city` and `postal_code` mainly apply to listing and dealer data.

| Field | 中文含义 | Recommended Type | Nullable | Example | Recommended Source | Cleaning or Validation Rules | Business Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `region` | 业务分析区域 | string | Yes | `Germany` | KBA, ACEA, marketplace, system mapping | Normalize broad analysis areas such as `Germany`, `EU`, or a German state. | Used for aggregation and dashboard filters. |
| `country_code` | 国家代码 | string | Yes | `DE` | All sources | Prefer ISO 3166-1 alpha-2; use `EU` only for Europe-level sources by project rule. | Do not infer country if source context is ambiguous. |
| `state` | 州或省级地区 | string | Yes | `Bavaria` | Marketplace, dealer data, official regional data | Normalize German federal-state names when available. | Useful for regional inventory and listing analysis. |
| `city` | 城市 | string | Yes | `Munich` | Marketplace, dealer data | Preserve raw value before normalization; trim whitespace. | Mainly applies to listings and sellers. |
| `postal_code` | 邮政编码 | string | Yes | `80331` | Marketplace, dealer data | Keep as string to preserve leading zeros. | Supports local inventory and dealer geography. |

## C. Website and Data Source Fields

`source_name` is the data source name. `source_url` stores the concrete page or
file origin. `source_listing_id` stores marketplace identifiers from sources
such as AutoScout24 or Mobile.de. Every source-derived record must be traceable.

| Field | 中文含义 | Recommended Type | Nullable | Example | Recommended Source | Cleaning or Validation Rules | Business Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `source_id` | 数据源标识 | string | No | `kba` | `config/sources.yaml` | Must match configured `source_id`. | Stable machine-readable source key. |
| `source_name` | 数据源名称 | string | No | `Kraftfahrt-Bundesamt (KBA)` | `config/sources.yaml` | Use configured display name. | Human-readable source label. |
| `source_type` | 数据源类型 | enum string | No | `government` | `config/sources.yaml` | Must use approved source type enum. | Supports authority and compliance routing. |
| `source_url` | 具体页面或文件来源 | string / URL | Yes | `https://www.kba.de/...` | Source metadata | Store exact URL when available; do not store secrets. | Required for auditability. |
| `source_listing_id` | 来源平台挂牌ID | string | Yes | `as24_123456` | AutoScout24, Mobile.de | Preserve source identifier exactly when provided. | Supports incremental listing matching. |
| `source_record_id` | 来源记录ID | string | Yes | `row_2026_06_001` | KBA, ACEA, ECB, imports | Preserve official or import record ID where available. | Useful when the source does not have listings. |
| `source_file_name` | 来源文件名 | string | Yes | `fz10_2026_06.xlsx` | Manual downloads, official files | Preserve original file name. | Links parsed rows to raw files. |
| `source_page_number` | 来源页码 | integer | Yes | `12` | PDF reports, official files | Must be positive when present. | Helps audit PDF/table extraction. |

## D. Brand and Vehicle Fields

`canonical_brand` and `canonical_model` must use standard names from
`config/vehicles.yaml`. `raw_brand` and `raw_model` preserve original source
text. Cleaning must not discard raw values.

| Field | 中文含义 | Recommended Type | Nullable | Example | Recommended Source | Cleaning or Validation Rules | Business Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `canonical_brand` | 标准品牌 | string | Yes | `Volkswagen` | `config/vehicles.yaml` | Match through approved aliases only; do not guess. | Primary brand dimension for analysis. |
| `canonical_model` | 标准车型 | string | Yes | `ID.4` | `config/vehicles.yaml` | Match through approved aliases only; `ID.4` must not match `ID.5`. | Primary model dimension for analysis. |
| `raw_brand` | 原始品牌文本 | string | Yes | `VW` | Source data | Preserve source text exactly when possible. | Required for traceability and matcher debugging. |
| `raw_model` | 原始车型文本 | string | Yes | `Volkswagen ID4` | Source data | Preserve source text exactly when possible. | Required for future mapping improvements. |
| `manufacturer` | 制造商 | string | Yes | `Volkswagen AG` | `config/vehicles.yaml`, manufacturer source | Normalize only through configuration or verified mapping. | Brand and manufacturer can differ in group structures. |
| `country_of_origin` | 品牌或车型来源国 | string | Yes | `Germany` | `config/vehicles.yaml` | Use configured value for research vehicles. | Strategic segmentation field. |
| `vehicle_segment` | 车型级别 | string | Yes | `compact_electric_suv` | `config/vehicles.yaml`, source specs | Use controlled project values. | Enables like-for-like comparisons. |
| `body_type` | 车身形式 | string | Yes | `suv` | `config/vehicles.yaml`, source specs | Use controlled values such as `hatchback`, `suv`, `sedan`. | Supports inventory and price segmentation. |
| `powertrain` | 动力系统 | enum string | Yes | `battery_electric` | `config/vehicles.yaml`, source specs | Use normalized values; unknown values remain `unknown`. | High-level drivetrain classification. |
| `fuel_type` | 燃料类型 | string | Yes | `electricity` | Source specs, listing data | Normalize only with verified rules. | More granular than `powertrain` when needed. |

## E. Model Year and Variant Fields

`model_year` is the model year and is not necessarily the first registration
year. `trim_name` is the official or website-displayed trim. `variant_name` may
represent powertrain or body variants. `edition_name` is for special or limited
editions. If source names differ across websites, preserve raw values and map
them later.

| Field | 中文含义 | Recommended Type | Nullable | Example | Recommended Source | Cleaning or Validation Rules | Business Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `model_year` | 车型年款 | integer / string | Yes | `2026` | Manufacturer, listing data | Do not confuse with first registration year. | Used for version comparisons. |
| `generation` | 代际 | string | Yes | `Mk8` | Manufacturer, expert mapping | Preserve unknown when not verified. | Useful for long-running models. |
| `trim_name` | 配置版本 | string | Yes | `Life` | Manufacturer, marketplace | Preserve raw display text before mapping. | Official trim naming can change. |
| `variant_name` | 车型变体 | string | Yes | `Pro Performance` | Manufacturer, marketplace | Preserve raw value; standardize later. | May refer to battery, power, or body variant. |
| `edition_name` | 特别版名称 | string | Yes | `First Edition` | Manufacturer, marketplace | Preserve only when source states it. | Helps avoid mixing limited editions with base trims. |
| `drivetrain` | 驱动形式 | string | Yes | `awd` | Manufacturer, listing data | Normalize values such as `fwd`, `rwd`, `awd` when verified. | Important for price comparability. |
| `transmission` | 变速箱 | string | Yes | `automatic` | Manufacturer, listing data | Normalize source-specific text carefully. | More relevant to ICE and hybrid vehicles. |
| `battery_capacity_kwh` | 电池容量 | Decimal | Yes | `77.0` | Manufacturer specs, listing data | Must be non-negative; record unit conversion if needed. | EV comparison feature. |
| `engine_power_kw` | 功率千瓦 | Decimal | Yes | `150` | Manufacturer specs, listing data | Must be non-negative. | Preferred metric unit for calculations. |
| `engine_power_ps` | 公制马力 | Decimal | Yes | `204` | Manufacturer specs, listing data | Must be non-negative; keep conversion trace if derived. | Useful because German listings often show PS. |

## F. Vehicle Condition Fields

`condition` should use values such as `new`, `used`, `demonstrator`, or
`unknown`. `seller_type` should distinguish `manufacturer`, `dealer`, `private`,
`marketplace`, and `unknown`.

| Field | 中文含义 | Recommended Type | Nullable | Example | Recommended Source | Cleaning or Validation Rules | Business Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `condition` | 车辆状态 | enum string | Yes | `used` | Marketplace, dealer data | Use controlled values: `new`, `used`, `demonstrator`, `unknown`. | Affects price comparability. |
| `first_registration_date` | 首次注册日期 | date | Yes | `2024-05-01` | Marketplace, dealer data | Must be valid date; do not confuse with model year. | Key used-car feature. |
| `mileage_km` | 里程公里数 | integer | Yes | `18500` | Marketplace, dealer data | Must be non-negative; convert from other units if needed. | Core used-car price driver. |
| `owner_count` | 车主数量 | integer | Yes | `1` | Marketplace, dealer data | Must be non-negative. | Often missing or inconsistently reported. |
| `seller_type` | 卖家类型 | enum string | Yes | `dealer` | Marketplace, dealer data | Use `manufacturer`, `dealer`, `private`, `marketplace`, `unknown`. | Helps compare inventory channels. |
| `dealer_name` | 经销商名称 | string | Yes | `Autohaus Example GmbH` | Marketplace, dealer data | Preserve source text; avoid collecting unrelated personal data. | Supports dealer-level audit if permitted. |

## G. Sales and Registration Fields

`registration_count` represents KBA or other authoritative new vehicle
registration counts and must not be negative. Project defaults should use
`registration_count` for German market sales trends. It is not the same as
company financial sales, wholesale sales, retail sales, revenue, or deliveries.
Different sales metrics must not be mixed without explicit methodology.

| Field | 中文含义 | Recommended Type | Nullable | Example | Recommended Source | Cleaning or Validation Rules | Business Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `registration_count` | 新车注册量 | integer | Yes | `1234` | KBA, ACEA | Must be integer and non-negative. | Preferred German sales-trend proxy. |
| `registration_period` | 注册统计周期 | string | Yes | `2026-06` | KBA, ACEA | Use clear period formats such as `YYYY-MM` or `YYYY-Qn`. | Must match source reporting period. |
| `registration_scope` | 注册统计范围 | string | Yes | `Germany` | KBA, ACEA | Use explicit geography such as `Germany`, `Bavaria`, or `EU`. | Enables scope-safe aggregation. |
| `sales_metric_type` | 销量口径类型 | enum string | Yes | `new_registration` | KBA, manufacturer, reports | Use `new_registration`, `retail_sales`, `wholesale_sales`, `delivery`, `unknown`. | Required when comparing non-KBA metrics. |
| `sales_value` | 其他销量口径数值 | integer / Decimal | Yes | `1200` | Manufacturer reports, third-party reports | Must be used with `sales_metric_type`; do not mix with registrations. | For metrics that cannot map directly to `registration_count`. |

## H. Price Fields

Amount fields should use Decimal semantics, not float. `official_price` is the
manufacturer's list price or recommended retail price. `listed_price` is an
asking price from a marketplace or dealer site and is not a transaction price.
`estimated_transaction_price` is an estimate and must never be presented as a
confirmed transaction price. `transaction_price` may be used only when a reliable
source explicitly provides an actual transaction price.

| Field | 中文含义 | Recommended Type | Nullable | Example | Recommended Source | Cleaning or Validation Rules | Business Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `official_price` | 官方指导价 | Decimal | Yes | `44990.00` | Manufacturer Germany websites, official price lists | Must be non-negative; record price status and VAT inclusion. | MSRP or official starting/list price. |
| `listed_price` | 市场挂牌价 | Decimal | Yes | `41990.00` | AutoScout24, Mobile.de, dealer sites | Must be non-negative; do not treat as transaction price. | Asking price for listing analysis. |
| `estimated_transaction_price` | 估算成交价 | Decimal | Yes | `40250.00` | Model output, derived analytics | Must be clearly marked estimated and include confidence. | Derived value only; not source truth. |
| `transaction_price` | 真实成交价 | Decimal | Yes | `39800.00` | Confirmed transaction source only | Must remain null without reliable source. | Do not fill from listed price. |
| `discount_amount` | 折扣绝对金额 | Decimal | Yes | `3000.00` | Derived from documented price fields | Calculation basis must be recorded. | Can compare official vs listed or estimated prices. |
| `discount_rate` | 折扣率 | Decimal | Yes | `0.067` | Derived analytics | Must state denominator price field. | Avoid ambiguous percentage calculations. |
| `price_min` | 价格下限 | Decimal | Yes | `39990.00` | Manufacturer, marketplace aggregation | Must be non-negative. | Useful for ranges and variants. |
| `price_max` | 价格上限 | Decimal | Yes | `55990.00` | Manufacturer, marketplace aggregation | Must be non-negative and greater than or equal to `price_min` when both exist. | Useful for ranges and variants. |
| `price_includes_vat` | 价格是否含增值税 | boolean | Yes | `true` | Manufacturer, marketplace | Must be boolean when known. | Important for German price comparability. |
| `price_status` | 价格状态 | enum string | Yes | `listed` | Source or derived logic | Use `official`, `listed`, `estimated`, `confirmed_transaction`, `unknown`. | Required to avoid mixing price meanings. |

## I. Currency and Exchange Rate Fields

`currency` must use ISO 4217 three-letter codes such as `EUR`, `CNY`, or `USD`.
Exchange-rate direction must be explicit. `price_eur` must be traceable to the
original price, original currency, exchange rate, exchange-rate date, and rate
direction. If the original price is already EUR, `exchange_rate` may be `1`, but
base and quote currencies still need to be explicit by project rule.

| Field | 中文含义 | Recommended Type | Nullable | Example | Recommended Source | Cleaning or Validation Rules | Business Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `currency` | 原始价格货币 | string | Yes | `EUR` | Manufacturer, marketplace, ECB | Use ISO 4217 three-letter code. | Required for price conversion. |
| `exchange_rate` | 汇率 | Decimal | Yes | `1.0000` | ECB, authoritative FX source | Must be positive and direction-aware. | Do not default missing non-EUR rates to 1. |
| `exchange_rate_base_currency` | 汇率基准货币 | string | Yes | `EUR` | ECB, conversion logic | Must use ISO 4217 and pair with quote currency. | Defines exchange-rate direction. |
| `exchange_rate_quote_currency` | 汇率报价货币 | string | Yes | `EUR` | ECB, conversion logic | Must use ISO 4217 and pair with base currency. | Defines exchange-rate direction. |
| `exchange_rate_date` | 汇率适用日期 | date | Yes | `2026-06-30` | ECB | Must be valid date and match price conversion date rules. | Historical conversions must use relevant dates. |
| `price_eur` | 欧元换算价格 | Decimal | Yes | `41990.00` | Derived conversion | Must be traceable to original price and exchange-rate fields. | Standardized price for comparison. |

## J. Date and Time Fields

Use ISO 8601 for dates and timestamps. Store timestamps in UTC where possible
and convert to Europe/Berlin for display when needed.

| Field | 中文含义 | Recommended Type | Nullable | Example | Recommended Source | Cleaning or Validation Rules | Business Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `observed_at` | 来源观察时间 | datetime | Yes | `2026-07-18T08:00:00Z` | Source data, collection process | Must represent the time the source data refers to. | Not always equal to collection time. |
| `collected_at` | 系统采集时间 | datetime | Yes | `2026-07-18T09:05:00Z` | Collection process | Must be generated by system and timezone-aware. | Audit field for imports and collectors. |
| `valid_date` | 业务有效日期 | date | Yes | `2026-06-01` | Official price, registration, FX source | Must match source's effective period or date. | Useful for official prices, FX, and registrations. |
| `effective_from` | 生效开始时间 | date / datetime | Yes | `2026-06-01` | Manufacturer, policy, source metadata | Must be earlier than `effective_to` when both exist. | Supports price validity windows. |
| `effective_to` | 生效结束时间 | date / datetime | Yes | `2026-06-30` | Manufacturer, policy, source metadata | Must be later than `effective_from` when both exist. | Supports price validity windows. |
| `first_seen_at` | 首次发现时间 | datetime | Yes | `2026-07-01T10:00:00Z` | Marketplace monitoring | Must be timezone-aware when generated. | Listing lifecycle tracking. |
| `last_seen_at` | 最后发现时间 | datetime | Yes | `2026-07-18T10:00:00Z` | Marketplace monitoring | Must be later than or equal to `first_seen_at`. | Listing lifecycle tracking. |
| `created_at` | 记录创建时间 | datetime | Yes | `2026-07-18T10:01:00Z` | System generated | Must be timezone-aware. | Data warehouse audit field. |
| `updated_at` | 记录更新时间 | datetime | Yes | `2026-07-18T10:02:00Z` | System generated | Must be timezone-aware and not before `created_at`. | Data warehouse audit field. |

## K. Data Quality Fields

Suggested enums:

- `data_quality_status`: `valid`, `warning`, `invalid`, `unknown`
- `validation_status`: `pending`, `passed`, `failed`
- `confidence_level`: `high`, `medium`, `low`, `unknown`

Estimated transaction prices must have `confidence_level`. Uncertain or missing
data must not be marked as high confidence by default.

| Field | 中文含义 | Recommended Type | Nullable | Example | Recommended Source | Cleaning or Validation Rules | Business Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `data_quality_status` | 数据质量状态 | enum string | Yes | `warning` | Validation process | Use controlled enum. | High-level quality state. |
| `validation_status` | 校验状态 | enum string | Yes | `passed` | Validation process | Use `pending`, `passed`, or `failed`. | Tracks rule execution. |
| `completeness_score` | 完整性评分 | Decimal | Yes | `0.95` | Data quality process | Range should be 0 to 1 or documented scale. | Supports data quality reporting. |
| `confidence_level` | 置信度等级 | enum string | Yes | `medium` | Matcher, estimator, validation process | Use controlled enum; do not default to high. | Required for uncertain matches and estimates. |
| `duplicate_key` | 去重键 | string | Yes | `autoscout24_de:123456:2026-07-18` | Deduplication process | Must be deterministic for its dataset. | Supports idempotent ingestion. |
| `is_duplicate` | 是否重复 | boolean | Yes | `false` | Deduplication process | Must be boolean when known. | Keeps rejected/duplicate records auditable. |
| `rejection_reason` | 拒绝原因 | string | Yes | `missing_currency` | Validation process | Use structured reason codes where possible. | Explains rejected records. |
| `normalization_status` | 标准化状态 | enum string | Yes | `matched` | Cleaning process | Suggested values: `matched`, `unmatched`, `review_required`, `unknown`. | Helps route manual review. |

## L. Raw Data and Traceability Fields

`notes` is for special offers, configuration differences, data anomalies, source
limitations, manual correction explanations, and unconfirmed information. It
must not replace structured fields.

| Field | 中文含义 | Recommended Type | Nullable | Example | Recommended Source | Cleaning or Validation Rules | Business Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `raw_file_path` | 原始文件路径 | string / path | Yes | `data/raw/kba/2026-07-18/file.xlsx` | Raw data layer | Must point to immutable raw storage when available. | Supports reprocessing and audit. |
| `raw_payload_reference` | 原始载荷引用 | string | Yes | `payload_001.json` | Raw data layer | Reference stored raw HTML, JSON, CSV, or row payload. | Avoid duplicating large payloads in analytics tables. |
| `parser_version` | 解析器版本 | string | Yes | `kba_parser@0.1.0` | Parser code | Record semantic version or commit reference. | Makes derived records reproducible. |
| `collection_job_id` | 采集任务ID | string | Yes | `job_20260718_001` | Collection process | Link to job or batch metadata. | Supports operational audit. |
| `checksum` | 校验哈希 | string | Yes | `sha256:abc123...` | Raw data layer | Use stable hash algorithm and prefix. | Detects raw file changes. |
| `notes` | 备注 | string | Yes | `Manual review required for trim mapping.` | Source, analyst, validation process | Do not use as replacement for structured fields. | Captures caveats and review notes. |
