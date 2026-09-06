# AnkiWeb listing copy

Paste the block below into the **Description** field at
ankiweb.net/shared/upload?id=1287017969

Branch settings: **Supports 23.10 to 25.09** (no `-` prefix on the max, or the
add-on stops being offered to newer Anki releases).

---

<b>NotionSync for Anki</b> — turn your Notion notes into Anki flashcards. Free, no paid tiers.<br><br>

<b>What it does</b><br>
📝 Notion <b>toggle lists</b> → Basic cards. The toggle title is the question, everything inside is the answer.<br>
📊 Notion <b>tables</b> → one card per row.<br>
✂️ <b>Cloze deletions</b> using <code>{{c1::...}}</code> syntax.<br>
🖼️ <b>Pictures are downloaded into your collection</b>, so they work offline and keep working. Notion's own image links expire after about an hour — these don't.<br>
🔊 Audio blocks become playable card audio.<br>
📁 <b>Nested Notion pages → nested Anki decks</b>, mirroring your structure.<br>
🎨 Keeps bold, italic, colours, highlights, lists, code blocks, callouts, quotes and LaTeX equations.<br><br>

<b>Built for big collections</b><br>
⏹️ <b>Stop button</b> — a large Notion workspace can take several minutes, so you can stop any time. Cards already imported are kept, and running it again picks up where it left off.<br>
🔁 <b>Re-syncing updates your existing cards in place.</b> It never creates duplicates and never touches your review history, so your scheduling is safe.<br>
⚡ Images are cached, so repeat syncs are much faster than the first.<br>
🕒 Optional auto-sync on a timer.<br><br>

<b>Setup</b><br>
1. Create a Notion integration at <a href="https://www.notion.so/profile/integrations">notion.so/profile/integrations</a> and copy the token.<br>
2. In Anki: <b>Tools → NotionSync for Anki</b>, paste the token.<br>
3. Add your Notion page link or ID, then click Sync Now.<br><br>
⚠️ <b>Important:</b> in Notion, open each page you want to sync, click the <b>•••</b> menu → <b>Connections</b>, and add your integration. Notion hides pages from the add-on until you do this — it's the most common reason a sync finds nothing.<br><br>

<b>Good to know</b><br>
• Only toggles, cloze text and tables become cards. A picture sitting loose on a page has no card to attach to — put it inside a toggle to bring it across. The sync tells you afterwards if it found any.<br>
• Cards are matched to their Notion block, so if you move pages out of the page you configured, those cards stop updating.<br>
• Requires <b>Anki 23.10 or newer</b>.<br><br>

🎓 Originally built to help a friend study, shared publicly so anyone can benefit.<br>
🐛 Issues and source: <a href="https://github.com/felixthe-cat/Notion_To_Anki">github.com/felixthe-cat/Notion_To_Anki</a>
