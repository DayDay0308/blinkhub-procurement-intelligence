"""Sample records from the case study (section 6), reproduced exactly.

Fictional data provided by ProcureSense for assessment purposes. Fields the case
study does not give (registration numbers, dates, approvers) are filled with
clearly labelled demo values; see ASSUMPTIONS.
"""

ASSUMPTIONS = [
    "SMME vs Large Enterprise is taken from the register; no EME/QSE size band was given.",
    "Invoice received date = today minus 'Days Outstanding'; invoice date = received date.",
    "Paid invoices: paid date = received date + 'Days Outstanding'.",
    "Invoices carry no PO reference in the source data, so po_id is left empty (as found).",
    "No approver is recorded for invoices in the source data, so none is assigned (as found).",
    "'Outstanding' invoices are stored with status PENDING_APPROVAL.",
    "Registration numbers are generated demo values in CIPC format.",
]

DEPARTMENTS = [
    ("FAC", "Facilities"),
    ("ADM", "Administration"),
    ("OPS", "Operations"),
    ("INF", "Infrastructure"),
]

CATEGORIES = [
    ("CLN", "Cleaning"),
    ("STA", "Stationery"),
    ("TRN", "Transport"),
    ("MNT", "Maintenance"),
    ("CON", "Construction"),
]

# name, province, type, B-BBEE level, status
SUPPLIERS = [
    ("Ubuntu Cleaning", "GAUTENG", "SMME", 1, "ACTIVE"),
    ("Prime Facilities", "GAUTENG", "LARGE_ENTERPRISE", 2, "ACTIVE"),
    ("Thuto Supplies", "LIMPOPO", "SMME", 1, "ACTIVE"),
    ("Metro Logistics", "GAUTENG", "LARGE_ENTERPRISE", 4, "ACTIVE"),
    ("Khula Electrical", "MPUMALANGA", "SMME", 2, "ACTIVE"),
    ("Rapid Transport", "KWAZULU_NATAL", "SMME", 1, "ACTIVE"),
    ("Apex Infrastructure", "GAUTENG", "LARGE_ENTERPRISE", 3, "ACTIVE"),
    ("Sisonke Trading", "LIMPOPO", "SMME", 1, "INACTIVE"),
]

# PO number, supplier, category, department, amount (R)
PURCHASE_ORDERS = [
    ("PO001", "Ubuntu Cleaning", "Cleaning", "Facilities", 85_000),
    ("PO002", "Prime Facilities", "Cleaning", "Facilities", 450_000),
    ("PO003", "Thuto Supplies", "Stationery", "Administration", 35_000),
    ("PO004", "Metro Logistics", "Transport", "Operations", 620_000),
    ("PO005", "Khula Electrical", "Maintenance", "Infrastructure", 95_000),
    ("PO006", "Rapid Transport", "Transport", "Operations", 180_000),
    ("PO007", "Apex Infrastructure", "Construction", "Infrastructure", 1_200_000),
    ("PO008", "Ubuntu Cleaning", "Cleaning", "Facilities", 95_000),
    ("PO009", "Prime Facilities", "Cleaning", "Operations", 390_000),
    ("PO010", "Thuto Supplies", "Stationery", "Administration", 42_000),
    ("PO011", "Metro Logistics", "Transport", "Operations", 710_000),
    ("PO012", "Khula Electrical", "Maintenance", "Infrastructure", 125_000),
]

# invoice, supplier, amount (R), days outstanding, status
INVOICES = [
    ("INV001", "Ubuntu Cleaning", 85_000, 15, "Paid"),
    ("INV002", "Thuto Supplies", 35_000, 42, "Outstanding"),
    ("INV003", "Metro Logistics", 620_000, 65, "Outstanding"),
    ("INV004", "Khula Electrical", 95_000, 12, "Paid"),
    ("INV005", "Rapid Transport", 180_000, 38, "Outstanding"),
    ("INV006", "Ubuntu Cleaning", 85_000, 47, "Outstanding"),
    ("INV007", "Prime Facilities", 450_000, 8, "Paid"),
    ("INV008", "Thuto Supplies", 35_000, 42, "Outstanding"),
]

DEMO_USERS = [
    # email, name, role, department, supplier, approval limit
    ("admin@mics.demo", "Ayanda Admin", "ADMIN", None, None, None),
    (
        "procurement@mics.demo",
        "Palesa Procurement",
        "PROCUREMENT_OFFICER",
        "Operations",
        None,
        None,
    ),
    ("finance@mics.demo", "Farid Finance", "FINANCE_OFFICER", None, None, 500_000),
    ("approver@mics.demo", "Anele Approver", "APPROVER", "Infrastructure", None, 250_000),
    ("manager@mics.demo", "Mpho Manager", "MANAGER", None, None, 2_000_000),
    ("auditor@mics.demo", "Aisha Auditor", "AUDITOR", None, None, None),
    (
        "accounts@ubuntucleaning.demo",
        "Ubuntu Cleaning Accounts",
        "SUPPLIER",
        None,
        "Ubuntu Cleaning",
        None,
    ),
    (
        "accounts@thutosupplies.demo",
        "Thuto Supplies Accounts",
        "SUPPLIER",
        None,
        "Thuto Supplies",
        None,
    ),
]
