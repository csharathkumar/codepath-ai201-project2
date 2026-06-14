# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Loads all 40 listings from `data/listings.json`, filters by size and max_price if provided, then scores the remaining listings by keyword overlap between the `description` query and each listing's `title`, `description`, `style_tags`, and `colors` fields. Returns the top matches sorted by score descending.

**Input parameters:**
- `description` (str): Free-text keywords describing what the user wants, e.g. `"vintage graphic tee"`. Matched case-insensitively against listing title, description, style_tags (joined), and colors (joined).
- `size` (str | None): Size string to filter on, e.g. `"M"` or `"S/M"`. Case-insensitive substring match against `listing["size"]` — so `"M"` matches both `"M"` and `"S/M"`. Pass `None` to skip size filtering.
- `max_price` (float | None): Upper bound on `listing["price"]` (inclusive). Pass `None` to skip price filtering.

**What it returns:**
A `list[dict]` of matching listing dicts, sorted by relevance score (highest first), each containing:
- `id` (str): unique listing ID, e.g. `"lst_007"`
- `title` (str): listing title, e.g. `"Vintage Graphic Band Tee — Faded Black"`
- `description` (str): seller's full description text
- `category` (str): one of `tops`, `bottoms`, `outerwear`, `shoes`, `accessories`
- `style_tags` (list[str]): style descriptors, e.g. `["vintage", "grunge", "graphic tee"]`
- `size` (str): size string, e.g. `"M"` or `"S/M"`
- `condition` (str): one of `excellent`, `good`, `fair`
- `price` (float): listing price in USD, e.g. `24.0`
- `colors` (list[str]): color list, e.g. `["black", "grey"]`
- `brand` (str | None): brand name or `null`
- `platform` (str): one of `depop`, `thredUp`, `poshmark`

Returns an empty list (`[]`) — never raises — if no listings pass the filters or all scores are 0.

**What happens if it fails or returns nothing:**
If the returned list is empty, the planning loop sets `session["error"] = "No listings found for '{description}' in size {size} under ${max_price}. Try broader keywords, a different size, or a higher budget."` and returns that message to the user without calling the remaining tools.

---

### Tool 2: suggest_outfit

**What it does:**
Calls the Groq LLM (`llama3-8b-8192`) with a prompt that includes the new thrift item's details and the user's existing wardrobe, asking it to suggest 1–2 complete outfits. If the wardrobe is empty, asks for general styling advice instead of named pairings.

**Input parameters:**
- `new_item` (dict): A listing dict from `search_listings` (same fields: `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`).
- `wardrobe` (dict): A wardrobe dict with a single key `"items"` containing a list of wardrobe item dicts. Each wardrobe item has: `id` (str), `name` (str), `category` (str), `colors` (list[str]), `style_tags` (list[str]), `notes` (str | None). The list may be empty.

**What it returns:**
A non-empty `str` containing 1–2 outfit suggestions. Each suggestion names specific wardrobe pieces (by their `name` field) and describes how they combine with the new item, including footwear and accessories where relevant. If the wardrobe is empty, returns a paragraph of general styling advice covering vibe, silhouette, and color pairings for the item.

**What happens if it fails or returns nothing:**
If the LLM returns an empty string or raises an exception, the planning loop sets `session["outfit_suggestion"] = "Couldn't generate outfit suggestions right now. The item still looks great — try pairing it with basics in similar colors."` and proceeds to `create_fit_card` with that fallback string.

---

### Tool 3: create_fit_card

**What it does:**
Calls the Groq LLM (`llama3-8b-8192`) at a higher temperature (~0.9) to generate a 2–4 sentence Instagram/TikTok-style OOTD caption for the thrift find. The caption mentions the item name, price, and platform once each, and captures the outfit's specific vibe.

**Input parameters:**
- `outfit` (str): The outfit suggestion string from `suggest_outfit`. Must be non-empty.
- `new_item` (dict): The listing dict for the thrift item, used to pull `title`, `price`, and `platform` for the caption.

**What it returns:**
A `str` of 2–4 sentences written as a casual social media caption. Example tone: _"Found this faded band tee on Depop for $22 and it's living in my closet now. Styled it with wide-leg cords and chunky boots for full vintage energy. Thrift always wins. 🖤"_

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, return the string `"[fit card unavailable — outfit suggestion was empty]"` without calling the LLM. If the LLM raises an exception, return `"[fit card unavailable — LLM error]"`. The planning loop treats either fallback as a valid final string and includes it in the session output.

---

### Additional Tools (if any)

None for the base implementation. (Stretch: `filter_by_style(wardrobe, style_tags)` — narrows the wardrobe down to items whose `style_tags` overlap with the new item before passing to `suggest_outfit`, to avoid confusing the LLM with mismatched pieces.)

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop is a single function `run_agent(user_query, wardrobe)` that executes the three tools in a fixed sequence, using a `session` dict to carry state between steps. Here is the exact conditional logic:

1. **Parse the query.** Extract `description`, `size`, and `max_price` from `user_query` using a simple Groq LLM call with a structured extraction prompt. The prompt asks for a JSON object with keys `description` (str), `size` (str or null), and `max_price` (float or null). Store in `session["parsed"]`.

2. **Call `search_listings`.** Pass `session["parsed"]["description"]`, `session["parsed"]["size"]`, `session["parsed"]["max_price"]`. Store result in `session["results"]`.
   - If `session["results"]` is an empty list → set `session["error"]` to the no-results message (see Tool 1 error handling), set `session["done"] = True`, and return `session["error"]` immediately. **Do not call Tools 2 or 3.**
   - If non-empty → set `session["selected_item"] = session["results"][0]` (the highest-scored match) and continue.

3. **Call `suggest_outfit`.** Pass `session["selected_item"]` and `wardrobe`. Store result in `session["outfit_suggestion"]`.
   - If result is empty or the LLM errored → set `session["outfit_suggestion"]` to the fallback string (see Tool 2 error handling). Continue to Tool 3 regardless — the fallback is still a valid string.

4. **Call `create_fit_card`.** Pass `session["outfit_suggestion"]` and `session["selected_item"]`. Store result in `session["fit_card"]`.

5. **Assemble and return output.** Build a final response string:
   ```
   🛍️  {selected_item["title"]} — ${selected_item["price"]} on {selected_item["platform"]}
   Size: {selected_item["size"]}  |  Condition: {selected_item["condition"]}

   HOW TO WEAR IT:
   {outfit_suggestion}

   FIT CARD:
   {fit_card}
   ```
   Set `session["done"] = True` and return the formatted string.

The loop does not iterate — it runs each tool exactly once in order. It knows it is done when `session["done"]` is `True`.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict created at the start of `run_agent`. It is local to one function call (no persistence between user queries). Keys written and read:

| Key | Type | Written by | Read by |
|-----|------|-----------|---------|
| `session["parsed"]` | dict with `description`, `size`, `max_price` | planning loop (query parser) | `search_listings` call |
| `session["results"]` | `list[dict]` (listing dicts) | planning loop after Tool 1 | emptiness check, selecting `selected_item` |
| `session["selected_item"]` | dict (one listing) | planning loop (`results[0]`) | `suggest_outfit`, `create_fit_card`, final output |
| `session["outfit_suggestion"]` | str | planning loop after Tool 2 | `create_fit_card`, final output |
| `session["fit_card"]` | str | planning loop after Tool 3 | final output |
| `session["error"]` | str | planning loop on empty results | returned immediately as final output |
| `session["done"]` | bool | planning loop | nothing (sentinel for caller) |

`wardrobe` is passed directly as a function parameter into `run_agent` and forwarded to `suggest_outfit` — it is not stored in `session`.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query (empty list returned) | Return `"No listings found for '{description}' in size {size} under ${max_price}. Try broader keywords, a different size, or a higher budget."` immediately. Skip Tools 2 and 3. |
| suggest_outfit | Wardrobe `items` list is empty | LLM is still called, but prompt asks for general styling advice (not specific wardrobe pairings). Returns a styling paragraph rather than named outfit. |
| suggest_outfit | LLM raises an exception or returns `""` | Set `outfit_suggestion` to `"Couldn't generate outfit suggestions right now. The item still looks great — try pairing it with basics in similar colors."` and continue to Tool 3. |
| create_fit_card | `outfit` argument is empty or whitespace-only | Return `"[fit card unavailable — outfit suggestion was empty]"` without calling the LLM. |
| create_fit_card | LLM raises an exception | Return `"[fit card unavailable — LLM error]"`. Include it in the final output as-is. |

---

## Architecture

```
User query (str) + wardrobe (dict)
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                      run_agent()                            │
│                    Planning Loop                            │
│                                                             │
│  Step 0: Parse query via LLM                               │
│    → session["parsed"] = {description, size, max_price}    │
│        │                                                    │
│        ▼                                                    │
│  Step 1: search_listings(description, size, max_price)     │
│    → session["results"] = [listing, ...]                   │
│        │                                                    │
│        ├── results == [] ──► session["error"] = "No        │
│        │                     listings found..."            │
│        │                     session["done"] = True        │
│        │                     return error msg  ────────────┼──► User sees error
│        │                                                    │
│        │ results non-empty                                  │
│        ▼                                                    │
│    session["selected_item"] = results[0]                   │
│        │                                                    │
│        ▼                                                    │
│  Step 2: suggest_outfit(selected_item, wardrobe)           │
│    wardrobe["items"] == [] ?                               │
│      └─ yes: prompt asks for general styling advice        │
│      └─ no:  prompt asks for specific wardrobe pairings    │
│    → session["outfit_suggestion"] = str                    │
│        │                                                    │
│        ├── LLM error / empty ──► fallback string set       │
│        │                         (continue to Step 3)      │
│        │                                                    │
│        ▼                                                    │
│  Step 3: create_fit_card(outfit_suggestion, selected_item) │
│    outfit empty? ──► return "[fit card unavailable...]"    │
│    LLM error?    ──► return "[fit card unavailable...]"    │
│    → session["fit_card"] = str                             │
│        │                                                    │
│        ▼                                                    │
│  Assemble final output string                              │
│  session["done"] = True                                    │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
User sees:
  🛍️  {title} — ${price} on {platform}
  Size: {size}  |  Condition: {condition}

  HOW TO WEAR IT:
  {outfit_suggestion}

  FIT CARD:
  {fit_card}
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

**Tool 1 (`search_listings`):** I'll paste the Tool 1 spec from this file (input parameters, return value, failure mode) into Claude and ask it to implement `search_listings()` using `load_listings()` from `utils/data_loader.py`. The scoring logic should tokenize `description` by whitespace, then count token matches in `title + description + style_tags + colors` (case-insensitive). I'll verify the output by checking: (a) filtering by `max_price` drops listings above the ceiling, (b) filtering by `size` uses case-insensitive substring match, (c) listings with a score of 0 are excluded, (d) results are sorted descending by score. I'll test with 3 queries: `("vintage graphic tee", "M", 30.0)`, `("chunky platform shoes", None, None)`, and `("cottagecore dress", "S", 20.0)`.

**Tool 2 (`suggest_outfit`):** I'll paste the Tool 2 spec into Claude along with the wardrobe schema (the `schema` field from `data/wardrobe_schema.json`). I'll ask it to implement `suggest_outfit()` with two prompt branches: one for an empty wardrobe and one for a populated wardrobe. I'll verify: (a) when `wardrobe["items"]` is empty, the LLM prompt does NOT reference any specific items; (b) when items exist, the prompt lists each wardrobe item by `name`, `category`, `colors`, and `style_tags`; (c) the function returns a non-empty string in both cases; (d) LLM exceptions are caught and return the fallback string.

**Tool 3 (`create_fit_card`):** I'll paste the Tool 3 spec into Claude, including the caption style guidelines (casual, mentions item name/price/platform once, captures outfit vibe). I'll ask it to implement `create_fit_card()` with temperature 0.9. I'll verify: (a) passing `outfit=""` returns `"[fit card unavailable — outfit suggestion was empty]"` without an LLM call; (b) the returned caption is 2–4 sentences; (c) it contains the item's `title`, `price`, and `platform`; (d) running it twice on the same input produces different text (temperature test).

**Milestone 4 — Planning loop and state management:**

I'll paste the full `## Planning Loop`, `## State Management`, and `## Architecture` sections from this file into Claude, along with the signatures of all three tools. I'll ask it to implement `run_agent(user_query: str, wardrobe: dict) -> str` in a new file `agent.py`. I'll verify: (a) the session dict contains all 7 keys after a successful run; (b) passing a query with no matching listings returns the error message and does NOT call `suggest_outfit` or `create_fit_card`; (c) passing a valid query produces all three sections (listing header, HOW TO WEAR IT, FIT CARD) in the output string; (d) the function doesn't mutate the `wardrobe` argument.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:** The planning loop calls the Groq LLM to parse the query. The LLM returns:
```json
{"description": "vintage graphic tee", "size": null, "max_price": 30.0}
```
These are stored in `session["parsed"]`. Size is null because the user didn't mention one.

**Step 2:** The planning loop calls `search_listings(description="vintage graphic tee", size=None, max_price=30.0)`.

The function loads all 40 listings, drops any with `price > 30.0`, then scores the rest by counting how many tokens from `"vintage graphic tee"` appear in each listing's title + description + style_tags + colors. Listings with score 0 are dropped. The result is a list of ~5–8 matching listings sorted by score. Example top result:

```json
{
  "id": "lst_007",
  "title": "Vintage Graphic Band Tee — Faded Black",
  "category": "tops",
  "style_tags": ["vintage", "grunge", "graphic tee", "band tee"],
  "size": "M/L",
  "condition": "good",
  "price": 22.0,
  "colors": ["black", "grey"],
  "brand": null,
  "platform": "depop"
}
```

`session["results"]` = that list. List is non-empty, so `session["selected_item"] = results[0]`.

**Step 3:** The planning loop calls `suggest_outfit(new_item=selected_item, wardrobe=example_wardrobe)`.

The wardrobe has 10 items (not empty), so the LLM prompt includes the full item list. The LLM returns something like:

> "Outfit 1: Pair this band tee with the baggy straight-leg dark wash jeans (w_001) and chunky white sneakers (w_007) for a classic 90s streetwear look — tuck the tee slightly at the front. Outfit 2: Try it with the wide-leg khaki trousers (w_002), a thin brown leather belt, and white low-top sneakers (w_007) for a more relaxed vintage vibe."

`session["outfit_suggestion"]` = that string.

**Step 4:** The planning loop calls `create_fit_card(outfit=outfit_suggestion, new_item=selected_item)`.

The LLM (temperature 0.9) returns:

> "Snagged this faded band tee on Depop for $22 and honestly it might be the best $22 I've ever spent. Threw it on with my baggy dark wash jeans and chunky sneakers and felt like I walked out of a 1994 music video. Thrift finds like this are why I can't stop scrolling. 🖤"

`session["fit_card"]` = that string.

**Final output to user:**
```
🛍️  Vintage Graphic Band Tee — Faded Black — $22.0 on depop
Size: M/L  |  Condition: good

HOW TO WEAR IT:
Outfit 1: Pair this band tee with the baggy straight-leg dark wash jeans and chunky
white sneakers for a classic 90s streetwear look — tuck the tee slightly at the front.
Outfit 2: Try it with the wide-leg khaki trousers, a thin brown leather belt, and
white low-top sneakers for a more relaxed vintage vibe.

FIT CARD:
Snagged this faded band tee on Depop for $22 and honestly it might be the best $22
I've ever spent. Threw it on with my baggy dark wash jeans and chunky sneakers and
felt like I walked out of a 1994 music video. Thrift finds like this are why I can't
stop scrolling. 🖤
```
