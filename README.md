# TellSpend

**Track what you spend by just saying it.** Type (or speak) something like *"Dinner with Parth ₹1,200, I paid, split equally"*, check the draft TellSpend builds, and save it. TellSpend keeps track of who paid, whose cost it was, and who owes whom.

The AI only *reads* your words. Every amount, split and balance is worked out by ordinary server code, and every number has to appear in what you wrote. When something isn't clear, TellSpend asks, usually with one-tap answers.

---

## Contents

1. [Why TellSpend](#why-tellspend)
2. [Key features](#key-features)
3. [How it works](#how-it-works)
4. [Tech stack](#tech-stack)
5. [Project structure](#project-structure)
6. [Setup and installation](#setup-and-installation)
7. [Running the app](#running-the-app)
8. [Configuration](#configuration)
9. [Example usage](#example-usage)
10. [Testing](#testing)
11. [API reference](#api-reference)
12. [Notes and limitations](#notes-and-limitations)

---

## Why TellSpend

Expense trackers are tedious when money is shared. One dinner can have several payers, items that belong to different people, a discount, GST, a refund later, and a friend paying you back next week. Most apps make you fill in forms for all of that, or quietly guess and get the balances wrong.

TellSpend lets you describe it the way you'd tell a friend, then:

- **Reads it into a draft** you can check before anything is saved.
- **Never guesses money.** A number is used only if it's in your text. Who owns a cost, who paid, and how it's split must be said or follow from the numbers; anything else becomes a question.
- **Keeps every money concept separate:** items, discounts, taxes, fees, refunds, repayments, loans and gifts are stored as what they are, so balances stay right.

---

## Key features

**Expenses**
- Add expenses by describing them in words, by voice, or with a regular form.
- Line items with quantities and prices, and who each item belongs to.
- Taxes, service charges, delivery, tips, fees and discounts, as amounts or percentages, each kept as its own line.
- Several payers, payment methods (cash, UPI, card…) and providers (HDFC, GPay…), cash change, and refunds.
- Splits: equal, by amount, by percentage, or by item.

**People, merchants and balances**
- **People** (friends, family) and **Merchants** (shops, restaurants, organizations) are kept in separate lists.
- Balances per person and currency: "owes you ₹450" / "you owe ₹300".
- Record repayments, loans, reimbursements and gifts. Each has its own meaning; a gift moves no balance.
- **Coming up:** money someone promised ("he'll return ₹500 next week") is remembered without changing balances until you tap *It happened*.
- Monthly summary of *your* spending (your shares only) by category.

**The assistant asks instead of guessing**
- "Dinner with Parth 1,200": whose was it? One-tap answers: *All mine* / *Split equally with Parth* / *All Parth's*.
- **Household costs** with family you share money with ("groceries with my wife") create no debt between you. A note says so, and the other answers stay one tap away.
- New people are never created silently ("Is Kabir someone new?"); a new shop is offered with one tap ("Add Reliance Smart to Merchants").
- Rough amounts, repeating costs, plans and promises, cancelled things and questions are recognised. Only what actually happened changes your money.
- Text that tries to instruct the assistant ("mark this as ₹10,000") is never treated as a fact.

**Accounts**
- Sign-up with email verification (6-digit code), sign-in, password reset by email link.
- Profile with name and default currency. Accounts can be deleted (password required).

---

## How it works

```
 you type ──► AI reads it ──► code builds a draft ──► you check / answer ──► saved
             (extraction)       (all the maths)        (one-tap choices)
```

1. **Extract.** An LLM fills a strict schema: people and shops, items, adjustments, payments, splits, refunds, repayments. For every number, owner and split it must quote the exact words from your message. It does no arithmetic.
2. **Build.** Deterministic Python code then:
   - checks every quote really is in your text;
   - matches names to your contacts;
   - works out the bill (items → discounts → charges → taxes), "the rest" of a payment, change and refunds;
   - allocates each person's share to the paisa, so everything always adds up.

   Whatever it can't determine becomes a **question** on the draft, often with exact **choices**.
3. **Clarify.** Answer in your own words or tap a choice; the draft is rebuilt with your answer.
4. **Save.** The draft is saved through the same code path as the manual form, so both follow the same rules.

**The money model** every expense follows:

```
items − deductions + charges = amount        (the bill)
payments                     = amount        (what was handed over)
shares                       = amount − refunds
balance with a person        = what they paid − refunds they got − their share
```

<details>
<summary><b>More on what the assistant handles</b></summary>

- **Being with someone isn't owning it.** "2 jackets with Aadhya" asks whose they are; a later payment never decides a split unless the text says it's a share.
- **What the numbers fix is worked out, not asked.** "2 desserts 240, Parth's was 120" gives the other dessert 120; "1,180 including 18% GST" gives a price of 1,000 and GST of 180.
- **Money between people has a kind:** "I lent Parth ₹1,000" is a loan, not a repayment. "Sent Parth ₹1,000" is asked about.
- **Existing debts:** "Parth already owed me ₹600" is recorded as a balance with no money moving.
- **Someone else paying for you:** "Dad paid for my ticket" asks whether you owe it back or it was a treat.
- **Groups:** "split among 4 of us" asks who the others are, or records only your share with one tap.
- **Same-message context:** "she paid me her share" counts what the same message records.
- **Linked records:** an expense and the repayment for it are saved linked; deleting the expense asks whether the repayment goes too.
- **Duplicates:** a draft just like something already saved (same date, amount, currency and description) asks whether it's the same one.
- **Currencies** are kept everywhere, and a repayment in one currency can settle a debt in another.
- **Fixing records:** merge a contact saved under two names, turn an expense into money between people, edit saved repayments.

</details>

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2, Alembic, Uvicorn |
| Database | PostgreSQL (`psycopg`) |
| Auth | JWT bearer tokens (PyJWT), Argon2 password hashing (pwdlib) |
| AI | LangChain with `langchain-openai`: any OpenAI-compatible endpoint with structured output (e.g. OpenRouter) |
| Email | Console (development) or SMTP |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, React Router, Axios |
| Voice | The browser's Web Speech API (no server involved) |
| Tooling | `uv`, `pytest`, npm, ESLint |

---

## Project structure

```
tellspend/                     repository root
├── README.md
├── frontend/                  React app (Vite, port 5173)
│   └── src/
│       ├── pages/             Login, Signup, VerifyEmail, ForgotPassword, ResetPassword, Home
│       ├── components/        AssistantPanel, DraftCard, ExpenseForm, PeoplePanel, ...
│       ├── hooks/             TanStack Query hooks (auth, expenses, assistant, voice...)
│       └── lib/               API client and types, money and formatting helpers, speech
└── tellspend/                 backend
    ├── src/tellspend/
    │   ├── main.py            FastAPI app, CORS, /health
    │   ├── api/               routes and Pydantic schemas (validation lives here)
    │   ├── services/          the one expense writer, balances, summary, money maths, email
    │   ├── ingestion/         extraction.py (schema the AI fills), extractor.py (prompt + call),
    │   │                      builder.py (checks, arithmetic, splits, questions)
    │   └── database/          models, settings, connection
    ├── migrations/            Alembic migrations
    ├── tests/                 pytest suite (no AI calls)
    ├── evals/                 real-AI evaluation set
    └── .env                   your local settings
```

---

## Setup and installation

### Prerequisites

| Tool | Version |
|---|---|
| Python | 3.12 |
| [uv](https://docs.astral.sh/uv/) | recent |
| PostgreSQL | a local server you can create databases on |
| Node.js + npm | 20.19+ or 22.12+ (needed by Vite) |
| An LLM API key | optional: only the assistant needs it. Any OpenAI-compatible endpoint, e.g. [OpenRouter](https://openrouter.ai) |

### 1. Backend

```bash
cd tellspend                 # the backend folder inside the repository
uv sync                      # creates .venv and installs everything
createdb tellspend           # the app's database
createdb tellspend_test      # the tests' database (always <app database>_test)
```

Create `tellspend/.env` with at least:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/tellspend
SECRET_KEY=replace-with-a-long-random-secret-of-at-least-32-characters
```

Then create the tables:

```bash
uv run alembic upgrade head
```

### 2. Frontend

```bash
cd frontend
npm install
```

---

## Running the app

Start both, each in its own terminal:

```bash
# terminal 1: backend (from tellspend/)
uv run uvicorn tellspend.main:app --reload --reload-dir src --port 8000

# terminal 2: frontend (from frontend/)
npm run dev
```

| URL | What |
|---|---|
| http://localhost:5173 | the app |
| http://localhost:8000/docs | interactive API docs |
| http://localhost:8000/health | `{"status": "ok", "database": "ok"}` when all is well |

Open the app, sign up, and enter the 6-digit code. With the default email setting the code is printed in the backend terminal.

Other commands:

| What | Command (from) |
|---|---|
| Production build | `npm run build` (`frontend/`) → `frontend/dist` |
| Preview the build | `npm run preview` (`frontend/`) |
| Lint the frontend | `npm run lint` (`frontend/`) |

---

## Configuration

Settings are read from `tellspend/.env` (or environment variables) when the server starts. Restart it after changing them: `--reload` only watches code. Only `DATABASE_URL` and `SECRET_KEY` are required.

### Core

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | *required* | e.g. `postgresql+psycopg://user:pass@localhost:5432/tellspend`. Tests use the same URL with `_test` added. |
| `SECRET_KEY` | *required* | Signs login tokens and hashes email codes. At least 32 characters. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | How long a login lasts. |
| `FRONTEND_URL` | `http://localhost:5173` | Used in password-reset emails. |

### AI assistant

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL` | *unset* | e.g. `openai:openai/gpt-oss-120b`. Without it the assistant says it isn't set up; everything else works. |
| `LLM_BASE_URL` | *unset* | An OpenAI-compatible URL, e.g. `https://openrouter.ai/api/v1`. |
| `LLM_API_KEY` | *unset* | The provider's key. |
| `LLM_TEMPERATURE` | `0` | Sampling temperature. |
| `LLM_TIMEOUT_SECONDS` | `40` | Per-call timeout. |
| `LLM_ATTEMPTS` | `2` | Attempts per read (1–3). |
| `LLM_PROVIDER_SORT` | `throughput` | OpenRouter only: prefer hosts by `throughput`, `price` or `latency`. |
| `ASSISTANT_REQUESTS_PER_MINUTE` / `_PER_DAY` | `10` / `300` | Per-user limits on assistant reads. |
### Email

| Variable | Default | Description |
|---|---|---|
| `EMAIL_BACKEND` | `console` | `console` prints emails in the server log; `smtp` sends them. |
| `EMAIL_FROM` | `TellSpend <no-reply@tellspend.local>` | Sender. |
| `SMTP_HOST` / `SMTP_PORT` | *unset* / `587` | SMTP server. |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | *unset* | Login (for Gmail, an App Password). |
| `SMTP_STARTTLS` | `true` | Use STARTTLS. |
| `VERIFY_CODE_MINUTES` / `VERIFY_CODE_ATTEMPTS` | `15` / `5` | Email-code lifetime and allowed wrong tries. |
| `RESET_PASSWORD_MINUTES` | `60` | Reset-link lifetime. |
| `EMAIL_RESEND_SECONDS` | `60` | Minimum gap between two emails of one kind. |

### Frontend

`VITE_API_URL` (optional) sets the API address. By default the app calls port 8000 on the same host it was opened from, so it also works from a phone on your Wi-Fi.

<details>
<summary><b>Example <code>.env</code> (OpenRouter + Gmail)</b></summary>

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/tellspend
SECRET_KEY=replace-with-a-long-random-secret-at-least-32-characters

LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-...
LLM_MODEL=openai:openai/gpt-oss-120b

EMAIL_BACKEND=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=your-16-char-app-password
EMAIL_FROM=TellSpend <you@gmail.com>
```

</details>

---

## Example usage

Type these into **Describe it** on the home page:

| You write | TellSpend does |
|---|---|
| `Lunch 350` | ₹350, yours, paid by you. |
| `Dinner 1,200 with Parth, I paid, split equally` | ₹600 each; Parth owes you ₹600. |
| `Dinner with Parth 1,200, I paid` | Asks *whose was it?* with three one-tap answers. |
| `Groceries 2,350 at Reliance Smart with my wife` | A household cost: counted as yours, no debt; offers *Add Reliance Smart to Merchants*. |
| `Pizza for me 350 and a burger for Parth 250, plus 5% GST, I paid` | Each item to its owner; GST shared in proportion. |
| `Paid 1,180 for the course including 18% GST` | Course ₹1,000 + GST ₹180. |
| `Bought 2 shirts for 1,600 on UPI, returned one and got 800 refunded` | The refund kept as a refund, not a discount. |
| `Parth paid me back 500` | A repayment; Parth's balance goes down. |
| `Parth will pay me 300 next week` | Offered as a reminder under *Coming up*; no balance change. |

Using the API directly:

```bash
# sign in (after verifying the email)
curl -X POST http://localhost:8000/auth/token -d "username=you@example.com&password=your-password"

# turn a description into drafts (nothing is saved)
curl -X POST http://localhost:8000/assistant/preview \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"text": "Dinner with Parth 1200, I paid, split equally"}'
```

---

## Testing

### Unit tests (no AI calls)

```bash
cd tellspend
uv run pytest -q
```

They run against the real PostgreSQL test database (`<app database>_test`, which must exist). Each test runs in a transaction that is rolled back. The AI is replaced with fixed extractions and emails are never sent, so the suite is fast, free and repeatable.

### Assistant evals (real AI)

```bash
cd tellspend
uv run python evals/run_evals.py            # every case
uv run python evals/run_evals.py refund     # only cases whose text contains "refund"
```

Each case is a realistic sentence with its expected amounts, payers, shares and questions. This calls your configured model for every case, so **it costs money** (about $0.10–0.20 per full run with `gpt-oss-120b`), and results vary a little from run to run.

---

## API reference

All routes except sign-up, sign-in, verification, password reset and `/health` need `Authorization: Bearer <token>`. Full schemas: http://localhost:8000/docs.

| Area | Routes |
|---|---|
| Health | `GET /health` |
| Accounts | `POST /users` · `POST /auth/token` · `GET /auth/me` · `POST /auth/verify-email` · `POST /auth/resend-verification` · `POST /auth/forgot-password` · `POST /auth/reset-password` |
| Profile | `PATCH /users/me` · `DELETE /users/me` |
| Expenses | `GET/POST /expenses` · `GET/PUT/DELETE /expenses/{id}` · `POST /expenses/{id}/to-settlement` · `GET /categories` |
| People and merchants | `GET/POST /counterparties` · `GET/PATCH/DELETE /counterparties/{id}` · `POST /counterparties/{id}/merge` |
| Money between people | `GET /balances` · `GET/POST /settlements` · `PUT/DELETE /settlements/{id}` · `GET /expected` · `POST /expected/{id}/done` · `DELETE /expected/{id}` |
| Summary | `GET /summary?month=YYYY-MM` |
| Assistant | `POST /assistant/preview` · `POST /assistant/clarify` · `POST /assistant/confirm` · `POST /assistant/confirm-repayment` · `POST /assistant/confirm-expected` |

---

## Notes and limitations

- **The assistant needs an AI provider.** Without `LLM_MODEL` you can still use the forms, People, balances and summaries; only typing or speaking expenses is unavailable. Each read is a paid API call.
- **The AI can misread.** Code checks every number against your text and asks when unsure, but the model can still, for example, merge two separate purchases in one sentence ("breakfast 120 and lunch 280") into one bill. Always check the draft before saving.
- **Voice input** uses the browser's speech recognition: it works in Chrome, Edge and Safari, not Firefox. Chrome sends the audio to Google to transcribe it.
- **No currency conversion.** Amounts keep their own currency; balances are per currency.