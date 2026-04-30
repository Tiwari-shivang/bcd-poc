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
            "### CONVERSATION HISTORY (for context only — do NOT re-render or duplicate past turns):\n"
            + "\n".join(history_lines)
            + "\n"
        )
    else:
        history_block = ""

    # Authoritative row-count signal so the model cannot misclassify a
    # populated result as empty.
    row_count_text = "unknown" if row_count is None else str(row_count)

    prompt = f"""
You are a senior UI data presenter. Your job is to convert the executed SQL query response (provided as JSON) into a single, well-formed, good-looking HTML page.

{history_block}
### INPUT CONTEXT (DO NOT ECHO VERBATIM):
1. User request (natural language): {user_query}
2. Result row count (authoritative): {row_count_text}
3. Executed SQL response (JSON):
{raw_data}

### CRITICAL OUTPUT RULES (NON-NEGOTIABLE):
- Output MUST be **ONLY raw HTML**. Absolutely NO markdown, NO backticks, NO code fences (` ``` ` or ` ```html `), NO explanations, NO labels, NO leading or trailing text of any kind.
- The very first character of your response MUST be `<` (the start of `<!doctype html>`). Any other character is a violation.
- The very last character of your response MUST be `>` (the closing `</html>`). Any other character is a violation.
- Output MUST be **valid, well-formed HTML** with correct opening/closing tags and **no syntax errors**.
- Output MUST be a **single complete HTML document** starting with `<!doctype html>` and containing `<html>`, `<head>`, and `<body>`.
- Do NOT mention implementation details like "SQL", "query", "rows", "JSON", "database", or "raw_data" anywhere in the HTML.
- Use ONLY information present in the provided JSON. Do NOT invent or infer values.

### RESULT-COUNT CONTRACT (HARD RULE):
- Treat field 2 ("Result row count") as the SINGLE SOURCE OF TRUTH about emptiness.
- If row count is `0`: render the "No results found" empty-state.
- If row count is `>= 1`: you are STRICTLY FORBIDDEN from rendering "No results", "No data", or any equivalent empty-state. You MUST render the data from the JSON, even if the JSON contains only one row or one field.
- A non-empty JSON array (e.g. `[{{"agreement_name": "Infosys Consulting Agreement"}}]`) is NEVER empty. One row IS data — render it as a table with one row.

### RENDERING REQUIREMENTS — CHAT-MESSAGE FRIENDLY:
This output is going to be embedded inside a chat message bubble in a web
app. It is NOT a standalone dashboard page. Style it like an elegant,
self-contained mini-card a chat assistant would attach to its reply.

- Create a clean, modern layout with inline CSS inside `<style>` (no
  external assets, no scripts, no fonts loaded from the network).
- Layout & sizing (chat-friendly):
  - The OUTERMOST visible element inside `<body>` MUST be a single
    container `<section class="chat-card">` (or equivalent) that wraps
    title + summary + data. This container is the "card".
  - The card MUST be width-flexible: `width: 100%; max-width: 720px;`
    and `box-sizing: border-box;`.
  - The card MUST have a subtle border (`1px solid #d6e6f5` or similar
    light blue), `border-radius: 8px`, and modest interior padding
    (around `12px 14px`).
  - Use a soft `box-shadow` (e.g. `0 1px 2px rgba(0,0,0,0.06)`) for a
    light "card" feel. Keep it minimal — this is a chat bubble, not a
    landing page.
  - `body` should have `margin: 0; padding: 0;` and use a system font
    stack (e.g. `font-family: -apple-system, BlinkMacSystemFont,
    "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;`).
  - Do NOT add page-level chrome: no full-screen headers, no sticky
    headers, no fixed positioning, no scroll-locking, no banners.
  - Spacing inside the card should be tight and balanced — title,
    summary, and data each visually distinct but compact.
- Typography and alignment are STRICT:
  - Every font size MUST be exactly `14px` — set globally with
    `*, *::before, *::after {{ font-size: 14px !important; }}` so
    browser UA defaults on headings (h1–h6), pre, code, etc. cannot
    override it.
  - The visible title heading inside the card MUST also be `14px`.
    You MAY use `font-weight: 600` or `bold` to give it weight, but
    `font-size` MUST stay `14px`.
  - The `<title>` tag inside `<head>` must contain a concise, human-
    readable title matching the card's visible heading.
  - All text MUST be left-aligned.
  - Use comfortable `line-height` (around 1.45) for readable prose.
- Color rule is STRICT:
  - The default page/card background colour is white (`#ffffff`) or
    transparent so the chat container shows through naturally.
  - If you use ANY non-default background colour anywhere — for the
    card, table headers, summary tint, hover/zebra rows, etc. — it
    MUST be `#8FC9FF` (no other background colours allowed). Use it
    sparingly so it stays elegant, not loud.
- Include a clear title inside the card (derived from the user request),
  but do not repeat the entire user request verbatim.
- The HTML must be formed according to the JSON structure:

### PAGE STRUCTURE (STRICT ORDER INSIDE `<body>`):
The body MUST be structured in EXACTLY this top-to-bottom order:
  1. The page title heading (e.g. `<h1>` styled to 14px / bold).
  2. A SUMMARY PARAGRAPH section (rules below). Skip ONLY when row count = 0.
  3. The DATA section (table / details card / value card / empty-state).
No additional sections, footers, or decorative blocks are allowed.

### SUMMARY PARAGRAPH (NON-EMPTY RESULTS ONLY):
Write a warm, natural, conversational paragraph that introduces the data
below it — the kind of sentence a helpful colleague would say when
handing over a small report in a chat. The user is reading this in a chat
message, NOT a dashboard, so it must feel like a human reply.

Mandatory rules:
- Wrap it in `<section class="summary"> ... </section>` placed BEFORE the
  data section.
- Use 1 to 3 sentences total. No bullet lists, no headings, no emojis.
- Address the reader naturally. You may begin with phrases such as
  "Here are…", "I found…", "Below are…", "These are the…". Do NOT begin
  with stiff report language like "The following table shows…" or
  "The result set contains…".
- It MUST be 100% data-grounded: only state facts derivable from the
  JSON. NEVER invent names, counts, dates, statuses, regions, or trends
  that are not present in the data.
- Where natural, weave in:
    * the total number of records shown (must equal the Result row count),
    * what they are about (entities inferred from JSON keys — e.g.
      agreements, owners, countries, solutions),
    * one obvious, trivially-true observation, such as:
        - all rows share a common value (e.g. all are status
          "Implemented", all from the same region, all owned by the
          same person),
        - the data is a single record vs. a list,
        - the date range present in the data.
- It MUST NOT speculate, recommend, predict, or editorialise. No phrases
  like "this suggests", "you should", "likely", "approximately" unless
  the approximation is literally in the data.
- It MUST NOT mention "SQL", "query", "rows", "JSON", "database",
  "raw_data", or any other implementation term.
- Tone: friendly, helpful, professional — like a colleague's chat reply.
  Keep it short. Avoid corporate jargon and filler.
- Typography rules apply: 14px font, left-aligned. If you visually
  separate the summary from the table with a background tint, it MUST
  be `#8FC9FF` (no other colour).

Good example (adapt to actual data — never copy verbatim):
  <section class="summary">
    <p>Here are the 6 active agreements owned by Rahul Mehta. They are all
       currently within their effective period and span the APAC and EMEA
       regions.</p>
  </section>

Bad example (do NOT do this):
  <section class="summary">
    <p>The result set contains 6 records of active agreements with their
       respective fields as shown.</p>
  </section>

### UUID / ID-LIKE VALUES (DEFENSIVE SAFETY NET — CHAT VIEW):
Sometimes JSON values expose internal surrogate identifiers that are meaningless in chat:

- Columns named `id`, ending with `_id`, or resembling bridge keys (`sf_id`, `case_safe_id` when opaque)
  or standard UUID shapes (8-4-4-4-12 hex). **Never render these** unless the user explicitly asked for IDs.

- Very short alphanumeric **placeholder / surrogate geography codes**—single letter + digits (e.g. `c1`, `t2`),
  or ≤4-character opaque tokens in columns whose header clearly refers to geography or named entities—are **NOT acceptable**
  substitutes for joined country/account names.

- Omit such columns entirely. Never mention them in the summary. Visible cells must carry **readable business words**
  produced by upstream SQL joins (typically `…name` columns for countries and solutions).

If removing every surrogate column exhausts usable fields but row_count ≥ 1, render a factual one-line acknowledgement
instead of surrogate codes (e.g. that records exist but descriptive labels were not supplied in the dataset).

### DATA-SHAPE PRECEDENCE (READ BEFORE PICKING A RENDERING BRANCH):
Decide how to render the data using EXACTLY this priority order. The first
matching rule wins — do not consider lower rules once one matches.

1. Result row count = 0
   → Use the "Empty state" branch.
2. Data is a list / JSON array AND it contains EXACTLY ONE object
   (i.e. row count = 1 and the JSON is a list with one element)
   → DO NOT render a 1-row table. Render the SINGLE OBJECT branch
     (details card / `<dl>` layout) using that one object.
   → This is a HARD RULE: a list of length 1 is ALWAYS rendered as a card.
3. Data is a list / JSON array with 2 OR MORE objects
   → Use the "list of objects" branch (table).
4. Data is a single object (not wrapped in an array)
   → Use the "single object" branch (details card).
5. Data is a scalar (string / number / boolean)
   → Use the "scalar" branch (single value card).

#### Empty state (ONLY if Result row count = 0):
- Render an elegant "No results found" state with a brief, user-friendly message and no technical terms.
- Do NOT use this branch when row count >= 1, regardless of how minimal the data looks.
- In this branch, the SUMMARY PARAGRAPH section is OMITTED entirely.

#### If data is a list of objects (typical result set):
- This branch applies ONLY when the list contains 2 OR MORE objects.
- A 1-element list MUST go to the "single object" branch instead — see
  the DATA-SHAPE PRECEDENCE rule above.
- Render a compact, chat-friendly table inside the card.
- Wrap the `<table>` in a `<div style="overflow-x:auto">` so wide tables
  scroll horizontally inside the chat bubble instead of overflowing it.
- Use `border-collapse: collapse;` and a thin `1px` border in a soft
  neutral or `#8FC9FF` tint. Padding around `8px 10px` per cell.
- Table columns MUST be derived from the union of keys across objects,
  preserving a stable order: key order from the first object, then any
  new keys appended later.
- BEFORE choosing the columns, apply the UUID / ID-LIKE safety net rule
  above — drop columns whose name is `id`, ends with `_id`, or whose
  every value matches the UUID pattern.
- Header labels MUST be human-friendly (e.g., `leaves_count` → `Leaves
  Count`, `agreement_end_date` → `Agreement End Date`). Header cells
  may use `font-weight: 600` and a subtle `#8FC9FF` background tint.
  Do NOT use sticky positioning.
- Cell values:
  - `null` / missing: show an em dash (—).
  - booleans: show `Yes` / `No`.
  - dates / timestamps: render in a friendly form (e.g.
    `Apr 22, 2026`) when the underlying value is unambiguously a
    calendar date; otherwise leave as-is.
  - arrays/objects: render as compact pretty JSON inside `<pre>` with
    safe wrapping (`white-space: pre-wrap; word-break: break-word;`).
- Subtle UX touches (kept minimal for a chat context):
  - Optional very-light zebra striping on alternate rows.
  - A subtle hover row highlight.
  - Right-align numeric columns when obvious.
  - DO NOT use sticky table headers, fixed positioning, or page-level
    scrolling — a chat bubble is not a dashboard.

#### If data is a single object (this also covers a 1-element array):
- Render a **premium single-record "details" card** — not a sparse `<dl>`. This is the
  default for **row count = 1**; it must feel intentional, scannable, and calm (senior product
  designer quality) while staying inside the chat bubble.

**Layout & structure (mandatory):**
- After the normal `<h1>` page title and optional `<section class="summary">`, add a
  dedicated inner wrapper: `<div class="detail-sheet" role="region" aria-label="Record details">`.
- Inside `detail-sheet`, group fields into **2–4 logical sections** using
  `<section class="detail-section">` with a short heading each:
  `<h2 class="detail-section-title">…</h2>` (still **14px** via global rule; use
  `font-weight: 600` and a thin bottom border or extra `margin-top` / `padding-top` to
  separate sections — no larger font sizes).
- Within each section, use a **responsive key/value grid**:
  - Preferred: CSS `display: grid; grid-template-columns: minmax(140px, 38%) 1fr; gap: 6px 14px;`
    with each row as `<div class="kv-row">` containing
    `<span class="kv-label">` (muted colour `#5a6b7a`, `font-weight: 500`) and
    `<span class="kv-value">` (`font-weight: 400`, word-break for long strings).
  - Alternative equivalent: a styled `<dl class="kv-grid">` with `<dt>` / `<dd>` per row,
    same grid alignment. Do **not** use a one-column bullet list.

**Visual polish (still chat-safe):**
- Give `detail-sheet` a **subtle left accent**: `border-left: 3px solid #8FC9FF;`
  and `padding-left: 12px;` (or full `padding: 10px 12px;` with very light `#8FC9FF`
  `background` at ~12% opacity if you can express it — e.g. `rgba` approximating tint).
- Rows: optional zebra using **only** alternating white / `#f5fafe` (still in the `#8FC9FF`
  family) for `.kv-row` — keep contrast low.
- **Primary value emphasis**: if exactly one scalar field is obviously the main answer (e.g.
  a total, a title, status), duplicate it once in summary or give that row `.kv-value--primary`
  with `font-weight: 600` — do not inflate font size above 14px.

**Grouping heuristics (best effort from keys):**
- Identity / naming fields first section; dates second; enums/status third;
  relational / attribution last — only when inferable from key names.

**Data rules unchanged:**
- If the input was a list with exactly one object, unwrap it and render that object —
  never a `<table>` with one body row.
- Human-friendly labels (`snake_case` → Title Case).
- UUID / surrogate / `_id` / opaque code columns remain **omitted entirely** per safety rules.
- Value formatting same as tables: null → — , booleans → Yes / No , dates readable,
  nested JSON → compact `<pre>` with wrap.

#### If data is a scalar (string/number/bool):
- Render a single prominent value inside the card with a small caption
  above (derived from the user question) and the value below in
  `font-weight: 600`. Keep it compact and chat-bubble sized.

### SAFETY & HTML HYGIENE:
- Escape content that could contain `<`, `>`, `&` so the HTML does not break (treat all values as text).
- Do NOT use scripts. Do NOT use iframes. Do NOT include external links unless they are present in the data.

### OUTPUT:
- Return ONLY the final HTML document.
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

