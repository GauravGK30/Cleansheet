"""Content for the "Learn Data Cleaning" page. Data only: the page never touches uploaded files.

Every statement here describes what CleanSheet really does (fixed rules, no AI, no guessing).
Optional keys: `tip` (a short "In CleanSheet" note) and example["show_spaces"] (draw spaces as a middle dot).
"""
from __future__ import annotations

GROUPS = ["Rows and gaps", "Ways to fill a gap", "Text clean-up", "Types and identifiers"]

TOPICS: list[dict] = [
    # ------------------------------------------------------------------ Rows and gaps
    {
        "slug": "remove-duplicates",
        "title": "Removing Duplicate Rows",
        "group": "Rows and gaps",
        "where_in_app": "Step 1 · Basic cleaning",
        "summary": "Finds rows that repeat and keeps only the first copy of each.",
        "why": "Repeated rows double-count orders, customers and money. Removing them makes counts and totals trustworthy.",
        "when_use": [
            "A file was exported or merged more than once.",
            "Every row should describe a different thing, such as one order per row.",
            "You are about to count rows or add up a column.",
        ],
        "when_avoid": [
            "Two real events can look identical, such as two separate purchases of the same item on the same day. Match on an ID column instead.",
            "You match on only some columns: rows that differ in the other columns are removed too, so pick columns that truly identify a row.",
        ],
        "tip": "You can match on all columns or only the ones you choose. If trimming is switched on, it runs first, so 'Ann ' and 'Ann' count as the same.",
        "example": {
            "caption": "Rows 3 and 5 repeat earlier rows, so only their first copies stay.",
            "columns": ["Order", "Customer", "Amount"],
            "before": [
                ["1001", "Ann Lee", "25.00"],
                ["1002", "Bo Chen", "40.00"],
                ["1001", "Ann Lee", "25.00"],
                ["1003", "Cy Diaz", "15.50"],
                ["1002", "Bo Chen", "40.00"],
            ],
            "after": [
                ["1001", "Ann Lee", "25.00"],
                ["1002", "Bo Chen", "40.00"],
                ["1003", "Cy Diaz", "15.50"],
            ],
            "removed_rows": [2, 4],
            "changed_cells": [],
        },
        "image": "dedupe.svg",
        "image_alt": "Five spreadsheet rows, two of them struck through as repeats, with an arrow to a three-row sheet that keeps the first copy of each.",
    },
    {
        "slug": "handling-missing-values",
        "title": "Handling Missing Values",
        "group": "Rows and gaps",
        "where_in_app": "Step 1 · Basic cleaning, then Step 2 · Advanced cleaning",
        "summary": "Spots empty cells and lets you decide, one column at a time, what to do: fill them, remove the row, or keep them missing.",
        "why": "Empty cells break totals and averages and can hide real problems. A deliberate choice beats a silent guess.",
        "when_use": [
            "A column has blanks or placeholders such as N/A, null, - or ?.",
            "You can say what a sensible value would be.",
            "Charts, sums or averages need complete data.",
        ],
        "when_avoid": [
            "An empty cell is meaningful, for example 'no discount' or 'not shipped yet'. Keep it missing.",
            "You would have to invent the value. A wrong fill is worse than a gap.",
        ],
        "tip": "Step 1 turns placeholder words into real empty cells. Step 2 shows controls only for columns that have gaps, and only the methods that suit that column's type. Nothing changes until you choose it.",
        "example": {
            "caption": "Age is filled with the median. City is kept missing on purpose.",
            "columns": ["Customer", "Age", "City"],
            "before": [
                ["Ann", "34", "Pune"],
                ["Bo", None, "Delhi"],
                ["Cy", "40", None],
                ["Di", "37", "Pune"],
            ],
            "after": [
                ["Ann", "34", "Pune"],
                ["Bo", "37", "Delhi"],
                ["Cy", "40", None],
                ["Di", "37", "Pune"],
            ],
            "removed_rows": [],
            "changed_cells": [[1, 1]],
        },
        "image": "missing.svg",
        "image_alt": "An Age column with one empty, selected cell and three arrows leading to the choices: fill it with a value, remove that row, or keep it missing.",
    },
    # ------------------------------------------------------------------ Ways to fill a gap
    {
        "slug": "mean-imputation",
        "title": "Mean Imputation",
        "group": "Ways to fill a gap",
        "where_in_app": "Step 2 · Advanced cleaning · Missing values",
        "summary": "Fills each empty cell with the average of the other numbers in the column.",
        "why": "It keeps the column's overall average unchanged and is quick for numbers that are spread fairly evenly.",
        "when_use": [
            "The column holds numbers such as prices, ages or scores.",
            "Values are fairly even, with no extreme outliers.",
            "Only a small share of the cells is missing.",
        ],
        "when_avoid": [
            "A few extreme values drag the average. Use the median instead.",
            "The column is an ID, a date or a Yes/No flag. An average means nothing there, so CleanSheet never offers it.",
            "Many cells are missing. An average then hides a lot of unknowns.",
        ],
        "tip": "The result is rounded to the column's own decimal places, so a whole-number column gets a whole number.",
        "example": {
            "caption": "The mean of 2.50, 3.50 and 3.00 is 3.00.",
            "columns": ["Item", "Price"],
            "before": [["Tea", "2.50"], ["Coffee", "3.50"], ["Milk", None], ["Juice", "3.00"]],
            "after": [["Tea", "2.50"], ["Coffee", "3.50"], ["Milk", "3.00"], ["Juice", "3.00"]],
            "removed_rows": [],
            "changed_cells": [[2, 1]],
        },
        "image": "mean.svg",
        "image_alt": "Bar chart of three prices with a dashed line at their mean. The missing fourth bar is drawn hatched and reaches the mean line.",
    },
    {
        "slug": "median-imputation",
        "title": "Median Imputation",
        "group": "Ways to fill a gap",
        "where_in_app": "Step 2 · Advanced cleaning · Missing values",
        "summary": "Fills each empty cell with the middle value of the other numbers: half are smaller, half are larger.",
        "why": "A few extreme values barely move the median, so the fill stays typical.",
        "when_use": [
            "The numbers are lopsided, as with salaries, prices or order sizes.",
            "There are outliers you do not want to influence the fill.",
            "CleanSheet itself suggests it when the values are clearly skewed.",
        ],
        "when_avoid": [
            "The column is an ID, a date or a Yes/No flag. A middle value means nothing there.",
            "Only a handful of numbers are known. Any single fill is a weak guess then.",
        ],
        "tip": "Like the mean, the median is rounded to the column's decimal places.",
        "example": {
            "caption": "The median is 33000. The mean would be 86500, which fits nobody.",
            "columns": ["Employee", "Salary"],
            "before": [["Ann", "30000"], ["Bo", "32000"], ["Cy", None], ["Di", "34000"], ["Eve", "250000"]],
            "after": [["Ann", "30000"], ["Bo", "32000"], ["Cy", "33000"], ["Di", "34000"], ["Eve", "250000"]],
            "removed_rows": [],
            "changed_cells": [[2, 1]],
        },
        "image": "median.svg",
        "image_alt": "A number line with a stack of three salaries near 30 to 34 thousand and one far-right salary of 250 thousand. The mean marker sits far from the stack, the median marker sits on it.",
    },
    {
        "slug": "mode-imputation",
        "title": "Mode Imputation",
        "group": "Ways to fill a gap",
        "where_in_app": "Step 2 · Advanced cleaning · Missing values",
        "summary": "Fills each empty cell with the value that appears most often in the column.",
        "why": "It is the one 'typical value' that also works for words, and it suits numbers that act like labels, such as shoe sizes.",
        "when_use": [
            "Text or category columns such as city, department or status.",
            "One value clearly dominates the column.",
            "Numbers that behave like labels, for example shoe size.",
        ],
        "when_avoid": [
            "No value stands out. A tie is settled by a rule, not by the truth.",
            "The gap probably means something else, such as 'not applicable'.",
            "The column is an ID. Guessing an ID would point at the wrong record, so CleanSheet never offers it.",
        ],
        "tip": "If values tie, CleanSheet takes the smallest number, or the first one in A to Z order for text, and tells you it did.",
        "example": {
            "caption": "Pune appears 3 times and Delhi once, so Pune is the mode.",
            "columns": ["Order", "City"],
            "before": [["1", "Pune"], ["2", "Pune"], ["3", None], ["4", "Delhi"], ["5", "Pune"]],
            "after": [["1", "Pune"], ["2", "Pune"], ["3", "Pune"], ["4", "Delhi"], ["5", "Pune"]],
            "removed_rows": [],
            "changed_cells": [[2, 1]],
        },
        "image": "mode.svg",
        "image_alt": "A bar chart where the Pune bar is tallest and highlighted, next to an empty city cell that is filled with Pune.",
    },
    {
        "slug": "custom-value-imputation",
        "title": "Custom Value Imputation",
        "group": "Ways to fill a gap",
        "where_in_app": "Step 2 · Advanced cleaning · Missing values",
        "summary": "Fills every empty cell in the column with a value you type yourself.",
        "why": "You know your data best. A clear label such as 'Unknown' keeps the gap visible instead of hiding it behind a guess.",
        "when_use": [
            "There is an obvious default, such as 0 for 'no discount'.",
            "You want a visible label such as 'Unknown' or 'Not provided'.",
            "No statistic suits the column.",
        ],
        "when_avoid": [
            "The value would mislead calculations, for example 0 for a missing age.",
            "A better, exact value can be recovered from related columns or a formula.",
        ],
        "tip": "CleanSheet checks that your value fits the column: a number for number columns, YYYY-MM-DD for date columns, and for Yes/No columns a value already in the column.",
        "example": {
            "caption": "The empty status becomes the text you typed.",
            "columns": ["Order", "Status"],
            "before": [["1001", "Shipped"], ["1002", None], ["1003", "Delivered"]],
            "after": [["1001", "Shipped"], ["1002", "Pending review"], ["1003", "Delivered"]],
            "removed_rows": [],
            "changed_cells": [[1, 1]],
        },
        "image": "custom-value.svg",
        "image_alt": "An empty cell, an arrow to a text box where a value is typed, and an arrow to the cell filled with that value. Three small cards list what fits number, date and Yes/No columns.",
    },
    {
        "slug": "group-based-imputation",
        "title": "Group-Based Imputation",
        "group": "Ways to fill a gap",
        "where_in_app": "Step 2 · Advanced cleaning · Missing values (called 'Recover from a related column')",
        "summary": "In CleanSheet this is an exact lookup: a missing value is copied from other rows that share the same key, such as the same customer ID.",
        "why": "The answer is already in your data. A lookup is exact, while an average is only an estimate.",
        "when_use": [
            "A key column (customer ID, product code) always goes with the same value (name, category, date).",
            "The key appears on several rows.",
            "The column to fill is text, a category, an ID or a date.",
        ],
        "when_avoid": [
            "One key sometimes has two different values. CleanSheet does not use that key.",
            "Every key appears only once, because nothing then shows the link is stable.",
            "You want a group average. CleanSheet does an exact lookup and never averages.",
        ],
        "tip": "CleanSheet offers this only when it finds a key that works, and tells you how many gaps it can fill. Gaps it cannot match stay missing.",
        "example": {
            "caption": "C01 always means Ann Lee, so that gap is filled. C03 has no known name, so it stays empty.",
            "columns": ["Customer ID", "Customer"],
            "before": [["C01", "Ann Lee"], ["C02", "Bo Chen"], ["C01", None], ["C02", "Bo Chen"], ["C03", None]],
            "after": [["C01", "Ann Lee"], ["C02", "Bo Chen"], ["C01", "Ann Lee"], ["C02", "Bo Chen"], ["C03", None]],
            "removed_rows": [],
            "changed_cells": [[2, 1]],
        },
        "image": "lookup.svg",
        "image_alt": "Rows grouped by customer ID in two colours. An empty name in the C01 group is filled from the C01 row above it, while the lone C03 row stays empty.",
    },
    {
        "slug": "formula-based-recovery",
        "title": "Formula-Based Recovery",
        "group": "Ways to fill a gap",
        "where_in_app": "Step 2 · Advanced cleaning · Missing values (calculated number columns)",
        "summary": "Recalculates a missing number from other columns, such as revenue = quantity × unit price.",
        "why": "The result is exact, not an estimate, so your totals still add up.",
        "when_use": [
            "A column is always the product or the difference of two other columns, as with revenue, cost and margin.",
            "The source columns are filled in on that row.",
        ],
        "when_avoid": [
            "The relationship does not hold on your rows, for example when discounts or taxes are added. CleanSheet only offers a formula after checking it on your data.",
            "A source number is missing too. That row stays empty.",
        ],
        "tip": "CleanSheet finds formulas in your data: multiplication (quantity × price = revenue) and subtraction (revenue − cost = margin). It needs at least five complete rows and the formula must hold on nearly all of them. A row is filled only when every source value on it is present.",
        "example": {
            "caption": "3 × 4.00 = 12.00. The row with no Qty has nothing to calculate from, so it stays empty.",
            "columns": ["Qty", "Unit price", "Revenue"],
            "before": [["2", "5.00", "10.00"], ["3", "4.00", None], [None, "2.50", None], ["4", "2.50", "10.00"]],
            "after": [["2", "5.00", "10.00"], ["3", "4.00", "12.00"], [None, "2.50", None], ["4", "2.50", "10.00"]],
            "removed_rows": [],
            "changed_cells": [[1, 2]],
        },
        "image": "formula.svg",
        "image_alt": "Quantity times unit price equals revenue: with both sources present the empty revenue cell is calculated as 12.00. In a second row the quantity is missing, so revenue stays empty.",
    },
    # ------------------------------------------------------------------ Text clean-up
    {
        "slug": "text-standardization",
        "title": "Text Standardization",
        "group": "Text clean-up",
        "where_in_app": "Step 2 · Advanced cleaning · Text standardization",
        "summary": "Makes the same thing look the same everywhere: one spelling, one case, one spacing.",
        "why": "'NYC', 'nyc' and 'New York ' are different values to a computer. Standardizing makes counting, grouping and duplicate checks work.",
        "when_use": [
            "Category columns typed by hand, such as cities, departments or statuses.",
            "You plan to count or group by the column.",
        ],
        "when_avoid": [
            "The column is an ID. CleanSheet protects IDs from text changes and keeps leading zeros.",
            "Case carries meaning, as in product codes where 'x' and 'X' differ.",
            "The column holds numbers or dates. These tools are not offered there.",
        ],
        "tip": "Steps always run in this order: trim, collapse repeated spaces, change case, then find and replace. The tools appear only for text and category columns.",
        "example": {
            "caption": "Trim, collapse spaces, Title Case, then the rule nyc → New York. A dot (·) marks a space.",
            "columns": ["Customer", "City"],
            "before": [["Ann", "new  york"], ["Bo", "NEW YORK"], ["Cy", "New York "], ["Di", "nyc"]],
            "after": [["Ann", "New York"], ["Bo", "New York"], ["Cy", "New York"], ["Di", "New York"]],
            "removed_rows": [],
            "changed_cells": [[0, 1], [1, 1], [2, 1], [3, 1]],
            "show_spaces": True,
        },
        "image": "text-standardization.svg",
        "image_alt": "Four messy spellings of New York flow through four steps, trim, collapse spaces, change case and find and replace, into one standard value.",
    },
    {
        "slug": "whitespace-trimming",
        "title": "Whitespace Trimming",
        "group": "Text clean-up",
        "where_in_app": "Step 1 · Basic cleaning (and the Step 2 text tools)",
        "summary": "Removes spaces at the start and end of a cell.",
        "why": "Invisible spaces make 'Ann Lee' and 'Ann Lee ' different values. They break duplicate checks, lookups and sorting.",
        "when_use": [
            "Almost always: text copied from websites, PDFs or other systems often carries extra spaces.",
            "Before removing duplicates or comparing values.",
        ],
        "when_avoid": [
            "The spaces themselves carry meaning, as in fixed-width codes padded with spaces. This is rare.",
        ],
        "tip": "Step 1 trims every column. In Step 2, text columns can also collapse repeated spaces inside the text, so 'new  york' becomes 'new york'.",
        "example": {
            "caption": "Spaces at the start and end are removed. A dot (·) marks a space.",
            "columns": ["ID", "Name"],
            "before": [["1", " Ann Lee"], ["2", "Bo Chen  "], ["3", "Cy Diaz"]],
            "after": [["1", "Ann Lee"], ["2", "Bo Chen"], ["3", "Cy Diaz"]],
            "removed_rows": [],
            "changed_cells": [[0, 1], [1, 1]],
            "show_spaces": True,
        },
        "image": "trim.svg",
        "image_alt": "A cell with hatched padding either side of the name Ann Lee, shown as not equal to a clean Ann Lee cell. After trimming, both cells are equal.",
    },
    {
        "slug": "find-and-replace",
        "title": "Find and Replace",
        "group": "Text clean-up",
        "where_in_app": "Step 2 · Advanced cleaning · Text standardization",
        "summary": "Swaps one piece of text for another, in the columns you choose.",
        "why": "It fixes the same typo or alias everywhere in one go, such as 'USA' and 'U.S.A.' both becoming 'United States'.",
        "when_use": [
            "A known spelling or abbreviation appears many times.",
            "You want to retire an old label.",
        ],
        "when_avoid": [
            "You need patterns or wildcards. CleanSheet matches the exact text only.",
            "The text may sit inside longer words: 'art' would also change 'Smart' unless you tick 'whole cell'.",
            "The column is an ID, a number or a date. The tool is not offered there.",
        ],
        "tip": "Matching ignores upper and lower case unless you tick 'match case'. 'Whole cell' replaces only cells that are exactly the text. Find and replace runs last, after trim, spaces and case.",
        "example": {
            "caption": "Two rules: USA → United States and U.S.A. → United States. 'usa' matches too, because case is ignored.",
            "columns": ["Customer", "Country"],
            "before": [["Ann", "USA"], ["Bo", "U.S.A."], ["Cy", "United States"], ["Di", "usa"]],
            "after": [["Ann", "United States"], ["Bo", "United States"], ["Cy", "United States"], ["Di", "United States"]],
            "removed_rows": [],
            "changed_cells": [[0, 1], [1, 1], [3, 1]],
        },
        "image": "find-replace.svg",
        "image_alt": "A rule that finds USA and replaces it with United States, applied to a column: USA and usa change, while U.S.A. is a different spelling and needs its own rule.",
    },
    # ------------------------------------------------------------------ Types and identifiers
    {
        "slug": "data-type-conversion",
        "title": "Data Type Conversion",
        "group": "Types and identifiers",
        "where_in_app": "Step 2 · Advanced cleaning · Data types",
        "summary": "Changes how a column's values are stored, for example text to whole number, number to decimal, or text to date.",
        "why": "Numbers stored as text cannot be added, and dates stored as text cannot be sorted or compared properly. The right type makes the spreadsheet behave.",
        "when_use": [
            "Numbers arrived as text, with commas or a '.0' ending.",
            "You want a consistent number of decimals.",
            "A text column really holds dates.",
        ],
        "when_avoid": [
            "The values are really labels, such as phone numbers or postcodes. Keep them as text.",
            "The column contains any invalid value. CleanSheet then skips the whole column instead of half-converting it.",
        ],
        "tip": "A whole number cannot be 12.5, so that column is skipped with a warning and the original values stay. Options depend on the column: text can become a date; numbers can become whole numbers, decimals or text; dates can be standardized or kept as text; IDs stay text.",
        "example": {
            "caption": "Text to whole number: the comma and the '.0' go. Every value was valid, so the column converts.",
            "columns": ["Item", "Qty"],
            "before": [["Pens", "1,200"], ["Ink", "12.0"], ["Clips", "7"]],
            "after": [["Pens", "1200"], ["Ink", "12"], ["Clips", "7"]],
            "removed_rows": [],
            "changed_cells": [[0, 1], [1, 1]],
        },
        "image": "type-conversion.svg",
        "image_alt": "Three conversions: the text 1,200 becomes the number 1200, the text 2024-03-05 becomes a date, and the text 12.5 cannot become a whole number so the column is skipped.",
    },
    {
        "slug": "date-standardization",
        "title": "Date Standardization",
        "group": "Types and identifiers",
        "where_in_app": "Step 2 · Advanced cleaning · Data types",
        "summary": "Rewrites every date in a column in one format, YYYY-MM-DD, for example 2024-03-05.",
        "why": "Dates written in mixed styles cannot be sorted or compared reliably. YYYY-MM-DD sorts in the right order and is understood everywhere.",
        "when_use": [
            "Dates arrive as day/month/year, with month names, or with dashes and slashes.",
            "You will sort, filter or compare by date.",
        ],
        "when_avoid": [
            "The column mixes formats or holds invalid dates. The whole column is skipped with a warning and the originals stay.",
            "The values include a time of day. CleanSheet never drops times silently, so it skips the column and tells you.",
        ],
        "tip": "03/04/2024 could be 3 April or March 4. CleanSheet only converts formats it can read exactly, and asks which order the column uses when the data cannot tell.",
        "example": {
            "caption": "17 cannot be a month, so this column is day-first. Result: YYYY-MM-DD.",
            "columns": ["Order", "Date"],
            "before": [["A1", "05/03/2024"], ["A2", "17/03/2024"], ["A3", "30/04/2024"]],
            "after": [["A1", "2024-03-05"], ["A2", "2024-03-17"], ["A3", "2024-04-30"]],
            "removed_rows": [],
            "changed_cells": [[0, 1], [1, 1], [2, 1]],
        },
        "image": "date-standardization.svg",
        "image_alt": "Three spellings of the same date, 05-Mar-2024, March 5 2024 and 05/03/2024, all become 2024-03-05. A note explains that 03/04/2024 is ambiguous, so CleanSheet asks which order is used.",
    },
    {
        "slug": "binary-column-conversion",
        "title": "Binary Column Conversion",
        "group": "Types and identifiers",
        "where_in_app": "Step 1 · Basic cleaning",
        "summary": "Rewrites a two-state column (TRUE/FALSE, Yes/No, 1/0) in the style you prefer.",
        "why": "One consistent style per column is easier to read, filter and import into other tools.",
        "when_use": [
            "The column only ever holds two states, in any of these styles: TRUE/FALSE, Yes/No, 1/0, Y/N or T/F.",
            "Another system expects a particular style.",
        ],
        "when_avoid": [
            "The column has a third value such as 'maybe'. It is not treated as a flag, so nothing is converted.",
            "A column of only 1s and 0s may really be a number, such as a count. CleanSheet flags it so you decide.",
        ],
        "tip": "Each column is converted on its own, so one can become Yes/No while another stays 1/0. Empty cells stay empty.",
        "example": {
            "caption": "TRUE/FALSE becomes Yes/No.",
            "columns": ["Customer", "Subscribed"],
            "before": [["Ann", "TRUE"], ["Bo", "FALSE"], ["Cy", "TRUE"]],
            "after": [["Ann", "Yes"], ["Bo", "No"], ["Cy", "Yes"]],
            "removed_rows": [],
            "changed_cells": [[0, 1], [1, 1], [2, 1]],
        },
        "image": "binary.svg",
        "image_alt": "Three two-state columns, TRUE and FALSE, 1 and 0, and Y and N, each converted to Yes and No. A note says a column of only 1s and 0s may be a number and needs confirming.",
    },
    {
        "slug": "identifier-handling",
        "title": "Identifier Handling",
        "group": "Types and identifiers",
        "where_in_app": "Protected in every step",
        "summary": "Treats ID-like columns (customer_id, invoice_no, SKU) as protected text: no averages, no changed case, no guessing.",
        "why": "An ID names exactly one thing. Turning '00123' into 123, or inventing a number, would point at the wrong record.",
        "when_use": [
            "Codes that identify something: customer IDs, invoice numbers, SKUs, postcodes.",
            "Any column where leading zeros must survive.",
        ],
        "when_avoid": [
            "The column is really a quantity that just has 'id' in its name. CleanSheet looks at the values as well as the name and asks you to confirm when it is unsure; you can change the type.",
        ],
        "tip": "A missing ID can be recovered from a related column when the link is exact, or filled with a value you type. You can also remove those rows or keep them missing. Averages and guesses are never offered.",
        "example": {
            "caption": "Nothing changes: the zeros are kept and the missing ID is not invented.",
            "columns": ["Customer ID", "Customer"],
            "before": [["00123", "Ann"], ["00456", "Bo"], [None, "Cy"], ["00789", "Di"]],
            "after": [["00123", "Ann"], ["00456", "Bo"], [None, "Cy"], ["00789", "Di"]],
            "removed_rows": [],
            "changed_cells": [],
        },
        "image": "identifier.svg",
        "image_alt": "The ID 00123 sits in a cell with a lock icon and stays as text. The number 123 is crossed out, and the actions average, change case and convert to number are crossed out as never applied to an ID.",
    },
]

EXPECTED_TITLES = [
    "Removing Duplicate Rows", "Handling Missing Values", "Mean Imputation", "Median Imputation",
    "Mode Imputation", "Custom Value Imputation", "Group-Based Imputation", "Formula-Based Recovery",
    "Text Standardization", "Whitespace Trimming", "Find and Replace", "Data Type Conversion",
    "Date Standardization", "Binary Column Conversion", "Identifier Handling",
]

_REQUIRED = ("slug", "title", "group", "where_in_app", "summary", "why", "when_use", "when_avoid",
             "example", "image", "image_alt")


def validate_topics(topics: list[dict] = TOPICS, groups: list[str] = GROUPS) -> None:
    """Raise ValueError when the content is malformed (used by the tests, not at import time)."""
    slugs = set()
    for t in topics:
        missing = [k for k in _REQUIRED if k not in t]
        if missing:
            raise ValueError(f"{t.get('title', '?')}: missing {missing}")
        if t["slug"] in slugs:
            raise ValueError(f"duplicate slug {t['slug']}")
        slugs.add(t["slug"])
        if t["group"] not in groups:
            raise ValueError(f"{t['title']}: unknown group")
        ex, width = t["example"], len(t["example"]["columns"])
        for rows in (ex["before"], ex["after"]):
            if any(len(r) != width for r in rows):
                raise ValueError(f"{t['title']}: ragged example")
