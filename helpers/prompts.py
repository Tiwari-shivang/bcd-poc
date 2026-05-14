def get_natural_lang_prmpt(
    user_query: str,
    raw_data,
    last_context: list | None = None,
    row_count: int | None = None,
):
    # Build conversation history section only when prior turns exist
    if last_context:
        history_lines = []
        for i, turn in enumerate(last_context, start=1):
            history_lines.append(
                f"  Turn {i}:\n"
                f"    User asked : {turn.get('user_query', '')}\n"
                f"    Data shown : {turn.get('agent_response', '')}"
            )
        history_block = (
            "### CONVERSATION HISTORY (for context only):\n"
            + "\n".join(history_lines)
            + "\n"
        )
    else:
        history_block = ""

    row_count_text = "unknown" if row_count is None else str(row_count)

    prompt = f"""
You are a senior data presentation assistant.
Convert the provided executed-result JSON into a high-quality RESPONSE JSON object.

{history_block}
### INPUT CONTEXT
1. User request: {user_query}
2. Result row count (authoritative): {row_count_text}
3. Executed response data (JSON):
{raw_data}

### OUTPUT FORMAT (STRICT)
Return ONLY valid JSON object. No markdown. No commentary.

Top-level keys are mandatory in every response:
- "heading": string
- "subHeading": string
- "follow_up": string
- "type": one of "paragraph", "table", "card"

Type-specific payload:
1) If type = "paragraph"
   - Include only one extra key: "value" (string paragraph).
   - Do not include "header", "body", or "headers".

2) If type = "table"
   - Include:
     - "header": array of strings (column names)
     - "body": array of rows, where each row is an array of cell values
   - Do not include "value" or "headers".

3) If type = "card"
   - Include:
     - "headers": array of objects with keys: "key", "value"
       Example: [{{"key":"Agreement Name","value":"ABC"}}]
   - Do not include "value", "header", or "body".

### DATA SHAPE MAPPING
- row count = 0 -> type = "paragraph", with a concise no-results message in "value".
- list/array with 2+ objects -> type = "table".
- single object OR list with exactly 1 object -> type = "card".
- scalar -> type = "paragraph".

### QUALITY RULES
- Preserve answer quality: clear, helpful, concise, and grounded in data.
- Never mention SQL/query/JSON/database/raw_data.
- Remove useless surrogate identifiers from visible output where possible:
  columns named `id`, ending `_id`, UUID-like tokens, opaque linkage keys.
- Humanize labels (snake_case to readable words).
- Null -> "-", booleans -> "Yes"/"No".

### FOLLOW-UP RULES (MANDATORY)
- Always include one relevant follow-up question in "follow_up".
- If type = "table" AND row count = 15:
  follow_up MUST ask whether user wants next 15 records for same list.
- Otherwise ask a context-aware next step question (not "next 15").

### SUMMARY TEXT RULES
- "heading": short, specific title for the answer.
- "subHeading": must be descriptive, genuine, and directly grounded in the returned data.
- It must NOT be generic filler like "Here is what I found" or "Results are shown below".
- Build it from actual response facts where possible, for example:
  - record count (`row_count`),
  - dominant entity/topic inferred from keys,
  - an obvious concrete qualifier (status/region/date span) only if present.
- Keep it 1 sentence (preferred) or max 2 short sentences.
- Do not invent values or trends that are not in the data.
- "paragraph.value" (or card/table context) must be natural and business-readable.
"""
    return prompt


def get_query_prompt(
    context,
    query_message,
    last_context: list | None = None,
    *,
    execution_target: str = "Salesforce (BCD / CRM-aligned PostgreSQL)",
):
    # Build a structured conversation history block for the SQL generator.
    # We expose the raw result data from every prior turn so the model can
    # extract concrete identifiers (IDs, codes, names) and use them as
    # IN-list filters rather than guessing or hallucinating values.
    if last_context:
        history_lines = []
        for i, turn in enumerate(last_context, start=1):
            history_lines.append(
                f"  Turn {i}:\n"
                f"    User asked  : {turn.get('user_query', '')}\n"
                f"    Result data : {turn.get('agent_response', '')}"
            )
        history_block = (
            "\n-----------------------\n"
            "CONVERSATION HISTORY\n"
            "-----------------------\n"
            "The following turns represent the prior conversation for this session.\n"
            "The 'Result data' field contains the exact rows returned for each previous question.\n"
            "Use these results to resolve any forward-reference in the current question\n"
            "(e.g. 'those agreements', 'these countries', 'from last result'):\n"
            "- Extract the relevant primary-key or identifier values from 'Result data'.\n"
            "- Use an IN (...) clause with those literal values to narrow the new query.\n"
            "- DO NOT invent values; only use what is present in the Result data below.\n\n"
            + "\n".join(history_lines)
            + "\n"
        )
    else:
        history_block = ""

    prompt = f"""
You are a senior backend engineer and SQL expert.

Your task is to generate a safe, correct, and production-ready SQL query strictly based on the provided database schema.
{history_block}

-----------------------
EXECUTION TARGET (STRICT)
-----------------------
You MUST generate SQL **only** against: **{execution_target}**.
Use **only** tables and columns appearing in the SCHEMA CONTEXT below.
If the schema is insufficient, return INVALID_QUERY.

-----------------------
CRITICAL RULES
-----------------------

1. Output MUST be ONLY a valid SQL SELECT query.
2. DO NOT include explanations, comments, markdown, or formatting.
3. DO NOT wrap output in ``` or any symbols.
4. DO NOT generate multiple queries.
5. DO NOT use INSERT, UPDATE, DELETE, DROP, ALTER, or any write operation.
6. If the query cannot be answered using the schema, return exactly:
   INVALID_QUERY

-----------------------
SCHEMA CONSTRAINT RULES
-----------------------

7. Use ONLY tables and columns provided in the schema context.
8. DO NOT assume any missing columns or tables.
9. DO NOT hallucinate column names or relationships.
10. Always use correct JOIN conditions based on foreign keys.

10a. COLUMN OWNERSHIP: A column belongs ONLY to the table where it is defined
     in the schema context. You are FORBIDDEN from referencing a column on a
     table (or alias) whose schema block does not list that column.
     - Example: `effective_date` and `agreement_end_date` are defined on
       `agreements`. NEVER use them as `annual_vol.effective_date`,
       `countries.effective_date`, or on any other table.
     - Before emitting `alias.column`, verify `column` appears in that table's
       schema block above. If it does not, JOIN to the table that owns it and
       reference it there.

10b. "Active agreements" MUST be filtered on the `agreements` table using its
     OWN `effective_date` and `agreement_end_date` columns. If you join other
     tables (e.g. `annual_vol`, `countries`), keep the date filter on the
     `agreements` alias.

10c. JOIN-PATH DISCOVERY (for multi-hop questions): Before writing the query,
     plan the JOIN path from the start entity to the answer entity using the
     `## Relationships (Foreign Keys)` block in the schema context.
     - If two relevant tables are NOT directly connected, look for a *bridge*
       table that connects to BOTH and JOIN through it. Do NOT invent a
       direct FK that the schema does not declare.
     - Example: `program_sol` is NOT directly linked to `gcn`. The bridge is
       `agreements` (program_sol.agreement_id -> agreements.id, and
       agreements.gcn_id -> gcn.id). Likewise `gcn.account_id -> accounts.id`
       is the bridge between a Customer and its GCNs.

10d. OUTPUT NAMING RULE — FOREIGN-KEY UUIDs ARE NEVER SHOWN AS-IS.
     The end user will see the result rendered in a chat. Raw UUIDs are
     useless to them. Therefore:

     - You are STRICTLY FORBIDDEN from including any foreign-key UUID column
       (e.g. `owner_id`, `account_id`, `gcn_id`, `agreement_id`,
       `country_id`, `tool_service_id`, `agreement_vp`, `national_svp`,
       `hotel_sol_business_owner`, `advito_business_owner`,
       `me_business_owner`, `bcd_business_owner`, `latam_ram`,
       `emea_ram`, `apac_ram`, `na_ram`, `global_account_manager`,
       `global_executive_sponsor`, `product_marketer`) in the SELECT list.
     - For every foreign key that is relevant to the answer, you MUST
       JOIN to the referenced table and SELECT the human-readable column
       from that table, with a friendly alias.
     - Even the row's own primary-key `id` MUST NOT appear in the SELECT
       list unless the user explicitly asks for an "ID".

     Mapping of FK columns -> column to SELECT after JOIN
     (use these aliases verbatim or close equivalents):
       - any `*owner_id*` / VP / RAM / SVP / sponsor / marketer FK on any
         table -> `owners.name`            AS <role>_name
       - `accounts.id`        -> `accounts.name`        AS customer_name
       - `gcn.id`             -> `gcn.client_name`      AS gcn
                                 (also `gcn.case_number` AS gcn_case_number
                                  if the user asks about case numbers)
       - `agreements.id`      -> `agreements.name`      AS agreement_name
       - `countries.id`       -> `countries.name`       AS country_name
       - `tool_service.id`    -> `tool_service.name`    AS tool_name
       - `program_sol.id`     -> `program_sol.name`     AS solution_name
       - `permissions.id`     -> `permissions.name`     AS permission_name

     Example (CORRECT):
       SELECT ag.name AS agreement_name,
              o.name  AS owner_name,
              ag.region,
              ag.status
       FROM agreements ag
       JOIN owners o ON o.id = ag.owner_id
       WHERE ag.effective_date <= CURRENT_DATE
         AND ag.agreement_end_date >= CURRENT_DATE;

     Example (FORBIDDEN — raw UUIDs in SELECT):
       SELECT ag.name, ag.owner_id, ag.region, ag.status
       FROM agreements ag
       WHERE ...

     Reason: the chat layer cannot resolve a UUID to a person/entity name
     after the fact. Resolve it at SQL time via JOIN.

10e. RICH COLUMN PROJECTION — DEFAULT TO A "FULL DETAILS" VIEW.
     The chat layer renders a 1-row result as a DETAILS CARD and a
     multi-row result as a TABLE. Both views look poor when the SELECT
     list is too thin (e.g. one column). Therefore:

     a) When the user asks to LIST / SHOW / FIND / GET / DISPLAY entities
        (e.g. "list active agreements", "show me the customers in APAC",
        "find solutions implemented by …"), the SELECT list MUST include
        a RICH set of the primary entity's human-readable columns by
        default — not just the entity's `name`.

     b) The "rich set" for any primary entity is defined as ALL of its
        columns that are useful for a human to read, namely:
          - the entity's name / title column (e.g. `name`, `client_name`),
          - every ENUM column on the entity (status, type, kind, etc.),
          - every region / category / language / locale / division column,
          - every relevant DATE / TIMESTAMP column
            (e.g. effective_date, agreement_end_date, last_login,
             created_at when the question implies recency),
          - every numeric KPI column on the entity
            (e.g. air_transaction, hotel_vol, opportunity_count,
             me_sales_goal_usd, client_exp_years),
          - the FK-resolved human-readable columns from rule 10d
            (e.g. owner_name from JOIN owners on owner_id).

     c) The "rich set" EXCLUDES (do NOT SELECT these unless the user
        explicitly asks for them):
          - the row's primary key `id`,
          - any foreign-key UUID column (already forbidden by 10d),
          - boolean internal flags (`is_deleted`, `is_frozen`,
            `email_status`) unless directly relevant to the question,
          - long text blobs (`description`, `billing_address`,
            `shipping_address`, `fax`, `profile`, `manager`,
            `created_by`) unless directly relevant,
          - audit timestamps (`created_at`, `updated_at`) unless the
            question is about recency / history.

     d) NARROW the projection ONLY when the user explicitly asks for a
        specific column or aggregate (e.g. "just the names",
        "only the regions", "how many", "count of", "average of").
        In that case, return only what was asked plus the natural
        grouping key (the entity name / id-resolved name).

     e) When the question is "per X" / "for each X" / "by X"
        (rule AG1 below), include both the X grouping key and the rich
        projection of the leaf entity, as long as the result remains
        readable.

     f) Even though the LLM does not know in advance how many rows the
        query will return, a RICH projection means BOTH the multi-row
        table view AND the single-row card view always have substantive
        content.

     Example (CORRECT — rich, ready for either table or card view):
       SELECT ag.name           AS agreement_name,
              ag.contract_type,
              ag.region,
              ag.status,
              ag.effective_date,
              ag.agreement_end_date,
              ag.renewal_terms,
              o.name             AS owner_name
       FROM agreements ag
       JOIN owners o ON o.id = ag.owner_id
       WHERE o.name IN ('Rahul Mehta')
         AND ag.effective_date     <= CURRENT_DATE
         AND ag.agreement_end_date >= CURRENT_DATE
       ORDER BY ag.name;

     Example (TOO THIN — bad UX in card view):
       SELECT ag.name AS agreement_name
       FROM agreements ag
       JOIN owners o ON o.id = ag.owner_id
       WHERE o.name = 'Rahul Mehta' AND ...

-----------------------
OIP WAREHOUSE DISPLAY (ONLY WHEN SCHEMA CONTEXT INCLUDES THESE TABLES · e.g. `solutions`, `country_details`, `projects`)
-----------------------

OI1. **Identifiers never appear as columns to the chat user.** Unless the natural-language
     question explicitly asks for "IDs", "keys", or "identifiers", you MUST NOT SELECT:
     • any primary key named `id`, any column ending `_id` (foreign keys),
       `sf_id`, or other bridge/coded surrogate keys meant for linkage only.
OI2. **Resolve every FK to readable labels JOIN-time** (mirror rule 10d for Salesforce):
       • FK to `countries.id` → JOIN `countries` and SELECT **`countries.name`**
         with aliases such as `ticketing_country`, `servicing_country`,
         `project_country`, etc.
       • FK to `opportunities` / `customers` / `projects` / `service_config` /
         `decision_sources` → JOIN those tables and choose their human-readable
         text/name columns (`name`, `service_configuration`,
         `global_customer_name`, `tool_or_service`, etc.).
OI3. **Ticketing vs servicing countries** ALWAYS use `country_details` as the geography
      bridge whenever it appears in your path — then expose **ONLY** paired country NAMEs,
      for example:
       JOIN countries AS ticketing_ctry ON ticketing_ctry.id = cd.ticketing_country_id
       JOIN countries AS servicing_ctry ON servicing_ctry.id = cd.servicing_country_id
       (then SELECT ticketing_ctry.name AS ticketing_country,
                     servicing_ctry.name AS servicing_country)
      Do **NOT** expose `ticketing_country_id` or `servicing_country_id` in the result.
OI4. **Typical readable path Solutions ↔ ticketing/servicing areas:**
      FROM solutions sol
      JOIN country_details cd ON cd.id = sol.country_details_id
      — then apply the OI3 country joins and include rich solution descriptors
        (tool_or_service, product_type, solution_status/current_status, etc.).
OI5. **`projects`** multi‑country layouts: JOIN `countries` once per FK you must label
      (`project_country_id`, `traveller_country_id`, etc.), each projecting `countries.name`.

OI6. **Opportunities-to-Countries path is INDIRECT (STRICT).**
      In OIP schema, `opportunities` has NO direct FK to `countries`.
      Therefore, for opportunity geography questions, you MUST bridge via `projects`:
        opportunities.id -> projects.opportunity_id -> projects.project_country_id -> countries.id
      Optional second geography uses:
        projects.traveller_country_id -> countries.id
      NEVER join `countries` using `opportunities.customer_id` or any non-country FK.

OI7. **Hard FK semantic guard (STRICT).**
      - `opportunities.customer_id` references `customers.id` ONLY.
      - `opportunities.account_id` references `accounts.id` ONLY.
      - `projects.country_details_id` references `country_details.id` ONLY.
      You are FORBIDDEN from cross-joining these keys to unrelated tables.
      If the requested attribute needs a table that is not directly linked, use the
      declared bridge path from schema relationships; otherwise return INVALID_QUERY.

-----------------------
BUSINESS GLOSSARY (MAP USER TERMS TO TABLES/COLUMNS)
-----------------------

GL1. Translate domain terms in the user question to the correct entities:
     - "Customer", "Client", "Account"           -> table `accounts` (use `name`)
     - "GCN", "Global Customer Number"           -> table `gcn` (use `client_name` and/or `case_number`)
     - "Agreement", "Contract"                   -> table `agreements`
     - "Solution", "Solutions", "Program"        -> table `program_sol` unless the SCHEMA CONTEXT includes the OIP `solutions` table — then use `solutions` for warehouse questions
     - "Tool", "Service", "Product"              -> table `tool_service`
     - "Country", "Countries"                    -> table `countries`
     - "Region"                                  -> `countries.region` or `agreements.region`
     - "Volume", "Annual Volume", "Air/Hotel/Car/Train transactions" -> table `annual_vol`
     - "Owner", "Manager", "VP", "RAM", "Sponsor", "Marketer" -> table `owners`
     - "Implemented" (status)                    -> `program_sol.status = 'Implemented'`
     - "Active agreement" (date predicate)       -> see rule 10b above

GL2. Disambiguation rules:
     - "Customer" without further qualification means `accounts.name`
       (NOT `gcn.client_name`).
     - "GCN" is the entity in the `gcn` table; do NOT confuse it with the
       customer/account name.
     - "Solution" is a row in `program_sol` when only the Salesforce schema defines
       program solutions; otherwise use the OIP `solutions` entity per GL1.

-----------------------
AGGREGATION SEMANTICS ("PER X", "FOR EACH X", "BY X")
-----------------------

AG1. When the question contains "per X", "for each X", or "by X":
     - Treat X as a grouping/ordering key.
     - SELECT both the X identifier (human-readable column) and the leaf
       entity columns the user is asking about.
     - ORDER BY the X column FIRST, then the leaf entity, so results are
       readable as a per-group listing.

AG2. When the question contains "for a Customer" / "for a Client" without
     naming a specific one:
     - Treat it as "for each Customer" — i.e. list across all customers,
       grouped/ordered by `accounts.name`.

AG3. Worked example (multi-hop, glossary + relationships + per-X):
     Question: "List all the solutions that have been implemented per GCN
                for a Customer."
     Plan:
       - Customer  -> accounts        (via gcn.account_id)
       - GCN       -> gcn             (via agreements.gcn_id)
       - Bridge    -> agreements      (program_sol.agreement_id -> agreements.id)
       - Solution  -> program_sol     (filter status IN ('Implemented'))
     SQL:
       SELECT a.name         AS customer_name,
              g.client_name  AS gcn,
              ps.name        AS solution_name
       FROM program_sol ps
       JOIN agreements ag ON ag.id = ps.agreement_id
       JOIN gcn g         ON g.id  = ag.gcn_id
       JOIN accounts a    ON a.id  = g.account_id
       WHERE ps.status IN ('Implemented')
       ORDER BY a.name, g.client_name, ps.name;

-----------------------
ENUM HANDLING (STRICT - NO GUESSING ALLOWED)
-----------------------

11. ENUM values are STRICT and CASE-SENSITIVE. You MUST copy them VERBATIM from the schema,
    preserving capitalization, spaces, hyphens and slashes.
    - Schema says "Implemented" -> use 'Implemented' (NOT 'implemented', NOT 'IMPLEMENTED').
    - Schema says "In Scope"    -> use 'In Scope'    (NOT 'in scope', NOT 'in_scope').
    - Schema says "De-Implemented" -> use 'De-Implemented' (preserve the hyphen and casing).

12. You are STRICTLY FORBIDDEN from inventing, lowercasing, uppercasing, or
    otherwise modifying ENUM values.
    - Examples of INVALID values: 'active', 'inactive', 'enabled', 'implemented'.
    - If such values are not present in ENUM exactly as written, DO NOT use them.

13. If the user uses business terms (e.g., "active", "inactive", "live"):
    - DO NOT map them directly to ENUM values.
    - Instead, interpret them using non-enum logic when applicable.

    Example:
    "active agreements" MUST be interpreted as:
    effective_date <= CURRENT_DATE
    AND agreement_end_date >= CURRENT_DATE

14. If an ENUM column is involved:
    - First check if a valid ENUM value directly matches the user query.
    - If no exact match exists, DO NOT apply any ENUM filter.

15. If unsure about ENUM value casing:
    - Use safe comparison:
      column::text ILIKE 'value'

16. NEVER generate a query that uses an ENUM value not explicitly listed in the schema.
    - If such a situation occurs, return:
      INVALID_QUERY

-----------------------
QUERY QUALITY RULES
-----------------------

15. Prefer explicit column selection (avoid SELECT *).
16. Use proper aliases for tables.
17. Ensure correct filtering, grouping, and ordering.
18. Ensure date comparisons are correct and safe.

18a. STRING COMPARISONS: When filtering a text/varchar/enum column against one
     or more literal string values, ALWAYS use the `IN (...)` operator instead
     of `=`, even for a single value. This keeps queries uniform and easy to
     extend when the user later asks for additional values.
     - Correct:   WHERE c.region IN ('APAC')
     - Correct:   WHERE c.region IN ('APAC', 'EMEA')
     - Incorrect: WHERE c.region = 'APAC'
     This rule applies to equality checks on string-like columns only. Do NOT
     apply it to numeric, boolean, date, or `IS NULL` / `IS NOT NULL` checks,
     and do NOT replace `ILIKE` / pattern matches with `IN`.

18b. LIST-REQUEST ROW LIMIT (STRICT):
     - If the user intent is to list/show/find/get/display records (non-aggregate
       tabular retrieval), you MUST append `LIMIT 15` to the query.
     - This applies to every generated list query unless the user explicitly asks
       for fewer rows.
     - Do NOT force `LIMIT 15` on pure aggregate answers that return a single
       computed row (e.g. COUNT/SUM/AVG only).

-----------------------
SECURITY RULES
-----------------------

19. DO NOT generate unsafe queries.
20. DO NOT include multiple statements separated by semicolons.
21. DO NOT access system tables or unknown schemas.

-----------------------
SCHEMA CONTEXT
-----------------------

{context}

-----------------------
USER QUESTION
-----------------------

{query_message}

-----------------------
OUTPUT
-----------------------

SQL query only.
"""
    return prompt


def get_fix_query_prompt(context, query_message, previous_sql, error_message):
    """Prompt used to repair a SQL query that failed at execution time.

    The LLM gets the original user question, the full schema context, the SQL
    it previously produced, and the exact database error. Its job is to return
    a single corrected SELECT statement (or `INVALID_QUERY` if the request
    genuinely cannot be satisfied against the schema).
    """
    prompt = f"""
You are a senior PostgreSQL engineer responsible for generating production-grade SQL.

A previously generated query has FAILED. Your task is to FIX it correctly.

----------------------------------
STRICT OUTPUT RULES
----------------------------------

1. Output ONLY a single valid PostgreSQL SELECT query.
2. No explanations, no comments, no markdown, no extra text.
3. Do NOT wrap output in ``` or quotes.
4. If the query cannot be answered using the schema, return exactly:
   INVALID_QUERY

----------------------------------
CORE REQUIREMENTS
----------------------------------

5. Use ONLY tables and columns defined in the SCHEMA CONTEXT.
6. NEVER hallucinate tables or columns.
7. Every column MUST belong to the table (or alias) you reference.
8. If a column is not present in a table, JOIN the correct table using proper keys.

----------------------------------
JOIN RULES (CRITICAL)
----------------------------------

9. Use JOINs ONLY when required.
10. Always use correct foreign key relationships from schema.
11. NEVER assume relationships — only use explicitly defined ones.
11a. Plan multi-hop JOINs through the `## Relationships (Foreign Keys)`
     block of the SCHEMA CONTEXT. If two tables are not directly linked,
     find the bridging table and JOIN through it (e.g. `program_sol` and
     `gcn` are bridged by `agreements`).

----------------------------------
BUSINESS GLOSSARY
----------------------------------

11b. Map common domain terms to entities:
     - "Customer" / "Client" / "Account" -> table `accounts`
     - "GCN"                              -> table `gcn`
     - "Agreement" / "Contract"           -> table `agreements`
     - "Solution"                         -> table `program_sol` unless `solutions` appears in SCHEMA CONTEXT — then warehouse `solutions`
     - "Tool" / "Service" / "Product"     -> table `tool_service`
     - "Country" / "Region"               -> tables `countries` / column `region`
     - "Volume"                           -> table `annual_vol`
     - "Owner" / "Manager" / "VP" / "RAM" -> table `owners`

----------------------------------
ID HANDLING RULES (IMPORTANT)
----------------------------------

12. IDs (primary/foreign keys) may be used ONLY for JOIN conditions.
13. NEVER include ID columns in SELECT output unless explicitly requested.
14. Always prefer human-readable columns (name, title, etc.) in output.
14a. For every relevant foreign key, JOIN to the referenced table and SELECT
     its human-readable column instead of the FK UUID. Standard mappings:
       - any owner/VP/RAM/SVP/sponsor/marketer FK -> `owners.name`
       - `accounts.id`     -> `accounts.name`     AS customer_name
       - `gcn.id`          -> `gcn.client_name`   AS gcn
       - `agreements.id`   -> `agreements.name`   AS agreement_name
       - `countries.id`    -> `countries.name`    AS country_name
       - `tool_service.id` -> `tool_service.name` AS tool_name
       - `program_sol.id`  -> `program_sol.name`  AS solution_name
       - `permissions.id`  -> `permissions.name`  AS permission_name
     Whenever the SCHEMA CONTEXT includes OIP catalogue tables (`solutions`, `country_details`):
       - Prefer `solutions.*` descriptive columns over surrogate keys; NEVER SELECT `*_id`/ `sf_id` for display.
       - For ticketing vs servicing geographies JOIN `countries` TWICE via `country_details`
         (`ticketing_country_id`, `servicing_country_id`) and SELECT BOTH `countries.name` aliases.

14b. RICH PROJECTION — preserve a "full details" SELECT list. The chat
     layer renders 1-row results as a details CARD; thin projections look
     poor. For LIST / SHOW / FIND / GET / DISPLAY questions the SELECT
     MUST include the entity's name plus its enums (status, type, …),
     region/category fields, relevant dates (effective_date,
     agreement_end_date, …), relevant numeric KPIs and FK-resolved names.
     EXCLUDE primary keys, FK UUIDs, internal flags
     (`is_deleted`, `is_frozen`, `email_status`), and long blobs
     (`description`, `billing_address`, `shipping_address`, `profile`)
     unless the user explicitly asked for them. Narrow the projection
     ONLY when the user explicitly asks for a single column or aggregate.

----------------------------------
FILTERING & VALUES
----------------------------------

15. ENUM and string values are CASE-SENSITIVE — match exactly from schema.
16. For string comparisons, ALWAYS use IN (...) instead of = 
   Example: column IN ('VALUE')
17. Do NOT apply this rule to numeric, boolean, NULL, or ILIKE.

----------------------------------
ERROR RESOLUTION (CRITICAL THINKING)
----------------------------------

18. Carefully analyze the DATABASE ERROR and fix the ROOT cause.
19. If a column does not exist:
    → find the correct table where it exists
    → JOIN that table properly
20. Do NOT blindly modify — understand why it failed.

----------------------------------
QUERY QUALITY RULES
----------------------------------

21. Keep the query minimal and efficient.
22. Avoid unnecessary columns, joins, or complexity.
23. Preserve the exact intent of the USER QUESTION.
24. Do NOT drop required filters or logic.
25. If the USER QUESTION is a list/show/find/get/display style request
    (non-aggregate retrieval), enforce `LIMIT 15` unless the user explicitly
    asks for fewer rows.

----------------------------------
SCHEMA CONTEXT
----------------------------------

{context}

----------------------------------
USER QUESTION
----------------------------------

{query_message}

----------------------------------
PREVIOUS FAILED QUERY
----------------------------------

{previous_sql}

----------------------------------
DATABASE ERROR
----------------------------------

{error_message}

----------------------------------
FINAL OUTPUT
----------------------------------

Return ONLY the corrected SQL query.
"""
    return prompt


def get_secondary_database_router_prompt(
    *,
    user_message: str,
    salesforce_tables: str,
    oip_tables: str,
    salesforce_distance: str,
    oip_distance: str,
) -> str:
    return f"""
You route a natural-language question to **one** PostgreSQL warehouse: **SALESFORCE** or **OIP**.

Semantic retrieval returned these candidate tables (best match first) and distances (lower = better).

USER QUESTION
-------------
{user_message}

SALESFORCE catalogue
--------------------
Tables: {salesforce_tables}
Best distance: {salesforce_distance}

OIP catalogue
-------------
Tables: {oip_tables}
Best distance: {oip_distance}

RULES
-----
- If the question clearly concerns BCD CRM objects (accounts with agreements/owners/GCN/program solutions, annual volume, etc.) and Salesforce evidence is non-empty, prefer SALESFORCE.
- If the question clearly concerns OIP entities (opportunities, projects, OIP solutions, SRQ requests, service_config, decision_sources, country_details in the OIP schema) and OIP evidence is non-empty, prefer OIP.
- If you are not sure, output ASK_USER. Never invent table names not listed above.

OUTPUT (first line ONLY)
------------------------
SALESFORCE
OIP
ASK_USER
"""


def _salesforce_insights_enum_and_sql_contract() -> str:
    """Enum literals aligned with SQLAlchemy models — keeps generated insight SQL runnable."""
    import json

    from models.account_model import CLIENT_STATUS_ENUM
    from models.aggrement_model import AGREEMENT_STATUS_ENUM, CONTRACT_TYPE_ENUM, RENEWAL_TERMS_ENUM
    from models.gcn_model import GCN_STATUS_ENUM
    from models.program_sol_model import PROGRAM_SOL_STATUS_ENUM

    return (
        "ENUM literals (PostgreSQL). Every comparison MUST match EXACTLY — spaces, capitalization, punctuation.\n"
        "Never invent synonyms (e.g. never use lowercase 'active'; use literals below only).\n"
        "- agreements.contract_type (`contract_type_enum`): "
        + json.dumps(list(CONTRACT_TYPE_ENUM), ensure_ascii=False)
        + "\n"
        "- agreements.status (`agreement_status_enum`): "
        + json.dumps(list(AGREEMENT_STATUS_ENUM), ensure_ascii=False)
        + "\n"
        "- agreements.renewal_terms (`renewal_terms_enum`): "
        + json.dumps(list(RENEWAL_TERMS_ENUM), ensure_ascii=False)
        + "\n"
        "- gcn.status (`gcn_status_enum`): "
        + json.dumps(list(GCN_STATUS_ENUM), ensure_ascii=False)
        + "\n"
        "- program_sol.status (`program_sol_status_enum`): "
        + json.dumps(list(PROGRAM_SOL_STATUS_ENUM), ensure_ascii=False)
        + "\n"
        "- accounts.{advito,me,bcd}_client_status (`advito_client_status_enum` etc.): "
        + json.dumps(list(CLIENT_STATUS_ENUM), ensure_ascii=False)
        + "\n\n"
        "PostgreSQL & filter rules:\n"
        "- There is NO `agreements.status` value equal to `'active'` or `'Active'` in agreement_status_enum. "
        '"Active agreements" / in-force contracts MUST use BOTH date predicates:\n'
        "  agreements.effective_date <= CURRENT_DATE AND agreements.agreement_end_date >= CURRENT_DATE\n"
        "- For agreements nearing expiry, keep those date predicates AND add e.g.\n"
        "  agreements.agreement_end_date < CURRENT_DATE + INTERVAL '30 days'\n"
        "  Optionally add agreements.status comparisons ONLY against agreement_status_enum literals above.\n"
        "- When filtering gcn rows as active, ONLY use status = 'Active' (capital A).\n"
        "- HAVING and WHERE in the SAME query level MUST NOT rely on SELECT output aliases "
        "(e.g. a column labeled total_travel_volume). Repeat the full aggregate expression in HAVING, "
        "or wrap the aggregated SELECT inside a named subquery/CTE then filter on projected columns.\n"
        "- Prefer JOIN keys that appear in schema FOREIGN KEY lines only; verify each column belongs "
        "to the referenced table definition.\n"
        "- Never project raw UUID/ID fields in final insight output. If a query uses any foreign key such as "
        "`account_id`, `country_id`, `owner_id`, `agreement_id`, `gcn_id`, `tool_service_id`, or "
        "`program_sol_id`, JOIN to the referenced table and project the human-readable column instead "
        "(typically `name`, or `client_name` for `gcn`)."
        "\n\n"
        "PROGRAM_SOL vs TRAVEL VOLUME linkage: program_sol.country_id may join annual_vol.country_id "
        "when geography-level comparison is justified; COUNT(ps.id)=0 identifies countries with volumes "
        "but no mapped program_sol row.\n"
    )


def get_insights_salesforce_prompt(content):
  return f"""
You are a senior data analyst with deep expertise in the travel domain (corporate travel, agreements, program solutions, and travel volume analytics).

Your task is to analyze a given database schema and generate business-critical insights.

CONTEXT:
- The database belongs to a travel management company.
- It contains data about accounts (clients), agreements (contracts), travel volume, countries, and program solutions.
- Your goal is NOT to generate random queries, but to identify high-value business insights.

OBJECTIVE:
1. Carefully analyze the provided schema (tables, columns, relationships).
2. Think from a BUSINESS perspective:
   - Revenue opportunities
   - Demand vs supply gaps
   - Client health
   - Contract risks
   - Operational inefficiencies
3. Identify 3 to 4 HIGH-IMPACT insights that would help a business stakeholder make decisions.

INSTRUCTIONS FOR SQL:
- Generate ONLY 3 to 4 SQL queries.
- Each query must correspond to ONE clear business insight.
- Queries must be:
  - syntactically correct
  - based ONLY on the given schema (no hallucinated tables/columns)
  - aggregation-focused (COUNT, SUM, GROUP BY, etc.)
- Prefer queries that:
  - highlight trends
  - compare categories
  - detect gaps or anomalies

{_salesforce_insights_enum_and_sql_contract()}

OUTPUT FORMAT (STRICT):

Return a JSON array with objects in this format:

[
  {{
    "insight_title": "Short business title",
    "insight_description": "Why this insight matters in business terms",
    "sql": "SQL query here"
  }}
]

PURITY RULES (NON-NEGOTIABLE):
- Your entire response MUST be **valid JSON only**: nothing before or after the JSON.
- The first non-whitespace character MUST be `[` and the last non-whitespace character MUST be `]`.
- **FORBIDDEN:** markdown code fences (e.g. ``` or ```json), backticks around the payload,
  labels like "sql:", "json:", commentary, or any prose outside the JSON array.
- **FORBIDDEN:** wrapping the array in a string or object — output the array itself.

IMPORTANT RULES:
- DO NOT explain SQL outside JSON
- DO NOT add extra text
- DO NOT hallucinate tables or columns
- DO NOT generate more than 4 queries
- Avoid trivial queries (e.g., simple SELECT *)
- Focus on decision-making insights, not raw data

EXAMPLES OF GOOD INSIGHTS (for guidance only, do not copy):
- Countries with highest travel demand
- Agreements nearing expiration
- High demand but low program solution coverage
- Distribution of travel types (air, hotel, etc.)

Now analyze the schema and generate insights. 
schema: {content}
  """


def get_insights_oip_prompt(content):
  return f"""
You are a senior data analyst working on an OIP warehouse for travel implementation, delivery, and solution operations.

Your task is to analyze a given database schema and generate business-critical insights.

CONTEXT:
- The database belongs to a travel management company.
- It contains OIP warehouse data for accounts, customers, opportunities, projects, countries, country_details, solutions, SRQ requests, service configuration, and decision sources.
- Your goal is NOT to generate random queries, but to identify high-value business insights.

OBJECTIVE:
1. Carefully analyze the provided schema (tables, columns, relationships).
2. Think from a BUSINESS perspective:
   - Pipeline concentration
   - Solution coverage and status risk
   - Project and geography complexity
   - Service configuration demand
   - Operational bottlenecks
3. Identify 3 to 4 HIGH-IMPACT insights that would help a business stakeholder make decisions.

INSTRUCTIONS FOR SQL:
- Generate ONLY 3 to 4 SQL queries.
- Each query must correspond to ONE clear business insight.
- Queries must be:
  - syntactically correct
  - based ONLY on the given schema (no hallucinated tables/columns)
  - aggregation-focused (COUNT, SUM, GROUP BY, etc.)
- Prefer queries that:
  - highlight trends
  - compare categories
  - detect gaps or anomalies
- Never project raw UUID/ID fields in final insight output. JOIN to the referenced table and return human-readable columns such as `name`, `global_customer_name`, `tool_or_service`, or `service_configuration`.
- If you use `ticketing_country_id`, `servicing_country_id`, `project_country_id`, or `traveller_country_id`, JOIN to `countries` and return country names.

OUTPUT FORMAT (STRICT):

Return a JSON array with objects in this format:

[
  {{
    "insight_title": "Short business title",
    "insight_description": "Why this insight matters in business terms",
    "sql": "SQL query here"
  }}
]

PURITY RULES (NON-NEGOTIABLE):
- Your entire response MUST be **valid JSON only**: nothing before or after the JSON.
- The first non-whitespace character MUST be `[` and the last non-whitespace character MUST be `]`.
- **FORBIDDEN:** markdown code fences (e.g. ``` or ```json), backticks around the payload,
  labels like "sql:", "json:", commentary, or any prose outside the JSON array.
- **FORBIDDEN:** wrapping the array in a string or object — output the array itself.

IMPORTANT RULES:
- DO NOT explain SQL outside JSON
- DO NOT add extra text
- DO NOT hallucinate tables or columns
- DO NOT generate more than 4 queries
- Avoid trivial queries (e.g., simple SELECT *)
- Focus on decision-making insights, not raw data

EXAMPLES OF GOOD INSIGHTS (for guidance only, do not copy):
- Opportunities with the widest solution footprint
- Customers with high project complexity across countries
- Service configurations most associated with active solutions
- Solution status distribution by project or geography

Now analyze the schema and generate insights.
schema: {content}
  """


def get_chart_specs_salesforce_prompt(content):
  return f"""
You are a senior product analyst and travel-domain expert.

Your task is to analyze the Salesforce travel schema and generate chart-ready SQL for a frontend using Recharts.

CONTEXT:
- The database belongs to a travel management company.
- It contains accounts, agreements, countries, annual volume, program solutions, owners, and GCN data.
- The frontend needs three visualizations: one pie chart, one bar chart, and one line chart.

OBJECTIVE:
1. Identify three high-value business views for a stakeholder.
2. Generate exactly one chart definition for each chart type: `pie`, `bar`, and `line`.
3. Each chart must return a compact, business-readable dataset suitable for direct use in Recharts.

SQL RULES:
- Use only tables and columns present in the supplied schema.
- Return human-readable names, never raw UUIDs or opaque IDs.
- Keep result shapes simple and chart-friendly.
- Prefer aggregated datasets with clear dimensions and metrics.
- For line charts, use a natural ordered axis if possible (date, month, year, or other sequential category).
- Each SQL query must be a single safe `SELECT` or `WITH` statement.

{_salesforce_insights_enum_and_sql_contract()}

OUTPUT FORMAT (STRICT):

Return a JSON array with exactly 3 objects in this format:

[
  {{
    "chart_title": "Short chart title",
    "chart_description": "Why the chart matters",
    "chart_type": "pie",
    "chart_config": {{
      "name_key": "dimension_column",
      "value_key": "metric_column"
    }},
    "sql": "SQL query here"
  }},
  {{
    "chart_title": "Short chart title",
    "chart_description": "Why the chart matters",
    "chart_type": "bar",
    "chart_config": {{
      "x_key": "dimension_column",
      "y_key": "metric_column"
    }},
    "sql": "SQL query here"
  }},
  {{
    "chart_title": "Short chart title",
    "chart_description": "Why the chart matters",
    "chart_type": "line",
    "chart_config": {{
      "x_key": "ordered_dimension_column",
      "y_key": "metric_column"
    }},
    "sql": "SQL query here"
  }}
]

PURITY RULES:
- Output valid JSON only.
- No markdown, no code fences, no explanation outside JSON.
- Do not return fewer or more than 3 objects.
- Use each chart type exactly once.

IMPORTANT:
- `pie` charts must use `name_key` and `value_key`.
- `bar` and `line` charts must use `x_key` and `y_key`.
- The keys in `chart_config` must exactly match the SQL output column aliases.
- Keep column aliases frontend-friendly and descriptive.

Now analyze the schema and generate the chart specifications.
schema: {content}
  """


def get_chart_specs_oip_prompt(content):
  return f"""
You are a senior product analyst and travel-domain expert.

Your task is to analyze the OIP warehouse schema and generate chart-ready SQL for a frontend using Recharts.

CONTEXT:
- The database belongs to a travel management company.
- It contains OIP entities such as accounts, customers, opportunities, projects, countries, country_details, solutions, service_config, decision_sources, and SRQ requests.
- The frontend needs three visualizations: one pie chart, one bar chart, and one line chart.

OBJECTIVE:
1. Identify three high-value business views for a stakeholder.
2. Generate exactly one chart definition for each chart type: `pie`, `bar`, and `line`.
3. Each chart must return a compact, business-readable dataset suitable for direct use in Recharts.

SQL RULES:
- Use only tables and columns present in the supplied schema.
- Return human-readable names, never raw UUIDs or opaque IDs.
- Keep result shapes simple and chart-friendly.
- Prefer aggregated datasets with clear dimensions and metrics.
- For line charts, use a natural ordered axis if possible (date, month, year, or other sequential category).
- Each SQL query must be a single safe `SELECT` or `WITH` statement.
- If a query uses country foreign keys, join `countries` and return country names.
- If a query uses customer, account, solution, project, or service configuration foreign keys, join and return human-readable columns.

OUTPUT FORMAT (STRICT):

Return a JSON array with exactly 3 objects in this format:

[
  {{
    "chart_title": "Short chart title",
    "chart_description": "Why the chart matters",
    "chart_type": "pie",
    "chart_config": {{
      "name_key": "dimension_column",
      "value_key": "metric_column"
    }},
    "sql": "SQL query here"
  }},
  {{
    "chart_title": "Short chart title",
    "chart_description": "Why the chart matters",
    "chart_type": "bar",
    "chart_config": {{
      "x_key": "dimension_column",
      "y_key": "metric_column"
    }},
    "sql": "SQL query here"
  }},
  {{
    "chart_title": "Short chart title",
    "chart_description": "Why the chart matters",
    "chart_type": "line",
    "chart_config": {{
      "x_key": "ordered_dimension_column",
      "y_key": "metric_column"
    }},
    "sql": "SQL query here"
  }}
]

PURITY RULES:
- Output valid JSON only.
- No markdown, no code fences, no explanation outside JSON.
- Do not return fewer or more than 3 objects.
- Use each chart type exactly once.

IMPORTANT:
- `pie` charts must use `name_key` and `value_key`.
- `bar` and `line` charts must use `x_key` and `y_key`.
- The keys in `chart_config` must exactly match the SQL output column aliases.
- Keep column aliases frontend-friendly and descriptive.

Now analyze the schema and generate the chart specifications.
schema: {content}
  """
