# FitFindr

A thrift-shopping assistant agent that takes a natural language query, finds matching secondhand listings, and returns outfit suggestions and a social-media-ready caption — all in one pipeline.

## Setup

```bash
# Clone and enter the repo
cd ai201-project2-fitfindr-starter

# Create and activate a virtual environment (Python 3.11 recommended)
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Create a `.env` file in the project root with your Groq API key (free at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

## Running the App

```bash
python app.py
```

Open the URL shown in your terminal (usually `http://localhost:7860`). Type a query like `"vintage graphic tee under $30, size M"`, choose a wardrobe, and hit **Find it**.

To run the agent from the terminal without the UI:

```bash
python agent.py
```

To run tests:

```bash
pytest tests/ -v
```

## Project Structure

```
├── agent.py              # Planning loop — run_agent()
├── app.py                # Gradio UI — handle_query()
├── tools.py              # Three standalone tools
├── utils/
│   └── data_loader.py    # Helpers for loading listings and wardrobe data
├── data/
│   ├── listings.json     # 40 mock secondhand listings
│   └── wardrobe_schema.json
├── tests/
│   └── test_tools.py     # pytest tests for all three tools
└── planning.md           # Design spec written before implementation
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

**Purpose:** Finds secondhand listings that match a natural language description, with optional size and price filters.

**Inputs:**
- `description` (`str`): Free-text keywords, e.g. `"vintage graphic tee"`. Matched case-insensitively against each listing's title, description, category, style tags, and colors.
- `size` (`str | None`): Size string to filter on, e.g. `"M"` or `"S/M"`. Uses substring match so `"M"` also matches `"S/M"`. Pass `None` to skip.
- `max_price` (`float | None`): Upper bound on price (inclusive). Pass `None` to skip.

**Output:** A `list[dict]` of matching listings sorted by relevance score (highest first). Each dict contains `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`. Returns `[]` — never raises — if nothing matches.

---

### `suggest_outfit(new_item, wardrobe)`

**Purpose:** Calls the Groq LLM (`llama-3.3-70b-versatile`) to suggest 1–2 complete outfits pairing the thrift find with the user's existing wardrobe. Handles the empty-wardrobe case by switching to general styling advice instead of named pairings.

**Inputs:**
- `new_item` (`dict`): A listing dict from `search_listings`.
- `wardrobe` (`dict`): A wardrobe dict with an `"items"` key containing a list of wardrobe item dicts (each with `name`, `category`, `colors`, `style_tags`, `notes`). The list may be empty.

**Output:** A non-empty `str` with outfit suggestions. If the wardrobe is empty, returns a paragraph of general styling advice (vibe, silhouette, color pairings). Returns a fallback string on LLM error — never raises.

---

### `create_fit_card(outfit, new_item)`

**Purpose:** Calls the Groq LLM at temperature 0.9 to generate a 2–4 sentence Instagram/TikTok-style OOTD caption for the thrift find. Output varies each run due to high temperature.

**Inputs:**
- `outfit` (`str`): The outfit suggestion string from `suggest_outfit`. Must be non-empty — function guards against this before calling the LLM.
- `new_item` (`dict`): The listing dict, used to pull `title`, `price`, and `platform` into the caption.

**Output:** A `str` of 2–4 casual sentences that mention the item name, price, and platform each exactly once. Returns a descriptive error string if `outfit` is empty or the LLM fails — never raises.

---

## Planning Loop

`run_agent(query, wardrobe)` in `agent.py` runs the three tools in a fixed sequence, using a `session` dict to carry state between steps. Here is the exact decision logic:

**Step 1 — Parse the query.** Regex extracts `max_price` (patterns like `"under $30"`, `"max $25"`) and `size` (patterns like `"size M"`, `"in size S/M"`) from the raw query string. The price fragment is stripped first, then the size fragment is found in the already-stripped string to avoid index misalignment. The remaining text becomes `description`. No LLM call is needed for parsing.

**Step 2 — Search.** `search_listings(description, size, max_price)` is called. If it returns an empty list, `session["error"]` is set to a message explaining what failed and what to try, and the function returns immediately. `suggest_outfit` and `create_fit_card` are **never called** on an empty result.

**Step 3 — Select item.** `session["selected_item"] = results[0]` (highest relevance score).

**Step 4 — Suggest outfit.** `suggest_outfit(selected_item, wardrobe)` is called. Even if the LLM errors, the fallback string flows forward — the pipeline does not abort.

**Step 5 — Create fit card.** `create_fit_card(outfit_suggestion, selected_item)` is called. Same resilience: LLM errors return a descriptive error string rather than crashing.

**Step 6 — Return session.** The caller receives the complete session dict and can inspect every intermediate value.

The loop runs each tool exactly once in order. It does not retry, iterate, or re-prompt the user.

---

## State Management

All state lives in a single `session` dict created at the start of `run_agent`. It is local to one function call — nothing persists between queries.

| Key | Type | Written by | Read by |
|-----|------|-----------|---------|
| `query` | `str` | `run_agent` init | reference only |
| `parsed` | `dict` (`description`, `size`, `max_price`) | Step 1 | Step 2 (`search_listings` call) |
| `search_results` | `list[dict]` | Step 2 | emptiness check; selecting `selected_item` |
| `selected_item` | `dict` | Step 3 (`results[0]`) | Steps 4, 5, and final output |
| `wardrobe` | `dict` | `run_agent` init | Step 4 (`suggest_outfit`) |
| `outfit_suggestion` | `str` | Step 4 | Step 5 (`create_fit_card`), final output |
| `fit_card` | `str` | Step 5 | final output |
| `error` | `str \| None` | Step 2 on empty results | caller (`handle_query`, CLI) |

`wardrobe` is passed as a parameter to `run_agent` and stored in the session so it's accessible anywhere in the loop without threading it through multiple function arguments.

---

## Error Handling

### `search_listings` — no results

**Trigger:** Query that matches nothing after price/size filtering, e.g. `"designer ballgown"` in size `XXS` under `$5`.

**Tested with:**
```
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
# Output: []
```

**Agent response:** Returns immediately with `session["error"]` set to:
> "No listings found for 'designer ballgown' in size XXS under $5. Try broader keywords, a different size, or a higher budget."

`suggest_outfit` and `create_fit_card` are not called.

---

### `suggest_outfit` — empty wardrobe

**Trigger:** User selects "Empty wardrobe (new user)" in the UI, or `get_empty_wardrobe()` is passed directly.

**Tested with:**
```
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
```

**Agent response:** The LLM is still called, but with a different prompt asking for general styling advice rather than specific wardrobe pairings. Returns a paragraph describing vibe, silhouette, and color suggestions. Never returns an empty string.

---

### `create_fit_card` — empty outfit string

**Trigger:** `outfit` argument is `""` or whitespace-only (e.g. if `suggest_outfit` had previously failed and returned an empty string).

**Tested with:**
```
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
# Output: [fit card unavailable — outfit suggestion was empty]
```

**Agent response:** Returns `"[fit card unavailable — outfit suggestion was empty]"` immediately, without making an LLM call. The pipeline continues and includes this string in the final output rather than crashing.

---

## Spec Reflection

Writing `planning.md` in full detail before coding turned out to be genuinely useful, not just a box to check. The most valuable part was writing the exact state management table — deciding upfront which keys existed, what type they held, and which step wrote vs. read each one meant that when I implemented `run_agent`, there were no ambiguous handoffs. The session dict came out matching the spec almost exactly.

The one thing I changed from the spec: I originally planned to use a Groq LLM call to parse the user's query into `description`, `size`, and `max_price`. During implementation I switched to regex instead. An extra LLM call for something as structured as "find a number after the word 'under'" added latency and a potential failure point without much benefit. The regex approach handles all the query patterns in the example set cleanly, and is easier to test deterministically. I updated `planning.md` to reflect this decision.

The architecture diagram was the most useful artifact when implementing the planning loop — having the error branch drawn explicitly made it obvious that `suggest_outfit` should never be reached when `search_results` is empty, which is easy to forget if you're just working from a text description.

---

## AI Tool Usage

### Instance 1 — Implementing `search_listings`

I pasted the Tool 1 spec block from `planning.md` into Claude (inputs, return value, failure mode, and the note to use `load_listings()` from the data loader). I asked it to implement `search_listings()` using keyword token overlap scoring.

The generated code scored listings by checking if query tokens appeared anywhere in a concatenated string of `title + description + style_tags + colors`. I reviewed it and caught one omission: `category` was not included in the searchable text, which meant searching `"shoes"` returned zero results even though the dataset has a `shoes` category. I added `category` to the concatenated string before accepting the output. I then tested with three queries (`"vintage graphic tee"`, `"chunky platform shoes"`, `"cottagecore"`) and confirmed the results were sensible.

### Instance 2 — Implementing the planning loop

I pasted the `## Planning Loop`, `## State Management`, and `## Architecture` sections of `planning.md` into Claude, along with the signatures of all three tools. I asked it to implement `run_agent(query, wardrobe) -> dict` in `agent.py`.

The generated code had the right structure but one logic bug: it ran the size regex on the original query string, then tried to strip the size fragment from the already-price-stripped description using indices from the original string. When both price and size were present in a query, the size stripping landed in the wrong position, leaving a stray letter in `description` (e.g., `"vintage graphic tee M"` instead of `"vintage graphic tee"`). I fixed this by running the size regex on the price-stripped string rather than the original query. I verified the fix against five query patterns before committing.
