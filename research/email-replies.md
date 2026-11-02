# Email reply tracking across providers

Answers [ticket #4](https://github.com/cutture/Job-Copilot/issues/4). Sources were read on 2026-11-01. Nothing here was tested against a live mailbox.

## Answer

Poll, and put each provider behind one small adapter with the contract "new messages since this cursor". Polling fits the planned Postgres queue, needs no public endpoint, and works the same for every provider.

| Order | Adapter | Reaches | Setup for a self-hosting user |
|---|---|---|---|
| 1 | IMAP with an app password | Gmail, Yahoo, iCloud, and most other providers | Minutes: turn on two-factor sign-in and create an app password |
| 2 | Microsoft Graph delta query | Outlook.com and Microsoft 365 | An app registration of their own |
| 3 | Gmail API with `gmail.readonly` | Gmail, with API-enforced read-only access | A Google Cloud project of their own |

This order and the recommendation are my judgement. The facts behind them are cited below.

For Gmail, set the user's Cloud project to production rather than Testing, and accept the unverified-app warning. Testing mode expires refresh tokens after 7 days, which breaks unattended polling.

Skip push and multi-provider services for v1. Multi-provider services matter only for a hosted version.

## Comparison

| | Gmail API | Microsoft Graph | IMAP | Multi-provider service |
|---|---|---|---|---|
| New-mail detection | `history.list` poll, or Pub/Sub push | Delta query poll, or webhook | Poll, or IDLE | Vendor API |
| Public endpoint needed | No (Pub/Sub pull is available) | Only for webhooks | No | Depends on the vendor; not checked |
| Read-only option | `gmail.readonly`, `gmail.metadata` | `Mail.Read`, `Mail.ReadBasic` | `EXAMINE` only; the credential itself has full access | Depends on the underlying scopes |
| Token or credential lifetime | 7 days in Testing, otherwise until an expiry event below | 90 days by default, replaced on each use | App password, until revoked | Vendor-managed |
| API cost | Free within quota | No charge found in the pages read; not confirmed | Free | $1 per account per month and up |

## Gmail API

**Polling.** A [full sync followed by `history.list`](https://developers.google.com/workspace/gmail/api/guides/sync) returns only what changed since a stored `historyId`. History is typically kept for at least a week but can be much shorter, and a 404 means a full sync is required. The worker must handle that case, for example after a stopped VPS comes back.

**Push.** [Push](https://developers.google.com/workspace/gmail/api/guides/push) requires a Cloud Pub/Sub topic, publish rights for Gmail's service account, and a `watch` call renewed at least every 7 days (Google recommends daily). The notification carries only the address and a `historyId`, so `history.list` is still needed. Google says notifications can be delayed or dropped and that apps should keep a periodic `history.list` fallback. Push therefore adds setup without removing the polling code.

**Read-only scopes.** [All Gmail read scopes are restricted](https://developers.google.com/workspace/gmail/api/auth/scopes), including `gmail.readonly` and `gmail.metadata`. No non-restricted scope reads mail. `gmail.metadata` gives labels and headers only, and [it can't use the `q` search parameter](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list), so filtering has to happen in the app.

**OAuth limits**, from [Google's OAuth documentation](https://developers.google.com/identity/protocols/oauth2):

- A project in Testing gets refresh tokens that expire in 7 days, unless it requests only basic profile scopes.
- A token also stops working after six months unused, on revocation, or on a password change when it includes Gmail scopes.
- Each Google Account can hold 100 refresh tokens per client ID. Going over silently invalidates the oldest.

**Self-hosting setup.** The user creates a Cloud project, enables the API, configures a consent screen, and creates a client. Google [exempts personal-use apps with fewer than 100 users from verification](https://support.google.com/cloud/answer/13464323); those users click through the [unverified-app warning](https://support.google.com/cloud/answer/7454865). Since each user has their own project, the 100-user cap should not matter (my inference). Desktop clients [can use a loopback redirect with PKCE](https://developers.google.com/identity/protocols/oauth2/native-app), which suits a local install. A VPS install needs its redirect flow worked out at implementation.

**Cost.** [The API has no additional cost within its quota](https://developers.google.com/workspace/gmail/api/reference/quota): 6,000 units per minute per user. `history.list` costs 2 units, so polling every 5 minutes uses about 576 units a day (my arithmetic). The same page mentions planned charges for exceeding quota. Pub/Sub [lists 10 GiB free per month, then $40 per TiB](https://cloud.google.com/pubsub/pricing), and these small notifications should stay inside the free allowance (my inference).

## Microsoft Graph

**Polling.** [Delta query](https://learn.microsoft.com/en-us/graph/delta-query-messages) returns changes through a stored `deltaLink`. It works per folder, so tracking the Inbox alone is simple, but mail moved by rules needs each folder tracked. `changeType=created` narrows the results to new messages. [The limit](https://learn.microsoft.com/en-us/graph/throttling-limits) is 10,000 requests per 10 minutes per app and mailbox, far above this need.

**Push.** [Webhooks need a public HTTPS endpoint](https://learn.microsoft.com/en-us/graph/change-notifications-delivery-webhooks) that answers validation within 10 seconds and notifications within 3 seconds. Dropped notifications can't be recovered. [Message subscriptions last under 7 days](https://learn.microsoft.com/en-us/graph/change-notifications-overview) and must be renewed. A local Docker install can't receive these without a tunnel.

**Read-only scopes.** [Delegated `Mail.Read` and `Mail.ReadBasic`](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/concepts/permissions-reference.md) don't need admin consent and work with personal accounts. `Mail.ReadBasic` excludes the body and preview, which limits how well a Reply can be classified. A work tenant's own consent policy may still block a user (my inference).

**Token lifetime.** [Refresh tokens last 90 days by default](https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens) and are replaced on each use, so the worker must save the new one every time. A polling worker keeps renewing it, but the app must handle revocation by asking the user to sign in again.

**Self-hosting setup.** [Registering an app](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app) requires an Azure account with an active subscription, which can be created for free. The user chooses the account types and needs the `offline_access` scope to get refresh tokens.

**Cost.** I found no per-call charge for these mail endpoints in the pages read, but I did not find a statement confirming it either.

## IMAP

**Coverage.** App passwords exist at [Google](https://support.google.com/mail/answer/185833), [Yahoo](https://help.yahoo.com/kb/SLN15241.html) and [Apple](https://support.apple.com/en-us/102654).

- Google and Apple require two-factor sign-in. Apple allows 25 active passwords.
- Google and Apple revoke app passwords when the main password changes. Yahoo's stay active until deleted.
- Google discourages app passwords, and they may be unavailable on work or school accounts, security-key-only setups, or Advanced Protection.

**Microsoft is the exception.** [Exchange Online has disabled Basic authentication for IMAP](https://learn.microsoft.com/en-us/exchange/clients-and-mobile-in-exchange-online/deprecation-of-basic-authentication-exchange-online), and it can't be re-enabled. [IMAP with OAuth works for Microsoft 365 and Outlook.com](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth), but it needs the same app registration as Graph, so Graph is the better route.

**Read-only is weak.** [`EXAMINE` opens a mailbox read-only](https://www.rfc-editor.org/rfc/rfc9051), but that is the client's choice. An app password has the full access of the account's IMAP session. OAuth doesn't help on Gmail either, because [IMAP requires the full `https://mail.google.com/` scope](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol). This is acceptable on a box the user controls, but not for a hosted service.

**Change detection.** [IDLE](https://www.rfc-editor.org/rfc/rfc2177) gives near-real-time updates but must be re-issued at least every 29 minutes and holds a connection open. A periodic poll is simpler, and Replies don't need to arrive within seconds.

**Cost.** Free, apart from the worker's own running cost.

## Multi-provider services

| Service | Model | Price | Notes |
|---|---|---|---|
| [Nylas](https://nylas.com/pricing) | Hosted | Free for 5 accounts; Essentials $15/month for 10; Pro $43-49/month for 25; extra accounts $1.75-2.25 | The free plan excludes the shared Google app |
| [Aurinko](https://www.aurinko.io/pricing/) | Hosted | From $1 per account per month | Trial terms aren't stated on the pricing page |
| [EmailEngine](https://postalsys.com/plans) | Self-hosted | $1,450 per year, unlimited accounts | Far above the $10 monthly budget for a single user |

[Nylas's shared Google app](https://developer.nylas.com/docs/provider-guides/google/) removes the need for your own Google project and security review, but it needs Pro Annual with the Accelerator add-on, or Enterprise. At [the listed prices](https://nylas.com/pricing) that is about $2,916 a year (12 × $43 + $2,400, my arithmetic). Without it, you still go through Google verification yourself.

Hosted services also put mail on another party's systems. [Nylas caches IMAP messages for a rolling 90 days](https://developer.nylas.com/docs/provider-guides/imap/). That conflicts with the project's privacy stance for a self-hosted install.

## Path to a hosted version

The map defers this, so these are the constraints the v1 data model should not block.

**Gmail** is the main barrier.

- [Apps using sensitive or restricted scopes must complete verification](https://support.google.com/cloud/answer/13463073), and restricted scopes are re-verified yearly.
- [An annual security assessment](https://support.google.com/cloud/answer/13465431) applies at assurance level AL1 or AL2.
- [Storing or transmitting restricted data on servers triggers it](https://developers.google.com/workspace/gmail/api/auth/scopes), so a hosted server can't avoid it.
- [Limited Use rules](https://developers.google.com/terms/api-services-user-data-policy) restrict transfers and human reading of the data.
- [The Workspace policy bars using this data to train general AI models](https://developers.google.com/workspace/workspace-api-user-data-developer-policy). This bears directly on the map's rule about free models: Reply content sent to any LLM must be under no-training terms.

**Microsoft** is lighter. [Publisher verification is free](https://learn.microsoft.com/en-us/entra/identity-platform/publisher-verification-overview) but needs a verified partner account and a work tenant. Without it, users in some tenants can't consent to a newly registered multitenant app.

**IMAP app passwords** should not carry over to hosted. Collecting users' full-access credentials is a much larger security burden (my judgement). A hosted version should use OAuth where it can.

**Design for this now:**

- One connection record per user and mailbox: tenant ID, provider, encrypted credential, and sync cursor.
- Keep only messages matched as Replies, plus the fields needed to show them. This reduces later exposure.
- The worker should treat any revoked credential as "reconnect needed" and show that on the dashboard.

## Not verified

- **No live test.** No adapter, token flow, or provider limit was exercised. In particular, I inferred from documentation that a production-status unverified Gmail project avoids the 7-day expiry. Test this first.
- **Security assessment cost.** The Google and CASA pages I read give no price and don't say who pays.
- **Outlook.com app passwords.** The Exchange page covers tenants, and the consumer support page I tried returned 404. I treat Outlook.com as OAuth-only without direct confirmation.
- **Gmail quota charges.** The quota page mentions charges planned for later in 2026 with 90 days' notice. I did not find the current status, though polling at this volume is far below the limits.
- **Pub/Sub pricing.** The price comes from a search excerpt of the official page, because a direct read returned no pricing text.
- **Microsoft pricing and consent.** No page confirmed that these mail endpoints are free. How an unverified app behaves for personal accounts, and whether a free Azure account needs a payment card, are also unconfirmed.
- **Other providers.** Yahoo and Apple IMAP behaviour, and OAuth options for providers other than Google and Microsoft, were not researched beyond the app-password pages. Zoho, Fastmail, Proton and similar providers were not checked.
- **Vendor details.** Nylas's page gives inconsistent figures for one unrelated Pro feature, so reconfirm prices before relying on them. Vendor read-only scopes and webhook requirements were not checked.
- **Reply matching.** This ticket covers reading mail, not linking it to an Application. Replies to applications made through web forms may not thread with anything the user sent (my inference), so matching will probably need sender domains and content rather than headers alone.
- **Reading method.** Several pages were read through a summarising fetch tool rather than as raw text, so check exact wording against the linked page before quoting it.
