"""
The evaluation set for the expense assistant: realistic sentences covering
every part of the flow, each with the result a person would expect.

Run with the real model (costs a little per run):

    uv run python evals/run_evals.py

Expected values:
    expenses    one dict per expense, in order:
                  amount    the final amount of the bill
                  paid      person -> what they paid (after any change)
                  shares    person -> their share (omitted: all yours)
                  charges   kinds of the charges (tax, fee...), if given
                  deductions  kinds of the deductions (discount, rounding...)
                  refunds   amounts given back after paying, when given
                  (shares default to all yours of what's left after refunds)
    repayments  (from, to, amount) for money paid back between people
    problem     True when the text is genuinely unclear or unsupported,
                so the draft must be stopped instead of guessed
    may_ask     True when the text can honestly be read two ways: a
                question passes, and so does the expected result

People are named as the app shows them: "You", or the contact's name.
The user's contacts are listed in CONTACTS.
"""

CONTACTS = [
    ("Parth", "PERSON", "flatmate"),
    ("Riya", "PERSON", None),
    ("Rahul", "PERSON", None),
    ("Meera", "PERSON", "wife"),
    ("Swiggy", "BUSINESS", None),
    # Saved by how they relate to the user, so cases about splitting with
    # them aren't about adding someone new (that's always asked).
    ("Cousin", "PERSON", "cousin"),
    ("Colleague", "PERSON", "colleague"),
    ("Neighbour", "PERSON", "neighbour"),
]

CASES: list[dict] = [
    # ---------- items and quantities ----------
    {"text": "Lunch 350",
     "expenses": [{"amount": "350.00", "paid": {"You": "350.00"}}]},
    {"text": "Bought 3 notebooks at 45 each and a pen for 20",
     "expenses": [{"amount": "155.00"}]},
    {"text": "2 kg apples at 180 per kg and a dozen bananas for 60",
     "expenses": [{"amount": "420.00"}]},
    {"text": "Phone case 1.2k",
     "expenses": [{"amount": "1200.00"}]},

    # ---------- discounts ----------
    {"text": "Shoes 2,999 with 20% off",
     "expenses": [{"amount": "2399.20", "deductions": ["discount"]}]},
    # 1,840 may be before or after the coupon: read as the price before
    # it, or asked (one tap); never guessed as what was paid.
    {"text": "Groceries 1,840, used a 200 coupon", "may_ask": True,
     "expenses": [{"amount": "1640.00", "deductions": ["discount"]}]},
    {"text": "Headphones 4,500 with a flat 500 discount",
     "expenses": [{"amount": "4000.00", "deductions": ["discount"]}]},

    # ---------- taxes ----------
    {"text": "Laptop bag 1,200 + 18% GST",
     "expenses": [{"amount": "1416.00", "charges": ["tax"]}]},
    {"text": "Hotel room 4,000, CGST 6% and SGST 6%",
     "expenses": [{"amount": "4480.00", "charges": ["tax", "tax"]}]},
    {"text": "Paid 1,180 for the course including 18% GST",
     "expenses": [{"amount": "1180.00"}]},
    {"text": "Spa 2,000 and GST 18% which came to 360",
     "expenses": [{"amount": "2360.00", "charges": ["tax"]}]},

    # ---------- fees, charges, tips ----------
    {"text": "Zomato: pizza 450, delivery 40, platform fee 5, GST 25",
     "expenses": [{"amount": "520.00", "charges": ["delivery", "fee", "tax"]}]},
    {"text": "Dinner 2,400 plus 10% service charge and 5% GST",
     "expenses": [{"amount": "2772.00", "charges": ["service_charge", "tax"]}]},
    {"text": "Cab 380 and tipped the driver 20",
     "expenses": [{"amount": "400.00", "charges": ["tip"]}]},

    # ---------- stated totals ----------
    {"text": "Dinner bill was 1,850 including tax",
     "expenses": [{"amount": "1850.00"}]},
    {"text": "Milk 60, bread 45, eggs 90, total 195",
     "expenses": [{"amount": "195.00"}]},

    # ---------- several payers, methods ----------
    {"text": "My movie ticket 900, Parth paid 500 and I paid 400",
     "expenses": [{"amount": "900.00", "paid": {"Parth": "500.00", "You": "400.00"}}]},
    # Others involved and nothing says whose it is: asked, never assumed yours.
    {"text": "Movie 900, Parth paid 500 and I paid 400", "problem": True},
    {"text": "Dinner 3,000: Riya paid 1,000 by card and I paid the rest on UPI, "
             "split equally between me, Riya and Parth",
     "expenses": [{"amount": "3000.00", "paid": {"Riya": "1000.00", "You": "2000.00"},
                   "shares": {"You": "1000.00", "Riya": "1000.00", "Parth": "1000.00"}}]},
    {"text": "Hotel 5,400 for my work trip: my wife covered 2,000 by card and I paid the remaining in cash",
     "expenses": [{"amount": "5400.00", "paid": {"Meera": "2000.00", "You": "3400.00"}}]},

    # ---------- cash tendered and change ----------
    {"text": "Coffee 180, paid with a 500 note",
     "expenses": [{"amount": "180.00", "paid": {"You": "180.00"}}]},
    {"text": "Paid 2,000 cash for a 1,640 bill and got 360 back",
     "expenses": [{"amount": "1640.00", "paid": {"You": "1640.00"}}]},
    {"text": "Groceries 870, gave 1,000 and got 130 change",
     "expenses": [{"amount": "870.00", "paid": {"You": "870.00"}}]},
    {"text": "Snacks 90, gave 100 and got 10 back",
     "expenses": [{"amount": "90.00"}]},

    # ---------- repayments (not expenses) ----------
    {"text": "Parth paid me back 500",
     "expenses": [], "repayments": [("Parth", "You", "500.00")]},
    {"text": "I returned 1,200 to Riya via UPI",
     "expenses": [], "repayments": [("You", "Riya", "1200.00")]},
    {"text": "Rahul settled the 750 he owed me",
     "expenses": [], "repayments": [("Rahul", "You", "750.00")]},
    {"text": "Lunch 600 with Riya split equally, I paid, and she paid me her share in cash",
     "expenses": [{"amount": "600.00", "paid": {"You": "600.00"},
                   "shares": {"You": "300.00", "Riya": "300.00"}}],
     "repayments": [("Riya", "You", "300.00")]},

    # ---------- refunds ----------
    {"text": "Bought 2 shirts for 1,600, returned one and got 800 refunded",
     "expenses": [{"amount": "1600.00", "deductions": [], "refunds": ["800.00"],
                   "shares": {"You": "800.00"}}]},
    # A refund and a discount on one bill stay two different things.
    {"text": "Jacket 3,000 with a 300 coupon, and 200 refunded for a missing button",
     "expenses": [{"amount": "2700.00", "deductions": ["discount"], "refunds": ["200.00"],
                   "shares": {"You": "2500.00"}}]},
    {"text": "Got a refund of 450 from Amazon for a charger I returned last week",
     "problem": True},

    # ---------- people and splits ----------
    {"text": "Pizza 600 with Rahul, my share 250 and Rahul owes me 350",
     "expenses": [{"amount": "600.00", "shares": {"You": "250.00", "Rahul": "350.00"}}]},
    {"text": "Rent 18,000, I pay 60% and Parth pays 40%",
     "expenses": [{"amount": "18000.00", "shares": {"You": "10800.00", "Parth": "7200.00"}}]},
    {"text": "Rent 18,000 split 60/40 between me and Parth, I pay 60% and Parth pays 40%",
     "expenses": [{"amount": "18000.00", "paid": {"You": "10800.00", "Parth": "7200.00"},
                   "shares": {"You": "10800.00", "Parth": "7200.00"}}]},
    {"text": "Pizza for me 350 and a burger for Parth 250, plus 5% GST, I paid",
     "expenses": [{"amount": "630.00", "paid": {"You": "630.00"}, "charges": ["tax"],
                   "shares": {"You": "367.50", "Parth": "262.50"}}]},
    {"text": "Groceries 1,200 split equally with Parth and Riya, Parth paid",
     "expenses": [{"amount": "1200.00", "paid": {"Parth": "1200.00"},
                   "shares": {"You": "400.00", "Parth": "400.00", "Riya": "400.00"}}]},
    {"text": "Uber 450 for my wife, I paid",
     "expenses": [{"amount": "450.00", "paid": {"You": "450.00"}, "shares": {"Meera": "450.00"}}]},

    # ---------- nothing allocated that wasn't said ----------
    # Being with someone, or them paying, doesn't make the cost shared.
    {"text": "Dinner with Riya 1,200, I paid", "problem": True},
    {"text": "My dinner 1,200 with Riya, I paid",
     "expenses": [{"amount": "1200.00", "paid": {"You": "1200.00"}}]},
    # Someone else paying for what's yours: owed back or their treat isn't
    # said, so it's asked; said either way, it isn't.
    {"text": "Parth paid 500 for my movie ticket", "problem": True},
    {"text": "Parth paid 500 for my movie ticket, I'll pay him back",
     "expenses": [{"amount": "500.00", "paid": {"Parth": "500.00"}, "shares": {"You": "500.00"}}]},
    {"text": "Parth paid 500 for my movie ticket, his treat",
     "expenses": [{"amount": "500.00", "paid": {"Parth": "500.00"}, "shares": {"Parth": "500.00"}}]},
    # An item nobody was named for isn't the payer's, and isn't assumed to
    # be yours: asked.
    {"text": "Lunch: pasta 400 was mine, burger 250 for Parth, fries 150. Parth paid.",
     "problem": True},
    # Items said to be shared by everyone go to everyone.
    {"text": "Lunch with Parth and Riya: pasta 450 shared by all three, soup 150 was Riya's. I paid.",
     "expenses": [{"amount": "600.00", "paid": {"You": "600.00"},
                   "shares": {"You": "150.00", "Parth": "150.00", "Riya": "300.00"}}]},
    # Owning one item doesn't put someone in the even split of the rest.
    {"text": "Pizza 600 split equally between me and Riya, and the 200 dessert was Parth's. I paid.",
     "expenses": [{"amount": "800.00", "paid": {"You": "800.00"},
                   "shares": {"You": "300.00", "Riya": "300.00", "Parth": "200.00"}}]},
    # Someone's own items plus a named group for everything else.
    {"text": "Pasta 400 for Parth, pizza 300 for me, garlic bread 100 shared by me and Riya. Riya paid.",
     "expenses": [{"amount": "800.00", "paid": {"Riya": "800.00"},
                   "shares": {"You": "350.00", "Riya": "50.00", "Parth": "400.00"}}]},
    # Split, but with nobody named: asked, not guessed.
    {"text": "Pizza 900 split equally", "problem": True},
    # Shared, but nobody said who paid: asked, not assumed to be you.
    {"text": "Dinner 1,200 split equally with Parth", "problem": True},
    # A total that disagrees with its parts: asked, never forced to fit.
    {"text": "Rice 600 and oil 900 plus 5% GST, total 1,600", "problem": True},

    # ---------- several expenses in one message ----------
    {"text": "Breakfast 120 and lunch 280",
     "expenses": [{"amount": "120.00"}, {"amount": "280.00"}]},
    {"text": "Petrol 2,000 by card and parking 50 in cash",
     "expenses": [{"amount": "2000.00"}, {"amount": "50.00"}]},

    # ---------- currency ----------
    {"text": "Hotel $120 in Bangkok",
     "expenses": [{"amount": "120.00", "currency": "USD"}]},

    # ---------- several payers and items that are someone's own ----------
    # People not in the contacts are proposed by their relation.
    {"text": "Cafe bill 900: pizza 520 split equally between me, my cousin and my colleague, "
             "brownie 110 only for my colleague, drinks 270 for me. My colleague paid 250 "
             "through UPI and my cousin paid whatever was left.",
     "expenses": [{"amount": "900.00",
                   "paid": {"Colleague": "250.00", "Cousin": "650.00"},
                   "shares": {"You": "443.34", "Cousin": "173.33", "Colleague": "283.33"}}]},
    {"text": "Dinner 1,000: noodles 600 shared by me, Riya and Parth, ice cream 150 was "
             "Parth's alone, soup 250 was mine. I paid 400 by card, Parth paid 300 on UPI "
             "and Riya paid the remaining.",
     "expenses": [{"amount": "1000.00",
                   "paid": {"You": "400.00", "Parth": "300.00", "Riya": "300.00"},
                   "shares": {"You": "450.00", "Parth": "350.00", "Riya": "200.00"}}]},
    {"text": "Movie snacks 650 split equally between me, Rahul and my neighbour, except the "
             "150 nachos which were only Rahul's. My neighbour paid 300 by UPI and I paid the rest.",
     "expenses": [{"amount": "650.00",
                   "paid": {"Neighbour": "300.00", "You": "350.00"},
                   "shares": {"You": "166.67", "Rahul": "316.67", "Neighbour": "166.66"}}]},
    {"text": "Lunch with Parth and Riya: pasta 450 for all three of us, cold coffee 120 only "
             "for Parth, plus 5% GST. Parth paid 200 on UPI and Riya paid the rest in cash.",
     "expenses": [{"amount": "598.50",
                   "paid": {"Parth": "200.00", "Riya": "398.50"},
                   "shares": {"You": "157.50", "Parth": "283.50", "Riya": "157.50"}}]},
]
