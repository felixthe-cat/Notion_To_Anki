# NotionSync for Anki

**A free, open-source Anki add-on that syncs your Notion notes directly into Anki flashcards.**
No AI, no paywall, no third-party server.

📦 **[Get it on AnkiWeb → Add-on #1287017969](https://ankiweb.net/shared/info/1287017969)**

---

## What it does

- 📄 Converts Notion **toggle lists** → Basic flashcards
- 📊 Converts Notion **tables** → one card per row
- 🗂️ Mirrors **nested pages** → nested Anki decks
- 🧩 Supports **cloze deletion** with `{{c1::...}}` syntax

---

## Setup

1. Create a Notion integration at [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Add your token in Anki under **Tools → NotionSync for Anki**
3. Paste your Notion page IDs and sync

---

## How cards are built

| Notion element | Anki output |
|---|---|
| Toggle heading | Front field |
| Toggle body | Back field |
| Nested toggles | Extra field (inside `<details>` blocks) |
| Table row | One Basic card per row |
| Subpage / child database | Subdeck |

Rich text formatting (bold, italics, colours, code), images, and LaTeX/MathJax are preserved without any external dependencies.

---

## 💸 Completely free

No subscriptions, no premium features, no paywalls. 

---

## License

AGPL-3.0 — keeping this free and open for everyone.

---

🎓 Originally built to help a friend study — shared publicly so anyone can benefit.
