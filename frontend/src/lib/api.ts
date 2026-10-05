/**
 * The one HTTP client every API call goes through, plus the auth calls.
 */

import axios from "axios";
import { todayISO } from "./format";
import { clearToken, getToken } from "./token";
import type { MoneyKind } from "./moneyKinds";

const baseURL =
  import.meta.env.VITE_API_URL ??
  `http://${window.location.hostname}:8000`;

export const api = axios.create({
  baseURL,
  timeout: 15000,
});

// Send the saved token with every request.
api.interceptors.request.use((config) => {
  const token = getToken();

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error)) {
      const isLoginAttempt = error.config?.url === "/auth/token";

      if (error.response?.status === 401 && !isLoginAttempt) {
        clearToken();

        if (window.location.pathname !== "/login") {
          window.location.assign("/login");
        }
      }
    }

    return Promise.reject(error);
  },
);


export type Health = {
  status: string;
  database: string;
};

export type User = {
  id: number;
  email: string;
  name: string;
  default_currency: string;
  email_verified: boolean;
};

export type SignupInput = {
  email: string;
  name: string;
  password: string;
  default_currency: string;
};

type Token = {
  access_token: string;
  token_type: string;
};

export async function getHealth(): Promise<Health> {
  const response = await api.get<Health>("/health");
  return response.data;
}

export async function signup(input: SignupInput): Promise<User> {
  const response = await api.post<User>("/users", input);
  return response.data;
}

export async function login(email: string, password: string): Promise<string> {
  const form = new URLSearchParams({ username: email, password });
  const response = await api.post<Token>("/auth/token", form);
  return response.data.access_token;
}

export async function getMe(): Promise<User> {
  const response = await api.get<User>("/auth/me");
  return response.data;
}

// Your name and default currency (only what's sent changes).
export async function updateMe(input: { name?: string; default_currency?: string }): Promise<User> {
  const response = await api.patch<User>("/users/me", input);
  return response.data;
}

// Deletes the account and everything in it, for good.
export async function deleteMe(password: string): Promise<void> {
  await api.delete("/users/me", { data: { password } });
}

// ---------- email verification and password reset ----------
// Verifying uses a 6-digit code; resetting uses a single-use link.

type Message = { detail: string };

// The 6-digit code from the email; a right code signs you in.
export async function verifyEmail(email: string, code: string): Promise<string> {
  const response = await api.post<Token>("/auth/verify-email", { email, code });
  return response.data.access_token;
}

// A new code by email; answers the same whether or not the account exists.
export async function resendVerification(email: string): Promise<string> {
  const response = await api.post<Message>("/auth/resend-verification", { email });
  return response.data.detail;
}

// Answers the same whether or not the email has an account.
export async function forgotPassword(email: string): Promise<string> {
  const response = await api.post<Message>("/auth/forgot-password", { email });
  return response.data.detail;
}

export async function resetPassword(token: string, password: string): Promise<string> {
  const response = await api.post<Message>("/auth/reset-password", { token, password });
  return response.data.detail;
}

// ---------- expenses ----------
// Amounts are strings ("350.00") so they are never rounded by floats.
// A person is a contact id, or null for you.

// The same person may pay twice, e.g. part by card and part in cash.
export type Payment = {
  counterparty_id: number | null;
  amount: string;
  method: string | null; // see lib/paymentMethods.ts
  provider: string | null; // bank or app, e.g. "HDFC"
};

export type Participant = {
  counterparty_id: number | null;
  share_amount: string;
};

// One bill line. `amount` is the line's total, before any discount.
export type Item = {
  name: string;
  quantity: string;
  unit: string | null; // what the quantity is counted or measured in ("kg", "bags")
  amount: string;
  unit_price?: string | null; // one unit's price, when known
  // Whose it is and how much of it (null: you); adds up to amount.
  owners?: { counterparty_id: number | null; amount: string }[];
};

// Something the bill added on top of the items: tax, a fee, a tip. Never
// an item (nothing was bought). Kinds: see lib/charges.ts.
export type Charge = {
  kind: string;
  label: string;
  amount: string;
};

// Something taken off the price: a discount or rounding down. Each kind is
// its own line. Kinds: see lib/deductions.ts. (Refunds are not deductions.)
export type Deduction = {
  kind: string;
  label: string;
  amount: string;
};

// Money given back after paying (e.g. a returned item), to one person:
// counterparty_id null means you. Never a discount or a payment.
export type Refund = {
  counterparty_id: number | null;
  amount: string;
  label: string | null;
  date: string | null; // when it came back; null (sending): the expense's date
};

export type Expense = {
  id: number;
  date: string; // "2026-09-29"
  amount: string; // what was charged, after deductions
  discount_amount: string; // the deductions' total
  original_amount: string; // amount + discount_amount (items + charges)
  currency: string;
  description: string | null;
  category: string;
  counterparty_id: number | null; // paid to
  payments: Payment[]; // who paid; adds up to amount
  participants: Participant[]; // whose cost; adds up to amount
  items: Item[]; // what was bought: items - deductions + charges = amount
  charges: Charge[]; // tax, fees, tips...
  deductions: Deduction[]; // discounts, rounding down
  refunds: Refund[]; // money given back after paying; shares are of what's left
  note?: string | null; // what was worked out, e.g. "an estimate"
  settlement_ids?: number[]; // repayments saved as settling it
  created_at: string;
  updated_at: string;
};

// What the expense form sends. An empty description is stored as none.
// Empty payments/participants in a form's `initial` mean "just you".
export type ExpenseInput = {
  date: string;
  amount: string;
  currency: string;
  description: string;
  category: string;
  counterparty_id: number | null;
  payments: Payment[];
  participants: Participant[];
  discount_amount: string; // the deductions' total
  items: Item[];
  charges: Charge[];
  deductions: Deduction[];
  refunds: Refund[];
  note?: string | null;
};

export async function listExpenses(category?: string): Promise<Expense[]> {
  const response = await api.get<Expense[]>("/expenses", { params: { category } });
  return response.data;
}

export async function createExpense(input: ExpenseInput): Promise<Expense> {
  const response = await api.post<Expense>("/expenses", input);
  return response.data;
}

export async function updateExpense(id: number, input: ExpenseInput): Promise<Expense> {
  const response = await api.put<Expense>(`/expenses/${id}`, input);
  return response.data;
}

// withSettlements: also delete the repayments saved as settling it.
export async function deleteExpense(id: number, withSettlements = false): Promise<void> {
  await api.delete(`/expenses/${id}`, { params: withSettlements ? { with_settlements: true } : {} });
}

export type CategoryOption = {
  key: string;
  label: string;
};

export async function listCategories(): Promise<CategoryOption[]> {
  const response = await api.get<CategoryOption[]>("/categories");
  return response.data;
}

export type CounterpartyType = "PERSON" | "BUSINESS" | "ORGANIZATION";

export type Counterparty = {
  id: number;
  name: string;
  counterparty_type: CounterpartyType;
  relation: string | null;
};

export type CounterpartyInput = {
  name: string;
  counterparty_type: CounterpartyType;
  relation: string | null;
};

export async function listCounterparties(): Promise<Counterparty[]> {
  const response = await api.get<Counterparty[]>("/counterparties");
  return response.data;
}

export async function createCounterparty(input: CounterpartyInput): Promise<Counterparty> {
  const response = await api.post<Counterparty>("/counterparties", input);
  return response.data;
}

export async function updateCounterparty(
  id: number,
  input: CounterpartyInput,
): Promise<Counterparty> {
  const response = await api.patch<Counterparty>(`/counterparties/${id}`, input);
  return response.data;
}

export async function deleteCounterparty(id: number): Promise<void> {
  await api.delete(`/counterparties/${id}`);
}

// The same person under two names: everything of `otherId` moves to `id`.
export async function mergeCounterparty(id: number, otherId: number): Promise<Counterparty> {
  const response = await api.post<Counterparty>(`/counterparties/${id}/merge`, { into_id: otherId });
  return response.data;
}

// balances and settlements
// Positive amount: they owe you. Negative: you owe them.
export type Balance = {
  counterparty_id: number;
  name: string;
  currency: string;
  amount: string;
};

export type SettlementDirection = "they_paid_me" | "i_paid_them";

export type Settlement = {
  id: number;
  counterparty_id: number;
  direction: SettlementDirection;
  kind: MoneyKind; // what it was: a loan, paying back, a gift...
  amount: string;
  currency: string;
  date: string;
  note: string | null;
  expense_id?: number | null; // the expense it settles, when saved with one
};

export type SettlementInput = {
  counterparty_id: number;
  direction: SettlementDirection;
  kind: MoneyKind;
  amount: string;
  currency: string;
  date: string;
  note: string;
};

export async function listBalances(): Promise<Balance[]> {
  const response = await api.get<Balance[]>("/balances");
  return response.data;
}

export async function listSettlements(): Promise<Settlement[]> {
  const response = await api.get<Settlement[]>("/settlements");
  return response.data;
}

export async function createSettlement(input: SettlementInput): Promise<Settlement> {
  const response = await api.post<Settlement>("/settlements", input);
  return response.data;
}

export async function deleteSettlement(id: number): Promise<void> {
  await api.delete(`/settlements/${id}`);
}

export async function updateSettlement(id: number, input: SettlementInput): Promise<Settlement> {
  const response = await api.put<Settlement>(`/settlements/${id}`, input);
  return response.data;
}

// An expense that was really money between you and a contact.
export async function expenseToSettlement(
  id: number,
  body: { counterparty_id: number; direction: SettlementDirection; kind: MoneyKind },
): Promise<Settlement> {
  const response = await api.post<Settlement>(`/expenses/${id}/to-settlement`, body);
  return response.data;
}

// Money expected that hasn't moved yet ("Parth will pay me back 500 next
// week"). It changes no balance until it's marked as happened.
export type ExpectedMoney = {
  id: number;
  counterparty_id: number;
  direction: "they_pay_me" | "i_pay_them";
  kind: MoneyKind;
  amount: string | null;
  currency: string;
  due_date: string | null;
  note: string | null;
  created_at: string;
};

export async function listExpected(): Promise<ExpectedMoney[]> {
  const response = await api.get<ExpectedMoney[]>("/expected");
  return response.data;
}

// It happened: becomes a settlement (for `amount`, or as expected).
export async function markExpectedDone(id: number, date: string, amount?: string): Promise<Settlement> {
  const response = await api.post<Settlement>(`/expected/${id}/done`, { date, amount: amount || null });
  return response.data;
}

export async function deleteExpected(id: number): Promise<void> {
  await api.delete(`/expected/${id}`);
}

// monthly summary
export type CurrencySummary = {
  currency: string;
  your_spending: string; // your shares of this month's expenses
  you_paid: string; // what you paid out for them
  expense_count: number;
  by_category: { category: string; amount: string }[]; // biggest first
  owed_to_you: string; // all-time
  you_owe: string; // all-time
};

export type MonthSummary = {
  month: string; // "2026-09"
  currencies: CurrencySummary[]; // your default currency first
};

export async function getSummary(month: string): Promise<MonthSummary> {
  const response = await api.get<MonthSummary>("/summary", { params: { month } });
  return response.data;
}

// ---------- assistant (natural-language entry) ----------

// You, one of your contacts, or a new contact proposed by the draft.
export type DraftPerson = {
  kind: "me" | "contact" | "new";
  contact_id: number | null;
  new_key: string | null;
  name: string;
};

export type DraftNewContact = {
  key: string;
  name: string;
  counterparty_type: CounterpartyType;
  relation: string | null;
  confirmed?: boolean; // the user said this is someone new (needed to add a person)
};

// What the assistant understood. With problems it can't be saved as is.
export type ExpenseDraft = {
  excerpt: string;
  date: string;
  amount: string | null;
  currency: string;
  description: string | null;
  category: string;
  discount_amount: string; // the deductions' total
  items: Item[];
  charges: Charge[];
  deductions: Deduction[];
  refunds: DraftRefund[]; // shares add up to amount less these
  paid_to: DraftPerson | null;
  payments: { person: DraftPerson; amount: string; method: string | null; provider: string | null }[];
  participants: { person: DraftPerson; share_amount: string }[];
  // One list per item: whose it is and how much of it ([] when not said).
  item_owners: { person: DraftPerson; share_amount: string }[][];
  new_contacts: DraftNewContact[];
  problems: string[];
  notes: string[]; // what was worked out, e.g. change given back
  // One-tap answers to its problems that the server applies exactly.
  choices: DraftChoice[];
};

// Money given back after paying, and who got it.
export type DraftRefund = {
  person: DraftPerson;
  amount: string;
  label: string | null;
  date: string;
};

// An exact answer the server applies: "keep_total" / "keep_parts" when a
// total and the bill's parts disagree; "refund_owner:<n>" / "refund_shared:<n>"
// for whose share refund n comes off. Sent back as the server gave it.
export type Decision = string;

export type DraftChoice = {
  decision: Decision;
  label: string;
};

// Every list in a draft is always a list, even if the server leaves one
// out (e.g. an older server without `notes`), so the cards never break.
function normalizeDraft(draft: Partial<ExpenseDraft> & Pick<ExpenseDraft, "excerpt" | "date">): ExpenseDraft {
  return {
    amount: null,
    currency: "",
    description: null,
    category: "other",
    discount_amount: "0",
    paid_to: null,
    ...draft,
    items: draft.items ?? [],
    charges: draft.charges ?? [],
    deductions: draft.deductions ?? [],
    refunds: draft.refunds ?? [],
    payments: draft.payments ?? [],
    participants: draft.participants ?? [],
    item_owners: draft.item_owners ?? [],
    new_contacts: draft.new_contacts ?? [],
    problems: draft.problems ?? [],
    notes: draft.notes ?? [],
    choices: draft.choices ?? [],
  };
}

// Money paid back between you and one person: saved as a settlement.
export type RepaymentDraft = {
  excerpt: string;
  date: string;
  amount: string | null;
  currency: string;
  method: string | null;
  kind: MoneyKind | null; // null: the text didn't say what it was (asked)
  from_person: DraftPerson;
  to_person: DraftPerson;
  new_contacts: DraftNewContact[];
  problems: string[];
  notes?: string[]; // what was worked out, e.g. paid in another currency (saved with it)
  choices?: DraftChoice[]; // exact answers to its questions, e.g. "Yes, add Kabir"
  settles_excerpt?: string | null; // the expense in the same message it pays back
};

// Money between you and someone that hasn't moved yet: can be remembered.
export type ExpectedDraft = {
  excerpt: string;
  from_person: DraftPerson;
  to_person: DraftPerson;
  amount: string | null;
  currency: string;
  kind: MoneyKind;
  due_date: string | null;
  new_contacts: DraftNewContact[];
  problems: string[];
  choices: DraftChoice[];
};

// Everything the assistant read from one message.
export type AssistantResult = {
  expenses: ExpenseDraft[];
  repayments: RepaymentDraft[];
  expected: ExpectedDraft[]; // money that hasn't moved yet
  skipped: string[]; // parts that can't be recorded, with why
};


// Every list in a result is always a list, even if the server leaves one out.
function normalizeResult(data: Partial<AssistantResult>): AssistantResult {
  return {
    expenses: (data.expenses ?? []).map(normalizeDraft),
    repayments: (data.repayments ?? []).map((repayment) => ({
      ...repayment,
      new_contacts: repayment.new_contacts ?? [],
      problems: repayment.problems ?? [],
    })),
    expected: (data.expected ?? []).map((draft) => ({
      ...draft,
      new_contacts: draft.new_contacts ?? [],
      problems: draft.problems ?? [],
      choices: draft.choices ?? [],
    })),
    skipped: data.skipped ?? [],
  };
}

export async function previewExpenses(text: string): Promise<AssistantResult> {
  // The model can take a while; allow more than the usual 15 seconds.
  const response = await api.post<Partial<AssistantResult>>(
    "/assistant/preview",
    { text, today: todayISO() },
    { timeout: 90000 },
  );
  return normalizeResult(response.data);
}

// One round of a draft's questions and the user's answer to them.
export type ClarificationTurn = {
  asked: string[];
  answer: string;
};

// A draft's description read again with every answer so far (and every
// choice picked); what comes back replaces the draft that was asked about.
// focus: with several things in one message, the part asked about (the
// whole message is read, so nothing it said about this part is lost).
export async function clarifyExpenses(
  text: string,
  turns: ClarificationTurn[],
  decisions: Decision[],
  focus?: string | null,
): Promise<AssistantResult> {
  const response = await api.post<Partial<AssistantResult>>(
    "/assistant/clarify",
    { text, turns, decisions, focus: focus ?? null, today: todayISO() },
    { timeout: 90000 },
  );
  return normalizeResult(response.data);
}

// Saves a repayment as a settlement, creating its proposed contact;
// expenseId: the saved expense from the same message it pays back.
export async function confirmRepayment(draft: RepaymentDraft, expenseId?: number | null): Promise<Settlement> {
  const response = await api.post<Settlement>("/assistant/confirm-repayment", {
    ...draft,
    expense_id: expenseId ?? null,
  });
  return response.data;
}

// Saves the draft exactly as shown, creating its proposed contacts;
// settlementIds: repayments from the same message already saved for it.
export async function confirmDraft(draft: ExpenseDraft, settlementIds: number[] = []): Promise<Expense> {
  const response = await api.post<Expense>("/assistant/confirm", { ...draft, settlement_ids: settlementIds });
  return response.data;
}

// Remembers money that hasn't moved yet, creating its proposed contact.
export async function confirmExpected(draft: ExpectedDraft): Promise<ExpectedMoney> {
  const response = await api.post<ExpectedMoney>("/assistant/confirm-expected", {
    ...draft,
    note: draft.excerpt,
  });
  return response.data;
}
