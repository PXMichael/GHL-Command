# GHL Command for Hermes Agent

GoHighLevel lives inside Hermes. Create contacts, move deals, send email and SMS, trigger workflows from chat. Live in 90 seconds, no browser clicks.

You supply your own GoHighLevel Location ID. The plugin ships no default location and never targets an account you did not configure.

## What it does

Twelve tools in the `ghl-command` toolset:

- `ghl_list_contacts` — list contacts for a location
- `ghl_search_contacts` — search by email or name
- `ghl_create_contact` — create a contact
- `ghl_update_contact` — update a contact (no locationId in the body)
- `ghl_delete_contact` — delete a contact
- `ghl_send_sms` — send SMS via conversations
- `ghl_send_email` — send email via conversations
- `ghl_list_pipelines` — list pipelines
- `ghl_search_opportunities` — search opportunities
- `ghl_move_opportunity` — move an opportunity to a stage
- `ghl_list_workflows` — list workflows
- `ghl_enroll_workflow` — enroll a contact with `POST /contacts/{contactId}/workflow/{workflowId}` and `{}`

All calls go to `https://services.leadconnectorhq.com` with `Version: 2021-07-28`. That's the only host that accepts `pit-` Private Integration Tokens. `POST /contacts/search` uses `pageLimit`, not `limit`. Workflow enrollment uses the exact singular route. Contact update does not send `locationId`.

## Install

```bash
hermes plugins install PXMichael/ghl-command
hermes plugins enable ghl-command
```

Or from the catalog once listed:

```bash
hermes plugins install ghl-command
```

## Setup

1. In GoHighLevel, open Settings, Integrations, Private Integrations.
2. Create a token inside the target sub-account (not agency level unless you use Location Access).
3. Grant scopes:
   - `contacts.readonly`, `contacts.write`
   - `conversations.readonly`, `conversations.write`
   - `opportunities.readonly`, `opportunities.write`
   - `calendars.readonly`, `calendars.write`
   - `locations.readonly`
   - `workflows.readonly`
4. Save the token. Add it through Hermes secrets as `GHL_API_KEY`.
5. Add your Location ID as `GHL_LOCATION_ID`. Both secrets are required. Without them the tools stay hidden.

In Hermes:

```bash
hermes auth add ghl-command:ghl
```

Then paste the `pit-` token when prompted. Or set `GHL_API_KEY` in your profile `.env` through Hermes secrets so `agent.secret_scope.get_secret("GHL_API_KEY")` can read it.

## Demo story

One subscriber, start to finish, from chat.

1. `ghl_list_workflows` shows the available workflows.
2. `ghl_create_contact` creates the subscriber with a tag.
3. `ghl_enroll_workflow` enrolls them in the sequence.
4. `ghl_send_email` sends the link.
5. `ghl_list_pipelines` then `ghl_move_opportunity` shows the deal stage.

All five steps run from chat. No browser clicking.

## Security notes

- Secrets are read via `get_secret`, never `os.environ` directly, so profile multiplexing works.
- The plugin never reads `.env` files, `auth.json`, or browser stores.
- Writes require a valid token; without `GHL_API_KEY` and `GHL_LOCATION_ID` the tools stay hidden.
- There is no default location. The plugin never writes to an account the user did not configure.
- The plugin sends network calls only to `services.leadconnectorhq.com`.

## Development

Validate like catalog CI does:

```bash
hermes plugins validate ./ghl-command --install-deps
```

Run tests:

```bash
python -m pytest tests/
```

## License

MIT
