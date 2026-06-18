# Notion_To_Anki

A **free, open-source Anki add-on** that syncs a Notion page (and its subpages) into Anki
flashcards — no AI, no paywall, no third-party server.

It converts every top-level **toggle list** on a Notion page into a flashcard:

- **Front** = the toggle heading
- **Back** = the content inside the toggle
- **Extra (3rd field)** = any *nested* toggles, each rendered inside a `<details>` block
- **Deck** = the Notion page title; **subpages** become **subdecks**

Rich text formatting (bold, italics, colors, code), images, and LaTeX/MathJax are
preserved and rendered without external dependencies.

> Goal: match the full *paid* feature set of [notion2anki](https://www.notion2anki.com/en)
> (unlimited pages, unlimited notes, fast auto-sync) but free for everyone.

## Status

🚧 Early development. See [`docs/PLAN.md`](docs/PLAN.md) for the implementation plan.

## License

AGPL-3.0 — keeping this free and open for everyone.
