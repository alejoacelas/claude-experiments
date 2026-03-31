# A Linear Walkthrough of OpenFactVerification (Loki)

*A walkthrough of [Libr-AI/OpenFactVerification](https://github.com/Libr-AI/OpenFactVerification), an open-source automated fact-checking system. This follows the [linear walkthrough](https://simonwillison.net/guides/agentic-engineering-patterns/linear-walkthroughs/) pattern described by Simon Willison.*

---

OpenFactVerification — branded **Loki** — is a Python pipeline that takes a piece of text, breaks it into individual claims, figures out which ones are worth checking, searches the web for evidence, and then uses an LLM to decide whether each claim is supported, refuted, or lacks evidence. The whole thing is about 20 files of Python glued together with OpenAI/Claude/local-LLM clients, the Serper search API, a cross-encoder for passage ranking, and a Flask web UI.

Let's walk through it end to end.

## 1. Entry points: how you run the thing

There are three ways to use Loki:

### The CLI (`factcheck/__main__.py`)

The simplest path in. It parses command-line arguments and wires everything together:

```python
parser.add_argument("--model", type=str, default="gpt-4o")
parser.add_argument("--client", type=str, default=None, choices=CLIENTS.keys())
parser.add_argument("--prompt", type=str, default="chatgpt_prompt")
parser.add_argument("--retriever", type=str, default="serper")
parser.add_argument("--modal", type=str, default="text")
parser.add_argument("--input", type=str, default="demo_data/text.txt")
parser.add_argument("--api_config", type=str, default="factcheck/config/api_config.yaml")
```

The `--modal` flag is what makes it multimodal — it accepts `"string"`, `"text"` (file), `"speech"`, `"image"`, or `"video"`. Before anything enters the pipeline, `modal_normalization()` in `factcheck/utils/multimodal.py` converts the input to plain text. Speech goes through OpenAI Whisper, images through GPT-4 Vision, video through frame extraction with OpenCV then GPT-4 Vision.

The actual `check()` function is short:

```python
def check(args):
    api_config = load_yaml(args.api_config)
    factcheck = FactCheck(
        default_model=args.model, client=args.client,
        api_config=api_config, prompt=args.prompt, retriever=args.retriever
    )
    content = modal_normalization(args.modal, args.input)
    res = factcheck.check_text(content)
    print(json.dumps(res, indent=4))
```

### The Python library

You can also use it as an import:

```python
from factcheck import FactCheck
fc = FactCheck(default_model="gpt-4o", retriever="serper")
result = fc.check_text("MBZUAI is the first AI university in the world.")
```

### The web app (`webapp.py`)

A Flask app running on port 2024. `POST /` accepts text, runs the pipeline, saves results to a JSON file, and renders them in a Jinja2 template. It registers a few custom Jinja2 filters — `count_occurrences` and `filter_evidences` — to help the template display the results grouped by relationship type (SUPPORTS, REFUTES, IRRELEVANT).

---

## 2. The FactCheck orchestrator (`factcheck/__init__.py`)

This is the brain. The `FactCheck` class wires together five sub-modules, each backed by its own LLM client instance:

```python
self.decomposer = Decompose(llm_client=self.decompose_model, prompt=self.prompt)
self.checkworthy = Checkworthy(llm_client=self.checkworthy_model, prompt=self.prompt)
self.query_generator = QueryGenerator(llm_client=self.query_generator_model, prompt=self.prompt)
self.evidence_crawler = retriever_mapper(retriever_name=retriever)(
    llm_client=self.evidence_retrieval_model, api_config=self.api_config
)
self.claimverify = ClaimVerify(llm_client=self.claim_verify_model, prompt=self.prompt)
```

A nice design choice: each pipeline stage can use a *different* model. You could run claim decomposition with GPT-4o but verification with GPT-3.5-turbo to save cost. The constructor accepts `decompose_model`, `checkworthy_model`, etc., falling back to `default_model` if not specified.

The `check_text()` method is the pipeline itself. Let's trace its execution:

### Step 1: Decompose

```python
claims = self.decomposer.getclaims(doc=raw_text, num_retries=self.num_seed_retries)
```

### Steps 2-3: Parallel execution

Here's where it gets interesting — three independent operations run concurrently via `ThreadPoolExecutor`:

```python
with concurrent.futures.ThreadPoolExecutor() as executor:
    future_claim2doc = executor.submit(
        self.decomposer.restore_claims, doc=raw_text, claims=claims, num_retries=self.num_seed_retries
    )
    future_checkworthy_claims = executor.submit(
        self.checkworthy.identify_checkworthiness, claims, num_retries=self.num_seed_retries
    )
    future_claim_queries_dict = executor.submit(
        self.query_generator.generate_query, claims=claims
    )
```

Three things happen at once:
- **Restore claims** — map each extracted claim back to its span in the original document
- **Checkworthiness filtering** — decide which claims are verifiable facts vs. opinions
- **Query generation** — produce search queries for every claim

After all three complete, the results are intersected: only claims that passed the checkworthiness filter get their queries forwarded to evidence retrieval.

```python
checkworthy_claims_S = set(checkworthy_claims)
claim_queries_dict = {k: v for k, v in claim_queries_dict.items() if k in checkworthy_claims_S}
```

### Step 4: Evidence retrieval

```python
claim_evidences_dict = self.evidence_crawler.retrieve_evidence(claim_queries_dict=claim_queries_dict)
```

### Step 5: Verification

```python
claim_verifications_dict = self.claimverify.verify_claims(claim_evidences_dict=claim_evidences_dict)
```

### Finalization

The `_merge_claim_details()` method assembles everything into `ClaimDetail` objects. For each claim, it computes a factuality score:

```python
labels = list(map(lambda x: x.relationship, evidences))
if labels.count("SUPPORTS") + labels.count("REFUTES") == 0:
    factuality = "No evidence found."
else:
    factuality = labels.count("SUPPORTS") / (labels.count("REFUTES") + labels.count("SUPPORTS"))
```

Factuality is the ratio of supporting evidence to all decisive evidence. A claim with 3 SUPPORTS and 1 REFUTES gets `0.75`. Claims that are entirely IRRELEVANT get the string `"No evidence found."` instead.

Finally, `_finalize_factcheck()` computes an overall summary — total claims, how many were checkworthy, how many supported/refuted — and wraps everything in a `FactCheckOutput` dataclass.

---

## 3. Stage 1: Claim Decomposition (`factcheck/core/Decompose.py`)

The `Decompose` class has two jobs: break text into atomic claims, and map those claims back to the original text.

`getclaims()` sends the document to the LLM with a prompt asking it to return a JSON list of concise, self-contained claims (under 15 words each, no vague pronouns). It retries up to 3 times with different random seeds. If the LLM keeps returning unparseable JSON, it falls back to NLTK's `sent_tokenize`:

```python
def _nltk_doc2sent(self, doc: str) -> list[str]:
    """Tokenize a document into sentences using NLTK."""
    sents = sent_tokenize(doc)
    sents = [sent for sent in sents if len(sent) > 3]
    return sents
```

`restore_claims()` is subtler. It asks the LLM to find the exact span in the original document where each claim originated, returning start/end character indices. This is what lets the web UI highlight the relevant portion of the source text for each claim.

---

## 4. Stage 2: Checkworthiness (`factcheck/core/CheckWorthy.py`)

The `Checkworthy` class receives a list of claims and asks the LLM to classify each as "Yes" (verifiable fact) or "No" (opinion, vague, or unverifiable).

The prompt guidelines are specific:
- Verifiable statements about people, places, dates, statistics = Yes
- Subjective opinions = No
- Statements with unresolved pronouns ("He is tall") = No

If the LLM response is unparseable after retries, the fallback is conservative: treat all claims as checkworthy and send them through.

---

## 5. Stage 3: Query Generation (`factcheck/core/QueryGenerator.py`)

For each checkworthy claim, the `QueryGenerator` produces up to 5 search queries. The claim itself is always included as the first query, and the LLM generates additional verification questions.

For example, given the claim "The Stanford Prison Experiment was conducted in Encina Hall," it might generate:
- "The Stanford Prison Experiment was conducted in Encina Hall." (the claim itself)
- "Where was the Stanford Prison Experiment conducted?"

The `max_query_per_claim` setting caps this at 5 queries.

---

## 6. Stage 4: Evidence Retrieval (`factcheck/core/Retriever/`)

This is the most complex stage. The retriever system uses a base class with two implementations.

### BaseRetriever (`base.py`)

The base class loads two heavyweight dependencies on init:
- **spaCy** (`en_core_web_sm`) — for sentence tokenization when chunking web pages
- **CrossEncoder** (`cross-encoder/ms-marco-MiniLM-L-6-v2`) — a neural passage ranker that scores how relevant a text passage is to a query

The retrieval pipeline for each claim:

1. **Get URLs** — search the web for each query
2. **Crawl and parse** — async-fetch each URL, strip HTML to visible text using BeautifulSoup
3. **Chunk** — split the page text into overlapping passages using a sliding window (10 sentences per passage, sliding by 8)
4. **Rank** — score every passage against the query using the CrossEncoder
5. **Deduplicate** — take the top non-overlapping passages to maximize information diversity
6. **Aggregate** — collect the best passage from each query into a final evidence list (max 5 total)

The chunking logic is elegant in its simplicity:

```python
for idx in range(0, len(sents), self.sliding_distance):
    passages.append(
        (
            " ".join(sents[idx : idx + self.sentences_per_passage]),
            idx,
            idx + self.sentences_per_passage - 1,
        )
    )
```

Each passage is a tuple of (text, start_sentence_index, end_sentence_index). The overlap (10 sentence window, 8 sentence slide = 2 sentence overlap) ensures claims that span sentence boundaries aren't lost.

The non-overlap deduplication in `_sorted_passage_by_relevant_score` checks whether a candidate passage's sentence range overlaps with any already-selected passage:

```python
for item in relevant_items:
    if passage_item[1] >= item[1] and passage_item[1] <= item[2]:
        overlap = True
        break
    if passage_item[2] >= item[1] and passage_item[2] <= item[2]:
        overlap = True
        break
```

### SerperEvidenceRetriever (`serper_retriever.py`)

The primary retriever implementation. It calls the [Serper API](https://serper.dev/) (a Google Search API wrapper) in batches of up to 100 queries per request.

A clever optimization: when Google returns an Answer Box (those direct-answer cards at the top of search results), the retriever uses that directly — one high-confidence evidence item rather than crawling multiple pages.

For organic results, it extends snippets by crawling the full page and extracting 500 characters of context after the snippet match. This gives the verifier more material to work with than the snippet alone.

### GoogleEvidenceRetriever (`google_retriever.py`)

An alternative that scrapes Google Search results directly (no API key needed), parsing the HTML for `<a><h3>` patterns to extract result URLs, then crawling those pages.

---

## 7. Stage 5: Claim Verification (`factcheck/core/ClaimVerify.py`)

The final stage. For each (claim, evidence) pair, the `ClaimVerify` class asks the LLM to determine the relationship.

The key design decision is the use of `multi_call()` — an async batch method on the LLM client that sends all verification requests in parallel with rate limiting. This is important because a single claim might have 5 evidence items, and there might be 10 claims, so that's 50 LLM calls. Doing them sequentially would be painfully slow.

Each response must be valid JSON with two fields:
- `reasoning` — the LLM's explanation
- `relationship` — one of `SUPPORTS`, `REFUTES`, or `IRRELEVANT`

If parsing fails after 3 retries, the claim gets a default IRRELEVANT verdict with a system warning — a safe fallback that avoids false positives/negatives.

---

## 8. The LLM Client Abstraction (`factcheck/utils/llmclient/`)

The LLM layer is cleanly abstracted. `BaseClient` defines the interface with:

- `call()` — single synchronous call with retries
- `multi_call()` — async batch calls with rate limiting (default: 200 requests/minute)
- Token usage tracking via a `TokenUsage` dataclass

Three implementations:

| Client | Class | API | Notes |
|--------|-------|-----|-------|
| OpenAI | `GPTClient` | OpenAI SDK | Forces JSON response format, uses seed=42 for reproducibility |
| Claude | `ClaudeClient` | Anthropic SDK | No system role (user messages only), max 2048 tokens |
| Local | `LocalOpenAIClient` | OpenAI-compatible endpoint | For self-hosted models (Vicuna, LLaMA, etc.) |

Model auto-detection in `model2client()` maps model name prefixes to clients: `"gpt*"` → GPTClient, `"claude*"` → ClaudeClient, `"vicuna*"` → LocalOpenAIClient.

---

## 9. The Prompt System (`factcheck/utils/prompt/`)

Each pipeline stage has its own prompt template. The `BasePrompt` dataclass defines the interface:

```
decompose_prompt   — "Break this text into atomic claims..."
restore_prompt     — "Map each claim back to the original text..."
checkworthy_prompt — "Is this claim verifiable? Yes/No..."
qgen_prompt        — "Generate search queries for this claim..."
verify_prompt      — "Does this evidence support or refute this claim?"
```

Implementations include `ChatGPTPrompt` (English), `ChatGPTPromptZH` (Chinese), `ClaudePrompt`, and `CustomizedPrompt` (loads from YAML/JSON files). Each prompt includes examples and explicit JSON output format specifications.

---

## 10. Data Structures (`factcheck/utils/data_class.py`)

The output hierarchy:

```
FactCheckOutput
├── raw_text: str
├── token_count: int
├── usage: PipelineUsage
│   ├── decomposer: TokenUsage
│   ├── checkworthy: TokenUsage
│   ├── query_generator: TokenUsage
│   ├── evidence_crawler: TokenUsage
│   └── claimverify: TokenUsage
├── claim_detail: list[ClaimDetail]
│   ├── id, claim, checkworthy, checkworthy_reason
│   ├── origin_text, start, end
│   ├── queries: list[str]
│   ├── evidences: list[Evidence]
│   │   ├── claim, text, url
│   │   ├── reasoning, relationship
│   └── factuality: float | str
└── summary: FCSummary
    ├── num_claims, num_checkworthy_claims
    ├── num_verified_claims, num_supported_claims
    ├── num_refuted_claims, num_controversial_claims
    └── factuality: float
```

Every dataclass has an `attribute_check()` method for validation. The `factuality` field on `ClaimDetail` is a union type in practice — it's a float between 0 and 1 for verified claims, or a string like `"Nothing to check."` or `"No evidence found."` for unverifiable ones.

---

## The Big Picture

Here's the complete data flow:

```
"MBZUAI is the first AI university, located in Abu Dhabi."
                    │
                    ▼
            ┌──────────────┐
            │  Decompose    │  LLM extracts atomic claims
            └──────┬───────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌────────┐  ┌───────────┐  ┌──────────┐
│Restore │  │Checkworthy│  │Query Gen │   Three tasks in parallel
│Claims  │  │  Filter   │  │          │
└───┬────┘  └─────┬─────┘  └────┬─────┘
    │             │              │
    └──────────────┼──────────────┘
                   │
                   ▼  (intersect: only checkworthy claims proceed)
            ┌──────────────┐
            │  Evidence     │  Serper API → crawl → chunk → rank
            │  Retrieval    │  (spaCy + CrossEncoder)
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │  Claim        │  LLM: SUPPORTS / REFUTES / IRRELEVANT
            │  Verification │  (parallel via multi_call)
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │  Finalize     │  Compute factuality scores
            │  Output       │  Build FactCheckOutput
            └──────────────┘
```

The architecture is modular in the right ways — you can swap LLMs, swap retrievers, swap prompts, or swap languages without touching the pipeline logic. The parallel execution in steps 2-3 and the batch async in step 5 keep things reasonably fast despite the many LLM calls involved.

The main bottleneck, unsurprisingly, is evidence retrieval: crawling web pages, parsing HTML, chunking text, and running a cross-encoder over hundreds of passages. Everything else is LLM calls that can be parallelized.
