# HR Assist

HR Assist answers questions about Northstar Digital Services' HR policies, grounded in a fixed corpus of policy documents and summary decks.

## Corpus

**Corpus**:
The set of Source Documents HR Assist answers from. Only documents listed in the Corpus Manifest belong to it.
_Avoid_: Knowledge base, dataset

**Corpus Manifest**:
The authoritative list of the Corpus's Source Documents, recording each one's Document ID, Document Version, kind, Document Status and Effective Period.

**Source Document**:
Any file in the Corpus, identified by its Document ID and Document Version.
_Avoid_: File, doc, policy (when the item is a deck)

**Document ID**:
The stable identifier printed on a Source Document, e.g. `NDS-HR-LAS-002`. It stays the same across versions.

**Document Version**:
A specific revision of a Source Document, e.g. `v1.2`. A Document ID plus a Document Version identifies exactly one Source Document.

**Policy Document**:
An authoritative Source Document that sets rules, such as the Employee Handbook or the Leave and Absence Standard.
_Avoid_: Policy PDF

**Summary Deck**:
A non-authoritative Source Document that summarises Policy Documents. Where a Summary Deck and a Policy Document differ, the Policy Document prevails.
_Avoid_: Slides, presentation, training

**Test Fixture**:
A Source Document created to test the assistant's robustness. It has no authority, and its content must never be presented as policy.

**Document Status**:
Whether a Source Document is `current` or `superseded`. A superseded document never takes precedence over a current one, but it still answers questions about the period when it was in force.
_Avoid_: Archived (as a status), active, old

**Effective Period**:
The date range during which a Document Version was in force. A current document's Effective Period has no end date.

**Precedence Order**:
The ranking that decides which Source Document wins when two disagree. It is defined by the Employee Handbook, not by HR Assist.

## Asking and answering

**Employee**:
The person asking HR Assist a question. They are anonymous, and HR Assist holds no records about them or their colleagues.
_Avoid_: User, customer

**As-Of Date**:
The date on which a question is asked. It defaults to today.

**Applicable Date**:
The date a question is about, such as the day a leave request was submitted or the day of a bereavement. It determines which Document Version applies, and it may differ from the As-Of Date.

**Response Type**:
The kind of reply HR Assist gives: Answer, Clarification, Abstention or Refusal.

**Answer**:
A reply grounded in retrieved evidence, with Citations.

**Clarification**:
A reply asking the Employee for missing details, because the question has several reasonable readings that lead to different answers.

**Abstention**:
A reply stating that the corpus does not contain the evidence needed to answer.
_Avoid_: Refusal, "I don't know"

**Refusal**:
A reply declining to answer because doing so would breach privacy, confidentiality or safety rules, even if the information may exist.
_Avoid_: Abstention

**Citation**:
A reference from an Answer to its supporting evidence: document title, Document ID, Document Version, section, and page or slide.
_Avoid_: Source, reference
