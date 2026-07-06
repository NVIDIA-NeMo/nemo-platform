#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generate a balanced labeled phishing/benign email dataset for the first-mile demo.

The 3-row LFS sample shipped upstream is too small to produce believable
classification metrics. This script composes a larger, balanced, deduplicated set
from parameterized archetypes (each phishing/benign category filled with randomized
slots) so the classification benchmark reports stable recall/precision/accuracy/F1.

Deterministic: a fixed seed makes the committed CSV reproducible. This is a
stand-in for a Data Designer + Safe Synthesizer pipeline; all content is synthetic
and contains no real PII. Regenerate with:

    python scripts/generate_dataset.py

Output columns: subject, body, label   (label in {"phishing", "benign"}).
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

SEED = 20260706
DEFAULT_PER_CLASS = 200
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "src" / "email_phishing_analyzer" / "email-phishing-eval-data.csv"

FIRST_NAMES = [
    "Alex",
    "Jordan",
    "Taylor",
    "Morgan",
    "Sam",
    "Priya",
    "Chen",
    "Diego",
    "Fatima",
    "Noah",
    "Olivia",
    "Liam",
    "Emma",
    "Raj",
    "Yuki",
    "Omar",
    "Sofia",
    "Ivan",
    "Grace",
    "Leo",
]
COMPANIES = [
    "Northwind",
    "Contoso",
    "Globex",
    "Initech",
    "Umbrella",
    "Acme",
    "Hooli",
    "Stark Industries",
    "Wayne Enterprises",
    "Soylent",
    "Vandelay",
    "Wonka",
    "Cyberdyne",
    "Massive Dynamic",
    "Pied Piper",
]
BANKS = ["First National Bank", "MetroTrust", "Union Savings", "Pacific Credit Union", "Sterling Bank"]
BRANDS = ["Amazon", "PayPal", "Netflix", "Microsoft 365", "Apple", "DHL", "FedEx", "DocuSign", "Dropbox"]
DEPARTMENTS = ["Marketing", "Finance", "Engineering", "People Ops", "Sales", "Legal", "IT"]
AMOUNTS = ["$49.99", "$128.50", "$1,240.00", "$76.20", "$999.00", "$14.30", "$540.00", "$2,310.75"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
TIMES = ["9am", "10:30am", "1pm", "2pm", "3:15pm", "4pm"]


def _domain(base: str) -> str:
    slug = base.lower().replace(" ", "-").replace(".", "")
    return f"http://{slug}-secure.example.com/verify?id={random.randint(10000, 99999)}"


def phishing_email() -> tuple[str, str]:
    kind = random.choice(
        [
            "suspension",
            "prize",
            "invoice",
            "delivery",
            "password",
            "ceo_fraud",
            "crypto",
            "tax",
            "shared_doc",
        ]
    )
    name = random.choice(FIRST_NAMES)
    company = random.choice(COMPANIES)
    brand = random.choice(BRANDS)
    bank = random.choice(BANKS)
    link = _domain(brand)
    amount = random.choice(AMOUNTS)

    if kind == "suspension":
        subject = random.choice(
            [
                f"Urgent: Your {brand} account has been suspended",
                f"Action required: unusual sign-in on your {brand} account",
                f"[Security Alert] Verify your {bank} account now",
            ]
        )
        body = (
            f"Dear customer,\n"
            f"We detected unusual activity on your {brand} account. To avoid permanent suspension, "
            f"you must verify your identity within 24 hours by clicking the link below and entering your "
            f"username, password, and one-time code.\n{link}\n"
            f"Failure to act will result in your account being disabled.\nRegards,\n{brand} Security Team"
        )
    elif kind == "prize":
        subject = random.choice(
            [
                "Congratulations! You have won a brand new iPhone",
                f"You are today's lucky {brand} winner!",
                "Claim your $1,000 gift card now",
            ]
        )
        body = (
            f"Dear valued customer,\nCongratulations! You have been selected to receive a free reward. "
            f"To claim your prize, simply confirm your shipping address and card details at the link below.\n{link}\n"
            f"This exclusive offer expires tonight, so act fast!"
        )
    elif kind == "invoice":
        subject = f"Invoice {random.randint(1000, 9999)} overdue - immediate payment required"
        body = (
            f"Hello,\nOur records show an unpaid balance of {amount}. To avoid a late fee and service "
            f"interruption, please review and settle the invoice using the secure portal below.\n{link}\n"
            f"If payment is not received today, the account will be forwarded to collections.\nAccounts Receivable"
        )
    elif kind == "delivery":
        subject = f"{brand}: your package could not be delivered"
        body = (
            f"Hi,\nWe attempted to deliver your parcel but were unable to complete it due to an unpaid "
            f"customs fee of {amount}. Reschedule delivery and pay the fee within 12 hours here:\n{link}\n"
            f"Unclaimed packages are returned to sender.\n{brand} Delivery"
        )
    elif kind == "password":
        subject = f"Your {brand} password will expire in 2 hours"
        body = (
            f"Dear user,\nYour password is about to expire. To keep your account active, re-enter your "
            f"current password and confirm a new one immediately at:\n{link}\n"
            f"Ignoring this message will lock you out of your mailbox.\nIT Helpdesk"
        )
    elif kind == "ceo_fraud":
        subject = random.choice(["Quick favor", "Are you available?", "Urgent request - confidential"])
        body = (
            f"Hi {name},\nI'm in back-to-back meetings and need you to handle something discreetly. "
            f"Please purchase four {amount} gift cards for a client and send me the codes right away. "
            f"I'll approve the reimbursement afterward. Do not loop in anyone else yet.\nThanks,\nThe CEO"
        )
    elif kind == "crypto":
        subject = "Double your Bitcoin in 24 hours - limited event"
        body = (
            f"Hello investor,\nOur exclusive {company} crypto event guarantees a 100% return. Send any "
            f"amount to the wallet on the page below and receive double back instantly.\n{link}\n"
            f"Verified by thousands of happy users. Offer ends at midnight."
        )
    elif kind == "tax":
        subject = "IRS notice: you are eligible for a tax refund"
        body = (
            f"Dear taxpayer,\nYou are eligible for a refund of {amount}. To process your refund, confirm "
            f"your social security number and bank routing details through the secure form:\n{link}\n"
            f"This request must be completed within 48 hours."
        )
    else:  # shared_doc
        subject = f"{name} shared a document with you"
        body = (
            f"{name} has shared a confidential file '{random.choice(['Q3-Payroll', 'Bonus-List', 'Budget'])}"
            f".xlsx' with you on {brand}. Sign in with your work email and password to view it:\n{link}\n"
            f"This link is available for a limited time."
        )
    return subject, body


def benign_email() -> tuple[str, str]:
    kind = random.choice(
        [
            "meeting",
            "newsletter",
            "receipt",
            "hr",
            "project",
            "invite",
            "thanks",
            "it_notice",
            "webinar",
        ]
    )
    name = random.choice(FIRST_NAMES)
    other = random.choice(FIRST_NAMES)
    company = random.choice(COMPANIES)
    dept = random.choice(DEPARTMENTS)
    day = random.choice(DAYS)
    time = random.choice(TIMES)
    amount = random.choice(AMOUNTS)

    if kind == "meeting":
        subject = f"Reminder: {dept} sync on {day}"
        body = (
            f"Hi team,\nJust a reminder that our {dept} sync is on {day} at {time}. Agenda: status updates "
            f"and next week's priorities. Let me know if you can't make it.\nThanks,\n{name}"
        )
    elif kind == "newsletter":
        subject = f"{company} monthly newsletter"
        body = (
            f"Hello,\nHere's what happened at {company} this month: a new office opened, the {dept} team "
            f"shipped a feature, and we welcomed five new hires. Read the full stories on our internal wiki.\n"
            f"Have a great week,\nThe {company} Comms Team"
        )
    elif kind == "receipt":
        subject = f"Your receipt from {company}"
        body = (
            f"Hi {name},\nThanks for your purchase. Your order total was {amount} and it will arrive in "
            f"3-5 business days. No action is needed; this email is for your records.\n{company} Support"
        )
    elif kind == "hr":
        subject = "Open enrollment starts next week"
        body = (
            f"Hi everyone,\nBenefits open enrollment begins {day}. Review your options in the HR portal at "
            f"your convenience before the end of the month. Reach out to People Ops with any questions.\n"
            f"Best,\n{name}, People Ops"
        )
    elif kind == "project":
        subject = f"Project update: {company} rollout"
        body = (
            f"Hi {other},\nQuick update: we finished the first milestone ahead of schedule and testing looks "
            f"good. I'll share the deck before {day}. Let me know if you'd like to review earlier.\nCheers,\n{name}"
        )
    elif kind == "invite":
        subject = f"Calendar invite: 1:1 on {day}"
        body = (
            f"Hi {other},\nSending over a calendar invite for our 1:1 on {day} at {time}. Feel free to add "
            f"anything you'd like to discuss to the shared notes doc.\nTalk soon,\n{name}"
        )
    elif kind == "thanks":
        subject = "Thanks for your help yesterday"
        body = (
            f"Hi {other},\nJust wanted to say thanks for jumping in on the {dept} issue yesterday - it really "
            f"helped us hit the deadline. Owe you a coffee.\nBest,\n{name}"
        )
    elif kind == "it_notice":
        subject = "Scheduled maintenance this weekend"
        body = (
            f"Hello,\nIT will perform scheduled maintenance on internal tools this Saturday from 10pm to 2am. "
            f"No action is required and you don't need to enter any credentials. Systems may be briefly "
            f"unavailable during that window.\n{company} IT"
        )
    else:  # webinar
        subject = f"You're invited: {company} tech talk on {day}"
        body = (
            f"Hi {name},\nWe're hosting an internal tech talk on {day} at {time} covering our latest {dept} "
            f"work. Add it to your calendar if you're interested - the recording will be shared afterward.\n"
            f"See you there,\n{other}"
        )
    return subject, body


def generate(per_class: int) -> list[tuple[str, str, str]]:
    random.seed(SEED)
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for label, fn in (("phishing", phishing_email), ("benign", benign_email)):
        count = 0
        attempts = 0
        while count < per_class:
            attempts += 1
            if attempts > per_class * 200:
                raise RuntimeError(f"Could not generate {per_class} unique {label} emails (got {count}).")
            subject, body = fn()
            key = f"{label}:{subject}:{body}"
            if key in seen:
                continue
            seen.add(key)
            rows.append((subject, body, label))
            count += 1

    random.shuffle(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--per-class", type=int, default=DEFAULT_PER_CLASS, help="Number of emails per class (phishing/benign)."
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output CSV path.")
    args = parser.parse_args()

    rows = generate(args.per_class)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["subject", "body", "label"])
        writer.writerows(rows)

    n_phish = sum(1 for r in rows if r[2] == "phishing")
    print(f"Wrote {len(rows)} rows ({n_phish} phishing / {len(rows) - n_phish} benign) to {args.out}")


if __name__ == "__main__":
    main()
