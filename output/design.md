# Campus Customs Back Office: the dashboard's design

The dashboard is the back room of the Campus Customs storefront built in Homework 4. A manager who
walks from the shop floor (HW4) to the desk (HW5) should feel they are in the same building, so the
page reuses that site's visual system rather than inventing a second one. Everything on the page
arrives through the FastAPI back end (`http://localhost:8000`), which in turn reads and writes only
through the MCP server; the dashboard computes no shop facts of its own.

Code: `frontend/` (React 19, Vite 8, TypeScript, no UI library). Start with `npm run dev` on
port 5173.

## 1. The look, and why

**Borrowed from HW4, on purpose.** Yale Blue (`#00356b`) on white; EB Garamond for headlines,
ticket subjects, agent names, and amounts; Source Sans 3 for everything else, with small uppercase
letter-spaced labels ("THE BOARD", "NEEDS YOU", "SHOP DATE"); thin `#ddd` rules; square corners;
buttons as blue slabs with uppercase text; a 4 px Yale Blue stripe across the top of the window.
The page background is the storefront's light gray, so the white panels read as sheets on a desk.

**Colour is spent only on meaning.** Blue is the shop's own voice (brand, primary buttons, the
Boss). Green means done or paid. Amber means waiting on a human. Red means refused or wrong. Each
of the five agents owns one more hue, and that hue follows the agent everywhere it appears. Nothing
else on the page is coloured, so when something is, it is saying something.

**Serif numbers for money.** The checking balance, approval amounts, and ticket subjects are set in
the serif at a larger size, like figures in a ledger. It makes the few numbers that matter look
considered rather than dashboard-y.

## 2. The layout

A fixed top bar and three columns, read left to right in the order the work happens:

| Where | What | Why it is there |
|---|---|---|
| Top bar | Brand, the shop's date, the checking balance, the team's status light, "Approving as" (your name), Reset | The facts a manager glances at before anything else, and the one identity that goes on every approval. |
| Left column, "The board" (330 px) | The tickets as cards: type, subject, requester, what is asked (SKU × quantity, lease, invoice), status chip, priority, assignee. The selected card opens to show the ticket note, the Run button, and the resolution once there is one. | Pick a ticket. |
| Centre, "Live floor" (fluid, sticky, full height) | The ticket's header and counts, the team strip (who is on it, what each is doing now), the feed of everything the agents say and do, auto-scrolling. | Watch the team. |
| Right column (360 px) | "Needs you": the approval queue with Approve & pay / Reject. "Who did what": a per-agent summary of the selected ticket. "Drafts on the board": the customer messages, never sent. | Act when asked, then read the summary. |

Under 1240 px the right column slides beneath the other two; under 860 px everything stacks and
the floor becomes a tall card. Motion is turned off for people who ask the OS for reduced motion.

## 3. How the agents read differently

**One colour, one initial, everywhere.** Boss is Yale Blue (B), Inventory green (I), Accounting
gold (A), Facilities teal (F), Customer Service plum (C). You, the human, are charcoal (H) and the
shop itself is gray (S). The same round serif initial appears on the board as the assignee, in the
team strip, beside every line in the feed, and in the summary, so by the second ticket you no
longer read names.

**The team strip shows presence.** Five members sit above the feed. An agent that has not been
needed on this ticket is dimmed and says "not needed" (or "standing by" while a run is on). One
that took part is at full strength and says "took part". The one working right now is lifted two
pixels, wears a pulsing ring in its own colour, and says what it is doing in plain words:
"checking the lease", "asking Accounting", "writing on the ticket", "made the call". The strip is
how you see, without reading, that the right agent went to the right ticket and Facilities never
touched the hoodie discount.

**The feed speaks in three voices.**

- *Asks and reports.* When the Boss hands work to a colleague the line is a bordered card whose
  left edge is the colleague's colour and whose tag reads "asked Facilities" with the chain
  (Boss → Fac → Acct) beside it. The colleague's report comes back in a card tinted with the
  reporter's colour. Long ones fold at a few hundred characters with a "more" link.
- *Tool calls.* Each is one compact line: a verb a manager would say ("counted the shelf",
  "checked the cash", "asked you to approve") followed by the real call in small monospace
  (`get_stock(sku=CC-TEE-WHITE, size=S)`). Click the line and the raw arguments and the result the
  tool returned open underneath. A refused call (the vendor block, a payment the rules stop) turns
  red and carries a "refused" chip. Every fact in the feed is one click from its evidence.
- *Notes and the call.* A note the agent wrote on the ticket is a dashed card. The Boss's final
  call is a wider card tinted by outcome: green for resolved, amber for waiting on you, red for
  blocked. If the back end sent the Boss back for claiming a resolution it had not made, that
  appears too, as an amber "Sent back" notice, because the human should see the guardrail work.

Quiet events (assignment, priority, the run starting, the shop reset) print as one gray line so
the conversation is not interrupted by bookkeeping.

## 4. How resolved tickets and cash show up

**A resolved ticket is stamped.** The card dims a little, the chip turns green, and a rotated
green "RESOLVED" stamp sits across the corner, the way a paper ticket would be stamped on a desk.
When a run ends in a resolution while you are watching, the stamp slams in (it starts large and
settles with a small bounce) and the card glows once; a toast repeats the Boss's summary. Select
the card and the written resolution appears under it, in green, as the record of what was done.
The run button on a resolved ticket changes to "Run the team again", so nothing is locked.

**Cash is felt, not just updated.** The checking balance is the largest figure on the page. When a
payment lands it counts down from the old balance to the new one over about a second, turns amber
while it is falling, and a small "−$2,400" floats up beside it for three seconds. The approve
button carries the amount ("Approve & pay $2,400"), so what is about to leave the account is
never a surprise, and the toast that follows states the new balance. Money only moves through
that button; the agents can prepare a payment and ask, but the dashboard offers them no way to pay.

## 5. The human's desk: "Needs you"

When something is waiting the panel takes an amber top rule and a "1 waiting" count. Each card
states the kind and the reference ("Rent · lease 1", "Invoice · invoice 501"), the amount in
serif, the agent's rationale word for word, who asked and for which ticket (a link that selects
it), and the two buttons. "Signed as Store Manager" under the buttons shows the name that will be
written on the approval and the payment; change it in the top bar and it changes here. Reject
opens an inline note field inside the card, no browser dialog. Once decided, approvals fold into a
small "Decided" list with their status chips. After an approval the Boss re-works the ticket in
the background, which is how a ticket goes from "Needs approval" to "Resolved" without anyone
re-typing anything.

## 6. The features that make it feel special

- **A floor you can watch.** Tool calls, asks, and reports arrive within a second or two of
  happening (the dashboard polls the timeline every 1.5 s while the team works, every 5 s when it
  is idle, and only asks for events it has not seen). Typing dots in the active agent's colour sit
  at the bottom of the feed, and a thin blue line crawls under the header while a run is on.
- **The strip's "doing" line.** Glance at the five avatars and you know who has the ticket and
  what they are doing, before reading a word of the feed.
- **Plain words with the receipt attached.** "Checked the lease" for the manager; `get_lease(lease_id=1)`
  and the raw result for the auditor, one click down.
- **The delegation chain, written out.** Every ask shows Boss → Facilities → Accounting, so a
  two-level hand-off reads as what it is.
- **"Who did what" writes itself.** For the selected ticket, each agent gets a line with its tool
  count, its tools in words, who it asked, how many notes it wrote, and the last thing it said,
  in quotation marks. It is the short summary the brief asked for, and it is built live from the
  same events, so it never disagrees with the feed.
- **Jump to latest.** Scroll up to read something and the feed stops following; a small pill
  offers the way back.
- **Two-click reset.** "Reset shop" arms a red "Yes, reset to seed" beside a "Keep"; it disarms
  itself after fifteen seconds. No browser dialog, and the audit trail keeps the record.
- **Your name, remembered.** "Approving as" is kept in the browser, so every approval in a session
  carries the same signature.
- **Toasts in the shop's voice.** "Paid $2,400 · Checking is now $1,000. The Boss is re-working
  ticket 102." Each toast says what happened and what happens next.
- **It never claims what it does not know.** If the back end is down the top status reads "Back
  end offline" and a banner gives the start command; if the back end cannot reach the MCP server,
  a second banner says so. The page shows only what the API returned.

## 7. What is deliberately absent

No send button on a draft (nothing is emailed). No pay button without an approval, and no approval
without a human's name. No way to edit a ticket's facts, stock, or prices from the page. No
numbers computed in the browser: counts and balances are the server's, formatted. The restraint is
the point: the dashboard is a window on the team and a desk for the human, not a second place
where shop facts can be made.

## 8. Screenshots (output/screens/)

| File | Moment |
|---|---|
| `dashboard-01-idle.jpg` | The desk at rest: board, empty floor, an invoice approval waiting. |
| `dashboard-02-run-in-progress.jpg` | Ticket 102 running: Facilities lit and "reading the ticket", the Boss's ask with its chain, typing dots, the card amber. |
| `dashboard-03-needs-approval.jpg` | The run ended waiting on the human: the Boss's call, the rent approval card with "Approve & pay $2,400". |
| `dashboard-04-paid-cash-drops.jpg` | The second after approving: the toast, the paid receipt in the feed, the re-work starting, checking at $1,000. |
| `dashboard-05-resolved.jpg` | The re-work done: the stamp on the card, the resolution under it, the Boss's call in green, "Who did what" filled in. |

## 9. How it talks to the back end

`frontend/src/api.ts` is a small typed client over `fetch`; the base URL is
`http://localhost:8000` unless `VITE_API_URL` says otherwise. The back end allows the Vite origin
(`http://localhost:5173`, plus any other local port) through CORS. The page polls `/health`,
`/tickets`, `/cash`, `/approvals` and `/drafts` together (every 2.5 s while a run is on, 8 s when
idle) and `/events?since=<last_id>` for the feed. Running a ticket posts to `/tickets/{id}/run`
and then follows `/runs/{job}` until it ends; a run started elsewhere (the console runner, or the
re-work the approve route starts) is picked up from `/health` so the board shows it the same way.
Approve posts to `/approvals/{id}/approve`, the only call that moves cash; the response's new
balance is applied at once, and the cash counter does the rest.
