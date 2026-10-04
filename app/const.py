# ── Column name aliases (case-insensitive matching) ────────────────────────────
DATE_ALIASES = ["Date", "Tran Date"]
DESCRIPTION_ALIASES = ["PARTICULARS", "Details"]
DEBIT_ALIASES = ["Debit", "CR"]
CREDIT_ALIASES = ["Credit", "DR"]
BALANCE_ALIASES = ["Balance", "BAL"]

# Upload limits for the web interface, measured in bytes unless noted otherwise.
MAX_UPLOAD_FILES = 10
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
MAX_REQUEST_SIZE_BYTES = 50 * 1024 * 1024

# Expire local session pickles and generated reports after this many days.
ARTIFACT_RETENTION_DAYS = 180

# ── Category rules: (category, [patterns], transaction_type) ──────────────────
#
# Pattern syntax:
#   plain text        → case-insensitive substring match  (default, recommended)
#   case:Text         → case-sensitive substring match
#   re:\bword\b       → raw regex, case-insensitive
#   re:case:[A-Z]+    → raw regex, case-sensitive
#
# Order matters — first match wins.
# transaction_type: "credit", "debit", or "both"
#
CATEGORY_RULES: list[tuple[str, list[str], str]] = [
    # Income - only for credits
    (
        "Income",
        [
            r"salary",
            r"SALARY",
            r"ACH-CR",
            r"IMPS/P2A",
            r"MBB-TD/",
            r"NEFT",
            r"UPI/CR",
            r"SB:",
        ],
        "credit",
    ),
    # Housing
    (
        "Housing",
        [
            r"rent",
            r"BABITHA  MANJUNATH   /",
        ],
        "debit",
    ),
    # Groceries
    (
        "Groceries",
        [
            r"Zepto",
            r"DMart",
            r"Instamart",
            r"BigBasket",
            r"market",
        ],
        "debit",
    ),
    # Dining & Restaurants
    (
        "Dining",
        [
            r"restaurant",
            r"cafe",
            r"Zomato",
            r"Dominos",
            r"Swiggy",
        ],
        "debit",
    ),
    # Transport
    (
        "Transport",
        [
            r"uber",
            r"Redbus",
            r"Ola",
            r"Cab",
        ],
        "debit",
    ),
    # Utilities
    (
        "Utilities",
        [
            r"electric",
            r"gas bill",
            r"water bill",
            r"internet",
            r"broadband",
            r"phone",
            r"mobile",
        ],
        "debit",
    ),
    # Subscriptions & Entertainment
    (
        "Subscriptions & Entertainment",
        [
            r"netflix",
            r"DISTRICT",
            r"bookmyshow",
        ],
        "debit",
    ),
    # Shopping
    (
        "Shopping",
        [
            r"amazon",
            r"CreditCard Payment",
        ],
        "debit",
    ),
    # ATM & Cash
    (
        "Cash & ATM",
        [
            r"ATMCard",
        ],
        "debit",
    ),
    # Transfers
    (
        "UPI & Transfers",
        [
            r"UPI/CR",
            r"RAZORPAY/",
            r"NEFT/",
            r"UPILITE",
        ],
        "both",
    ),
    # Investments
    (
        "Investments",
        [
            r"Mutual Funds",
            r"Groww",
            r"PPF",
            r"RD/",
            r"ACH-DR-Groww",
            r"LIC OF INDIA",
            r"ECS/UTIBDE34161840202601",
            r"WEALTHYIN CUSTOMER",
            r"gold",
        ],
        "debit",
    ),
    # EMI
    (
        "EMI",
        [
            r"_EMI_",
        ],
        "debit",
    ),
]
