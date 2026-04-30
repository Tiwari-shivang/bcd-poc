# BCD POC — High-Level Design (HLD)

> A FastAPI service that lets users ask business questions in plain English about
> the BCD Travel data model and get back a clean, well-formatted HTML page
> rendered from live PostgreSQL results — backed by OpenAI for both intent
> understanding (embeddings) and SQL generation.

---

## 1. What this application does (in one paragraph)

A user types a question like *"List all the active agreements whose owner is
Rahul Mehta"* into the chat endpoint. The system **figures out which database
tables are relevant**, **builds a faithful, model-driven schema description**,
asks an LLM to **write a safe `SELECT` query** for it, **executes that query**
against PostgreSQL (auto-repairing it once if it fails), and finally asks the
LLM to **convert the result rows into a polished HTML page** that the frontend
can render directly. Conversation memory is kept per-session so follow-up
questions like *"Which countries hold these agreements?"* work naturally.

There is also a small **ingestion endpoint** that loads the schema from a JSON
file, builds a textual summary of every table, embeds it with OpenAI, and
stores it into the `embeddings` table — this is what powers the per-question
table retrieval at runtime.

---

## 2. Components at a glance

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              FastAPI App                                 │
│                                                                          │
│   ┌──────────────────┐         ┌──────────────────┐                      │
│   │  /file/upload    │         │   /agent/chat    │                      │
│   │ (ingest schema)  │         │ (answer queries) │                      │
│   └────────┬─────────┘         └────────┬─────────┘                      │
│            │                            │                                │
│            ▼                            ▼                                │
│   ┌──────────────────┐         ┌──────────────────┐                      │
│   │  FileService     │         │  AgentService    │                      │
│   │ (build summary,  │         │ (orchestration)  │                      │
│   │  embed, store)   │         │                  │                      │
│   └────────┬─────────┘         └────────┬─────────┘                      │
│            │                            │                                │
│            │      ┌─────────────────────┼─────────────────────┐          │
│            │      ▼                     ▼                     ▼          │
│            │  helpers/agent_helper  helpers/schema_context  helpers/     │
│            │  (LLM wrappers)        (FK-aware schema)        prompts     │
│            │      │                     │                     │          │
│            ▼      ▼                     ▼                     ▼          │
│   ┌────────────────────────────────────────────────────────────────────┐ │
│   │             SQLAlchemy models  +  Postgres + pgvector              │ │
│   │  accounts, agreements, gcn, program_sol, countries, annual_vol,    │ │
│   │  tool_service, owners, owner_permissions, permissions, embeddings  │ │
│   └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                        OpenAI (embeddings + GPT-4o-mini)
```

### Layered structure

| Layer            | Folder            | Responsibility                                           |
| ---------------- | ----------------- | -------------------------------------------------------- |
| API / Controllers| `controllers/`    | FastAPI routers, HTTP request/response                   |
| DTOs             | `DTOs/`           | Pydantic request/response models                         |
| Services         | `services/`       | Orchestration & business logic                           |
| Helpers          | `helpers/`        | LLM wrappers, schema context, SQL post-processing, prompts |
| Models           | `models/`         | SQLAlchemy ORM models (the single source of truth)       |
| Config           | `config/`         | OpenAI client init                                       |
| Database         | `database.py`     | Engine, session factory, `get_db` dependency             |
| Entry point      | `main.py`         | App bootstrap, router registration, CORS                 |

---

## 3. The two main flows

There are exactly two user-facing flows in this service.

### Flow A — Ingest the schema once (`POST /file/upload`)

This is what makes runtime retrieval possible. A schema JSON file (one entry
per table, with columns, types, and relationships) is uploaded once, and the
service turns each table into an embedding row.

```
┌──────────────┐
│  Client      │  multipart/form-data: file (schema.json) + description
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ /file/upload     │
│ FileService      │
│  .upload_file()  │
└──────┬───────────┘
       │ for each table in schema.json
       ▼
┌──────────────────────────┐
│ build_summary(table)     │  rich text:
│ - columns (type, enums,  │  "Table: agreements
│   PK/FK, constraints)    │   Columns:
│ - relationships          │   - id (uuid; Primary Key)
└──────┬───────────────────┘   - status (enum; values: ...)
       │                        Relationships: ..."
       ▼
┌──────────────────────────┐
│ OpenAI Embeddings API    │  text-embedding-3-small → 1536-d vector
│ helpers.generate_embeddings()
└──────┬───────────────────┘
       ▼
┌──────────────────────────┐
│ Postgres (pgvector)      │
│ INSERT INTO embeddings   │  data=vector, key=table_name,
│   (data, key, content,   │  content=summary, description=upload tag
│    description)          │
└──────────────────────────┘
```

**Why summaries (not just column names)?** The original POC embedded only
column names, which made retrieval blind to types and enum values. The
current `build_summary` emits type, enum values, PK/FK and relationships in a
self-contained block — much richer signal per vector → far better recall.

### Flow B — Answer a user question (`POST /agent/chat`)

This is the heart of the system. End-to-end, a single chat call goes through
**seven well-defined steps**.

```
                 ┌────────────────────────────────────────────┐
                 │ 1. Resolve / create session_id (cookie)    │
                 │  ─ if missing, generate uuid4 and Set-Cookie│
                 │  ─ track in active_users[]                 │
                 └────────────────┬───────────────────────────┘
                                  │
                 ┌────────────────▼───────────────────────────┐
                 │ 2. Load conversation history for session   │
                 │   from last_contexts[]                     │
                 └────────────────┬───────────────────────────┘
                                  │
                 ┌────────────────▼───────────────────────────┐
                 │ 3. Embed user message → vector             │
                 │  pgvector cosine search → top-10 tables    │
                 │  + dedupe by table key                     │
                 │  + always union "anchor" tables            │
                 │    (accounts, agreements)                  │
                 │  → seed table list                         │
                 └────────────────┬───────────────────────────┘
                                  │
                 ┌────────────────▼───────────────────────────┐
                 │ 4. Build schema context (helpers/schema_context)│
                 │  ─ FK-graph 1-hop expansion (bridge tables)│
                 │  ─ Per-table columns with types & enums    │
                 │  ─ Explicit "Relationships" block (FK edges)│
                 └────────────────┬───────────────────────────┘
                                  │
                 ┌────────────────▼───────────────────────────┐
                 │ 5. SQL generation (helpers.llm_response)   │
                 │  prompts.get_query_prompt(                 │
                 │    context, message, last_context)         │
                 │  ─ enforces SELECT-only, enum casing,      │
                 │    JOIN paths, business glossary, "per X"  │
                 │  ─ post-process: normalize_enum_literals   │
                 └────────────────┬───────────────────────────┘
                                  │
                 ┌────────────────▼───────────────────────────┐
                 │ 6. Execute SQL with auto-repair            │
                 │   (AgentService._execute_with_repair)      │
                 │  ─ on DBAPIError: rollback, ask LLM to fix │
                 │    using prompts.get_fix_query_prompt      │
                 │  ─ bounded retries (MAX_SQL_REPAIR_ATTEMPTS)│
                 │  ─ returns rows OR None                    │
                 └────────────────┬───────────────────────────┘
                                  │
                 ┌────────────────▼───────────────────────────┐
                 │ 7. Render HTML response                    │
                 │   (helpers.generate_normalized_llm_response)│
                 │  ─ rows → list[dict] (clean JSON)          │
                 │  ─ row_count + JSON sent to LLM via        │
                 │    prompts.get_natural_lang_prmpt          │
                 │  ─ strict format: 14px, left-aligned,      │
                 │    optional bg only #8FC9FF, no fences     │
                 │  ─ _strip_markdown_fences as safety net    │
                 │                                            │
                 │  Persist this turn to last_contexts[]      │
                 └────────────────┬───────────────────────────┘
                                  │
                                  ▼
                       Response: { "response": "<!doctype html>..." }
```

---

## 4. Data layer

### 4.1 Database
PostgreSQL with the **pgvector** extension. Connection string is read from
`.env` (`DB_URL`). Engine and session factory live in `database.py` and are
exposed via `get_db()` (used as a FastAPI dependency).

### 4.2 Domain model (the business tables)

| Table             | Purpose                                                       | Key relationships |
| ----------------- | ------------------------------------------------------------- | ----------------- |
| `owners`          | People (account owners, VPs, RAMs, marketers, etc.)           | central reference |
| `accounts`        | Customer/Company records ("Customer" in business language)    | many FKs to `owners` |
| `gcn`             | Global Customer Number records belonging to an account        | `account_id → accounts.id` |
| `agreements`      | Contracts attached to an account; can be tied to a GCN        | `account_id`, `gcn_id`, `owner_id`, `agreement_vp` |
| `countries`       | Country rows belonging to an agreement                        | `agreement_id` |
| `annual_vol`      | Annual transaction/volume figures per country / agreement     | `country_id`, `agreement_id` |
| `program_sol`     | "Solutions" / programs deployed under an agreement            | `agreement_id`, `country_id`, `tool_service_id` |
| `tool_service`    | Tools/services catalogue                                      | `product_marketer → owners.id` |
| `permissions`     | Permission catalogue                                          | — |
| `owner_permissions` | join table owners ↔ permissions                             | composite PK |
| `embeddings`      | Vector index of table summaries                               | `data` is `Vector(1536)` |

> **Anchor tables**: `accounts` and `agreements` sit at the structural center
> of the graph. The agent always force-includes them in the rendered schema
> context so multi-hop joins through them are always possible.

### 4.3 Enums
Several columns are PostgreSQL enums (e.g. `program_sol.status` ∈
`{Implemented, De-Implemented, In Scope, In Vetting, Never Implemented}`).
Two facts about enums shape the design:

1. They are **case-sensitive** in PostgreSQL.
2. LLMs commonly emit them in the wrong case.

So we have a dedicated post-processor (`helpers/sql_normalizer.py`) that
introspects every `Enum` column once, builds a lower-case → canonical
mapping, and rewrites any matching string literal in generated SQL to the
exact casing the database expects. This runs *after* the LLM produces SQL
but *before* execution.

---

## 5. The agent pipeline, step by step

The orchestrator is `AgentService.get_agent_response` in
`services/agent_service.py`. Each numbered step below maps directly to a
section in that method.

### Step 1 — Sessions and per-user memory

- Read `session_id` from the request **cookie**.
- If absent, generate `uuid.uuid4()` and write it back via `Set-Cookie`
  (`HttpOnly`, `SameSite=Lax`).
- Track every seen session_id in a process-local list `active_users`.

This is intentionally simple (no Redis/DB persistence) for the POC — the
contract is identical in shape to a production session store.

### Step 2 — Load conversation history

Per-session conversation memory is kept in `last_contexts`, shaped as:

```python
[
    {
        "session_id": "...",
        "previous_responses": [
            {"user_query": "...", "agent_response": [ ...rows... ]},
            ...
        ],
    },
    ...
]
```

`_get_previous_responses(session_id)` returns the list for the current user
(or `[]` for first-time visitors). This list is then forwarded to **both**
the SQL generator and the HTML renderer so follow-up questions like *"Which
countries hold these agreements?"* can resolve back-references.

### Step 3 — Retrieve relevant tables (vector search)

1. Embed the user message via `text-embedding-3-small` (1536-d vector).
2. `helpers.search_data_embeddings()` runs a `cosine_distance` ORDER BY,
   `LIMIT 10`, against the `embeddings` table.
3. Caller de-duplicates by `key` (multiple summaries can share a key) and
   keeps similarity order.
4. Always union in `CORE_ANCHOR_TABLES = ("accounts", "agreements")` —
   without these, multi-hop questions would be impossible to answer because
   the bridging tables would be absent from the prompt.

### Step 4 — Build schema context (the most important helper)

`helpers/schema_context.build_schema_context(table_names)` produces the
machine-readable block the LLM uses to write SQL. Three properties make it
robust:

1. **Single source of truth.** It walks the SQLAlchemy `BaseModel.registry`
   directly — types, enums, PKs, FKs are always accurate and can never
   drift from the running models.
2. **FK-graph 1-hop expansion.** Given a seed of tables, it pulls in every
   directly-related table (parents *and* children) so a *bridge* such as
   `agreements` is always present even when the user never said the word
   "agreement".
3. **Explicit relationships block.** At the bottom of the rendered context
   it writes a flat, padded list:

   ```
   ## Relationships (Foreign Keys)

   - program_sol.agreement_id  -> agreements.id
   - agreements.gcn_id         -> gcn.id
   - gcn.account_id            -> accounts.id
   ```

   The LLM no longer has to reconstruct join paths from per-column metadata.

### Step 5 — Generate SQL (with conversation awareness)

`helpers.llm_response` uses GPT-4o-mini (`temperature=0.2`) with the prompt
returned by `prompts.get_query_prompt`. The prompt enforces, among other
things:

- **SELECT-only** output, no markdown, single statement.
- **Schema fidelity**: only columns that exist; column ownership rule.
- **ENUM strictness**: must match schema casing verbatim, otherwise omit.
- **String comparisons** use `IN (...)`, never `=`.
- **Active agreement** semantics (date predicate on `agreements`).
- **JOIN-PATH discovery** through the Relationships block (with a worked
  multi-hop example — solutions per GCN for a customer).
- **Business glossary**: Customer → `accounts`, GCN → `gcn`, Solution →
  `program_sol`, etc.
- **Aggregation semantics** for "per X" / "for each X" / "by X".
- **Conversation history block** with each prior turn's user_query and
  result data (as clean JSON), so the model can extract IDs and use
  `IN (...)` filters for follow-ups.

The output is then run through `sanitize_generated_query` which strips
whitespace and normalises enum casing.

### Step 6 — Execute with auto-repair

`AgentService._execute_with_repair`:

1. `db.execute(text(sql)).mappings().all()` → list of `RowMapping`.
2. On any `DBAPIError`:
   - `db.rollback()` (otherwise the connection stays aborted).
   - Extract a concise driver message via `_extract_db_error`.
   - If under `MAX_SQL_REPAIR_ATTEMPTS`, call
     `helpers.llm_fix_response` (which uses `prompts.get_fix_query_prompt`)
     with the schema, user question, failing SQL and the database error,
     get a corrected query, and retry.
3. Bail out after the cap; return `None` (the controller responds
   "No search result for this").

This is what turns occasional LLM JOIN/column slips into a transparent
self-healing loop — without ever falling into an infinite retry.

### Step 7 — Render to HTML

After execution succeeds, the rows are normalised once at the source:
`serialized_data = [dict(row) for row in raw_data]`. From that point onward,
**everything downstream sees clean Python dicts** — both the LLM call and
the conversation-memory write.

`helpers.generate_normalized_llm_response`:

- Computes an authoritative `row_count` (`len` for lists, `0` for `None`,
  `1` for scalars).
- Serialises `data` to **real JSON** with `json.dumps(default=str, indent=2)`
  so `Decimal`, `date`, `UUID`, etc. never break the prompt.
- Calls `prompts.get_natural_lang_prmpt(user_query, raw_data=json,
  last_context=..., row_count=...)`.
- Strips any markdown fences the model may add as a defensive safety net
  (`_strip_markdown_fences`).

The HTML prompt enforces a hard, character-level contract:

- The very first character must be `<` (start of `<!doctype html>`); the
  very last must be `>` (close of `</html>`); no fences, no extra prose.
- Every font size is `14px` (set globally with a `*, *::before, *::after`
  override so heading defaults can't override it).
- Text is left-aligned.
- Any background colour, if used, must be `#8FC9FF`.
- The `row_count` field is the **single source of truth** for emptiness.
  When it's `≥ 1`, "No results" is forbidden; the model must render the
  data — even a single row.

Finally, `_save_to_context(session_id, user_query, serialized_data)` appends
the new turn to `last_contexts` so it becomes available as memory for the
next question.

---

## 6. Prompt engineering layers

Three prompts power the system, all in `helpers/prompts.py`. Each is a pure
function — easy to inspect and unit-test.

| Prompt                       | Purpose                                                                 |
| ---------------------------- | ----------------------------------------------------------------------- |
| `get_query_prompt`           | Generate a safe SELECT from the user message + schema + history         |
| `get_fix_query_prompt`       | Repair a SELECT that just failed against the live database              |
| `get_natural_lang_prmpt`     | Convert result rows into a polished HTML page                           |

Three things make these prompts production-grade rather than ad-hoc:

1. **Hard rules with examples.** Every constraint is written in imperative
   form, with positive *and* negative examples (e.g. "Correct: `IN ('APAC')`
   / Incorrect: `= 'APAC'`").
2. **Explicit business glossary + multi-hop worked example.** Domain terms
   ("Customer", "GCN", "solution") are mapped to tables/columns, and one
   complete 4-table JOIN ("solutions per GCN for a customer") is shown
   end-to-end in SQL inside the prompt.
3. **Output contracts.** The HTML prompt contains a *character-level*
   contract (first char `<`, last char `>`) plus an authoritative
   `row_count` signal that strictly forbids false empty-state rendering.

---

## 7. Concrete walk-through of the failing-then-fixed query

User: *"List all the solutions that have been implemented per GCN for a
Customer."*

1. **Embeddings** retrieve `program_sol`, `gcn`, possibly `tool_service`.
2. **Anchor union** adds `accounts`, `agreements`.
3. **FK-graph expansion** confirms `agreements` (it bridges `gcn` ↔
   `program_sol` via `agreements.gcn_id` and `program_sol.agreement_id`).
4. **Relationships block** prints the entire 4-edge join chain in plain
   text.
5. **SQL prompt** activates the *Aggregation semantics* rule ("per X"),
   *Business glossary* (Customer → `accounts`, GCN → `gcn`, Solution →
   `program_sol`), and *Multi-hop worked example*. The model emits:

   ```sql
   SELECT a.name AS customer_name,
          g.client_name AS gcn,
          ps.name AS solution_name
   FROM program_sol ps
   JOIN agreements ag ON ag.id = ps.agreement_id
   JOIN gcn g         ON g.id  = ag.gcn_id
   JOIN accounts a    ON a.id  = g.account_id
   WHERE ps.status IN ('Implemented')
   ORDER BY a.name, g.client_name, ps.name;
   ```

6. **Enum normaliser** confirms `'Implemented'` casing.
7. **Execution** returns rows; if any column-ownership issue appears, the
   repair loop fixes it once.
8. **HTML renderer** receives `row_count = N`, real JSON, and the per-row
   payload — produces a 14px, left-aligned, optionally `#8FC9FF`-tinted
   table with sticky headers.

---

## 8. Cross-cutting concerns

### 8.1 Configuration & secrets
- `.env` holds `DB_URL` and `OPEN_AI_KEY` (used by `database.py` and
  `config/openai_config.py`).
- No secret is ever logged or sent back to the client.

### 8.2 CORS
`main.py` allows `http://localhost:5173/` for the local React dev server,
with credentials on (so the `session_id` cookie round-trips).

### 8.3 Safety
- The SQL prompt **bans** non-SELECT statements and multi-statement
  payloads.
- `db.rollback()` is mandatory on every DBAPIError to keep the connection
  alive after a bad query.
- All result rows are escaped at render time (HTML hygiene rule in the
  renderer prompt — values are treated as text).

### 8.4 Testability
The codebase has unit tests for the heaviest helpers:

- `tests/test_schema_parser.py` — schema rendering.
- `tests/test_validator_and_compiler.py` — SQL post-processing.
- `tests/test_retrieval.py` — embedding retrieval logic.

Pure functions (prompts, schema_context, sql_normalizer) and lean services
make this straightforward.

### 8.5 Observability
Lightweight logging is via `print()` at the moment (distance, generated
SQL, raw data). Easy to upgrade to `logging` with structured fields without
changing flow.

---

## 9. Why each design decision was made

| Decision | Why it matters |
| -------- | -------------- |
| **SQLAlchemy models = single source of truth** | Schema description (types, enums, FKs) is generated, never hand-written. The LLM cannot hallucinate columns that don't exist. |
| **pgvector for retrieval** | Cheap, in-process semantic search over schema summaries — no extra infra. |
| **FK-graph expansion + Relationships block** | Multi-hop joins through *bridge* tables (e.g. `agreements` between `gcn` and `program_sol`) are now always expressible. |
| **Auto-repair loop with bounded retries** | Recovers from common LLM slips (column ownership, casing, missing JOIN) without any human intervention or infinite loops. |
| **Enum normalizer** | Closes the LLM↔Postgres case mismatch hole that would otherwise produce `InvalidTextRepresentation` errors at runtime. |
| **Per-session memory in `last_contexts`** | Enables natural follow-ups ("from those agreements…") without re-asking the user to repeat context. |
| **JSON-serialised data + explicit `row_count`** | Removes ambiguity around RowMapping reprs and stops the renderer from misclassifying a populated result as empty. |
| **HTML output with strict format contract** | Frontend can render the response **as-is**, no ad-hoc client formatting; consistent UX (14px, left-aligned, `#8FC9FF`). |
| **Markdown-fence stripper** | Defensive belt-and-braces guarantee — even if the model slips and wraps output in ` ```html `, the API never returns it. |

---

## 10. Sequence diagram (chat happy path)

```
Client      Controller        AgentService          OpenAI            Postgres
  │              │                 │                  │                  │
  │ POST /chat   │                 │                  │                  │
  ├─────────────▶│                 │                  │                  │
  │              │ get_agent_resp ▶│                  │                  │
  │              │                 │ resolve session  │                  │
  │              │                 │ load history     │                  │
  │              │                 │ embed message ──▶│                  │
  │              │                 │◀──── vector ─────│                  │
  │              │                 │                  │                  │
  │              │                 │ cosine search ───────────────────▶ │
  │              │                 │◀── top tables ─────────────────────│
  │              │                 │                  │                  │
  │              │                 │ build context (FK expand + rels)  │
  │              │                 │                  │                  │
  │              │                 │ get_query_prompt + history ─────▶ │
  │              │                 │ chat.completions.create ──────▶ OpenAI
  │              │                 │◀───── SELECT SQL ───────── OpenAI
  │              │                 │ enum-normalise SQL                │
  │              │                 │                  │                  │
  │              │                 │ execute SQL ─────────────────────▶│
  │              │                 │◀── rows OR DBAPIError ────────────│
  │              │                 │   (on error: ask LLM to fix, retry)│
  │              │                 │                  │                  │
  │              │                 │ rows → list[dict]                  │
  │              │                 │ get_natural_lang_prmpt + JSON ──▶ OpenAI
  │              │                 │◀────── HTML ────────────── OpenAI
  │              │                 │ strip markdown fences              │
  │              │                 │ persist to last_contexts           │
  │              │◀── HTML ────────│                  │                  │
  │ {response} ◀─│                 │                  │                  │
  │              │                 │                  │                  │
```

---

## 11. Future work (out of scope for the POC)

- Move `active_users` / `last_contexts` to a real session store (Redis).
- Replace `print` logging with structured logs + correlation IDs.
- Cap conversation history size (sliding window of N turns) for prompt
  budget control.
- Add row-level access control if the customer set ever grows beyond demo
  data.
- Optional: stream the HTML response back to the client (Server-Sent
  Events) so big result sets render progressively.
- Add Alembic migrations now that the model count has stabilised.
