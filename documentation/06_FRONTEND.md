# 06. Frontend

The UI is a single-page **Angular 22** app in [frontend/](../frontend/), styled with **Tailwind CSS 4** and tested with **Vitest**. It uses standalone components and **signals** for state, with no router and no NgRx.

```sh
cd frontend
npm install
npm start          # http://localhost:4200, calls the API at http://localhost:8000
npm test           # Vitest (watch mode; add -- --watch=false for one run)
npm run lint
npm run build      # production bundle in dist/frontend/browser
```

From the repo root, `npm run dev` runs [scripts/dev.sh](../scripts/dev.sh), which starts the backend and the frontend together and stops both on Ctrl-C.

## Components

```text
App (app.ts)
├── Sidebar          new chat, the current conversation; a drawer below the lg breakpoint
├── Logo
└── Conversation     the message list, example questions on an empty chat
    ├── Reply        one assistant reply: message, markers, citation cards
    ├── Composer     the input box and send button
    ├── ConnectionStatus   API and Qdrant indicator, polls /api/health
    └── ThemeToggle  light, dark or system
```

| Folder | Component | What it does |
| --- | --- | --- |
| `app.ts` | `App` | Layout. Holds `navOpen`; Escape closes the drawer |
| `sidebar/` | `Sidebar` | Starts a new chat (`ChatStore.reset()`) and lists the current conversation |
| `conversation/` | `Conversation` | Renders turns, the pending state, the error with a retry button, and the example questions |
| `composer/` | `Composer` | Text input; sends through `ChatStore.ask()` |
| `reply/` | `Reply` | Splits the message into text and markers, styles each Response Type, renders citation cards |
| `reply/snippet.ts` | `parseSnippet` | A small Markdown reader for citation snippets |
| `connection-status/` | `ConnectionStatus` | Polls health every 30 seconds and shows Connected, Qdrant unreachable, API unreachable or Checking |
| `theme-toggle/` | `ThemeToggle` | Light, dark and system themes |
| `logo/` | `Logo` | The mark |

## State: `ChatStore`

[chat-store.ts](../frontend/src/app/chat-store.ts) is a root-provided service with four signals:

| Signal | Holds |
| --- | --- |
| `turns` | The conversation: Employee questions and assistant `ChatReply` objects |
| `pending` | A request is in flight |
| `error` | The last error message, or `null` |
| `asOfDate` | Today's local date as `YYYY-MM-DD`, sent with every request |

| Method | Behaviour |
| --- | --- |
| `ask(question)` | Ignores empty input and input while pending. Appends the question, then sends the **last 6 turns** as `messages` (assistant turns as their `message` text) with `as_of_date` |
| `retry()` | Resends the exact request that failed, so the Employee doesn't retype it |
| `reset()` | Cancels any request in flight, clears the conversation and the error. Keeps the As-Of Date |

On an error, the store shows the API's `error.message` when there is one (for example the rate-limit text), otherwise "HR Assist could not be reached."

## How a reply is shown

| Response Type | Look | Label |
| --- | --- | --- |
| Answer | Plain text beside the assistant's mark | none |
| Clarification | Soft accent panel, reads as a question waiting for a reply. Focus moves back to the input | "A question for you" |
| Abstention | Muted panel, plus a People Operations next step | "Not covered by the policies" |
| Refusal | Neutral notice, deliberately not error red | "HR Assist can't help with this" |

Inline markers `[n]` become links to citation card `n`. The API has already renumbered them to match the order of `citations` ([04](04_ANSWERING_ENGINE.md)).

### Citation cards

Each card shows the document title, ID and version, the section, and the page range or slide. A Citation from a superseded source is marked **Superseded**. A card expands to show its snippet: the whole chunk body, rendered by `parseSnippet`, which understands only what the parsers produce:

- headings (`#` to `######`)
- `**bold**`
- pipe tables, with or without a header rule
- bulleted (`-`, `*`, `•`) and numbered lists, even with blank lines between items
- `<br>` inside a table cell, read as a space (where the PDF wrapped a line)
- a lone `**` left by a cut bold run is dropped

## Example questions

An empty chat offers example questions in three groups, each showing one behaviour:

| Group | Shows |
| --- | --- |
| Answers with citations | Grounded, cited answers |
| Asks when unclear | Clarifications |
| Knows its limits | Abstentions and Refusals |

The As-Of Date picker and the "version-aware" examples were removed when retrieval switched to current documents only ([ADR 0007](../docs/adr/0007-search-only-current-documents.md)).

## API base URL

| Build | `environment.apiBaseUrl` | Requests go to |
| --- | --- | --- |
| Development (`npm start`) | `http://localhost:8000` | The local backend, cross-origin, allowed by CORS |
| Production (`npm run build`) | `''` | The same origin. Firebase Hosting rewrites `/api/**` to Cloud Run |

The URL is injected through the `API_BASE_URL` token ([api-base-url.ts](../frontend/src/app/api-base-url.ts)), so tests can replace it. HTTP uses `provideHttpClient(withFetch())`.

## Privacy notice

On first load the UI tells visitors that questions are logged to improve the demo, so they shouldn't enter personal information ([13](13_DEPLOYMENT_AND_CI.md)).

## Tests

| Spec | Covers |
| --- | --- |
| `app.spec.ts` | The app shell and the connection indicator: connected, degraded (Qdrant down), offline |
| `chat.spec.ts` | The chat page end to end with a mocked backend: the privacy notice, sending with the As-Of Date, citation cards and markers, loading, error and retry, example questions, new conversation (including dropping a pending reply), history limits, the Superseded label, and how each Response Type is shown |
| `reply/snippet.spec.ts` | The snippet reader: headings, bold, tables (wrapped cells, cut rows, no header), lists with blank lines, a bold marker left open |

CI runs `npm ci`, `npm run lint`, `npx ng test --watch=false` and `npm run build` on every PR ([10](10_TESTING.md)).
