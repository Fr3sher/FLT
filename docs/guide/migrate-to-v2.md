# Move an existing installation to V2

The maintained Git branch is now `v2`. The former `main` is named `v1` and is
read-only. You can keep your current installation, datasets and settings.

## Windows: guided tool for Git installations

[Download LDS-Migrate-to-V2.zip](https://github.com/perfectgf/lora-dataset-studio/releases/download/v2026.09.14.4/LDS-Migrate-to-V2.zip).

1. Close LDS **and its launcher**. In Pinokio, click **Stop** first.
2. Extract the complete tool ZIP to a separate folder, outside the LDS installation.
3. Double-click **migrate-to-v2.bat**. Paste the path of your existing LDS folder
   (the folder containing `backend` and `frontend`).
4. Check the installation and data paths it shows. Type **V2** to proceed.
5. When it says **Done**, start LDS with your usual launcher. In Pinokio, run
   **Update** before **Start** so its Python dependencies are refreshed too.
6. Check your datasets and settings. Choose the optional features you need in
   **Plugins → Store**; the tool does not install or activate plugins for you.

The tool uses the installation's Python, or an existing Python 3.10+ on your
computer, and Git. It does not install either of them or request administrator rights.

## What stays in place

The tool switches application code to the public `v2` branch and configures future
Git updates to follow it. Images, videos, datasets, installed plugins, configuration,
API keys and Python environments remain in their existing folders. Custom absolute
`LDS_DATA_DIR`, `LDS_CONFIG`, `LDS_ENV` and `LDS_PLUGINS_DIR` paths are checked too.
Unusual environment expressions or ambiguous relative overrides require manual help.
If your launcher sets a custom data path, run the helper with the same environment.
The helper stops if it cannot find `studio.db` in the detected data folder; it
does not guess a new location for your data.

Before switching, it saves **studio.db and any WAL/journal sidecars**, configuration
and `.env` files under `.git/lds-migration-backups/` in your installation. It also
creates an `lds-before-v2-…` recovery branch for the old application code. Keep
these until you have checked your installation in V2.

**This is a database/settings backup, not a full media backup.** Keep your normal
backup of images and videos. The tool does not move those files, start LDS, or run
database schema migrations. A new app version can migrate its database on first
launch; switching Git branches alone is not a database downgrade procedure.

The backup includes private settings and may include API keys. Keep it local;
do not attach it to a public issue or Discord message.

## If the tool stops

An open LDS process, occupied server port, local source edit, local commit, Git
operation in progress, linked worktree, or file collision makes the tool stop.
It never uses `reset --hard`, `clean`, an automatic stash or a forced checkout.
An ignored file is protected from being overwritten too.

Keep the installation folder and read the message. Do not delete or re-clone it:
that folder may contain your only copy of the datasets. Ask in Discord **#help**
with the stop message, hiding local paths or other personal details. Keep LDS
closed after an interrupted migration until its branch and backup have been reviewed.

## macOS / Linux or check without switching

Use `migrate_to_v2.py` from the same download, outside your installation:

```sh
python3 migrate_to_v2.py --root "/path/to/lora-dataset-studio" --check
python3 migrate_to_v2.py --root "/path/to/lora-dataset-studio"
```

The check fetches the public `v2` reference, but leaves the current branch and
application files unchanged. The second command shows the plan and asks you to
type **V2** before making a backup and switching.

## ZIP and Docker installations

- **Installed from a release ZIP, without Git:** there is no branch to switch.
  Use **Update & restart** in your existing LDS installation to get the current
  release. Do not delete its folder or copy your data into a fresh installation.
  The helper detects this case and leaves it unchanged.
- **Docker:** use the [Docker update guide](docker.md). This desktop tool does
  not migrate running containers or manage their volumes.

Tool source: [Python helper](../../scripts/migrate_to_v2.py),
[Windows launcher](../../scripts/migrate-to-v2.bat).
