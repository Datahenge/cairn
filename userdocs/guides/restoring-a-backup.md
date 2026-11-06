# Restoring a Database Backup

This page walks you through restoring a Frappe backup onto a target that cairn manages. It
covers a backup taken on the same site, and a copy brought in from another site, such as
production data loaded into staging.

cairn has no restore command. It does not read or write your database, except for the
`bench migrate` that follows a deploy. A restore is something you run by hand with Frappe's
own `bench restore`. cairn's part is getting you a shell in the right container and bringing
the stack back afterward.

!!! danger "A restore replaces the whole database"
    `bench restore` drops the site's database and recreates it from the backup file.
    Everything written since that backup was taken is gone. Step 2 takes a fresh backup first,
    so you can undo the restore. Don't skip it.

The examples use the site `erp.acmecorp.com`. Substitute your own: it's the `site` value in
`/etc/cairn/adopt.toml`.

## 1. Stop the reconcile timer

The reconcile timer keeps running during a restore. If a new image reaches the environment
tag partway through, the timer recreates the stack and runs `bench migrate` against a
half-restored database. `cairn-adopt stop` can't prevent this, because it takes down the
containers the restore needs. Stop the timer instead:

```bash
sudo systemctl stop cairn-reconcile.timer
```

This stops the timer for now. It stays enabled, so it starts again at the next boot.

## 2. Take a fresh backup

Open a shell in the bench container and back up the site as it stands:

```bash
cairn-adopt shell
```

```bash
bench --site erp.acmecorp.com backup --with-files
```

Stay in this shell for the steps that follow.

## 3. Put the backup files in place

Frappe writes backups to the site's own backups directory, named by timestamp and site:

```bash
ls -l /home/frappe/frappe-bench/sites/erp.acmecorp.com/private/backups
```

A full backup is four files sharing one prefix, for example `20261106_141502-erp_acmecorp_com`:

| File | Holds |
| --- | --- |
| `…-database.sql.gz` | the database |
| `…-files.tar` | public attachments |
| `…-private-files.tar` | private attachments |
| `…-site_config_backup.json` | the source site's `site_config.json` |

The tar files end in `.tgz` instead if the backup was compressed. An encrypted backup carries
`-enc` before the extension.

**If the backup is already in that directory**, skip to step 4. That includes the backup
`cairn-adopt setup` takes before it changes anything.

**If the backup is somewhere else**, copy it onto the target, then into the container.
`cairn-adopt cp` runs on the target itself, not in the container shell. Open a second SSH
session to the target, or `exit` the container shell and reopen it with `cairn-adopt shell` for
step 4.

```bash
cairn-adopt cp 20261106_141502-erp_acmecorp_com-database.sql.gz \
  backend:/home/frappe/frappe-bench/sites/erp.acmecorp.com/private/backups/
```

`backend` is the bench container. Repeat the `cp` for each of the other three files. Copy the
`site_config_backup.json` too, because step 5 needs it.

## 4. Run the restore

Back in the container shell, give `bench restore` absolute paths to the database file and
both tar files:

```bash
cd /home/frappe/frappe-bench/sites/erp.acmecorp.com/private/backups

bench --site erp.acmecorp.com restore "$PWD/20261106_141502-erp_acmecorp_com-database.sql.gz" \
  --with-public-files "$PWD/20261106_141502-erp_acmecorp_com-files.tar" \
  --with-private-files "$PWD/20261106_141502-erp_acmecorp_com-private-files.tar"
```

`bench restore` asks for the database superuser name (press Enter for `root`) and its
password. If the stack runs its own MariaDB from cairn's compose recipe, the password is the
`DB_PASSWORD` value in the stack's env file. If the database is external, ask whoever
administers it. Answering at the prompt keeps the password out of your shell history.
`--db-root-password` exists, but avoid it for that reason.

If the backup was taken on a newer Frappe version than the image runs, Frappe warns that
restoring it isn't recommended and asks whether to continue. Answer no, unless you know why
you're doing it.

**For an encrypted backup taken on a different site**, add
`--encryption-key <key>`. The key is that site's `backup_encryption_key`. You'll find it in
its `site_config_backup.json`. Without the flag, Frappe tries this site's own key, and the
decryption fails.

## 5. Copy the data encryption key, for a backup from another site

Skip this step if the backup came from this same site.

Frappe encrypts stored passwords, such as email account and integration credentials, with
the site's `encryption_key`. The restore brings over the other site's encrypted values, but
`site_config.json` still holds this site's key. Those values won't decrypt until the keys
match.

Read `encryption_key` out of the backup's `site_config_backup.json`. It's a different setting
from `backup_encryption_key`. Then set it on this site:

```bash
bench --site erp.acmecorp.com set-config encryption_key '<value from site_config_backup.json>'
```

Everything else in `site_config.json` stays this site's own, including the database name and
password. That's correct. Don't copy those over.

This site's previous key is still in the backup you took in step 2, in its
`site_config_backup.json`. You'll need it back if you ever restore that backup.

!!! warning "A copy of production behaves like production"
    The restored database brings the other site's email accounts, scheduled jobs, and
    integration settings with it. Check those before the stack is back up and running jobs.

## 6. Bring the stack back

Leave the container shell, then restart the stack:

```bash
exit
cairn-adopt restart
```

`restart` stops the stack and converges it again, which includes running `bench migrate`.
That brings an older backup's schema up to the apps this image runs. It converges to whatever
image the environment tag names, as it always does.

Then start the reconcile timer again:

```bash
sudo systemctl start cairn-reconcile.timer
```

## Next

- **[Operating the Stack](../target/operating.md)** covers the other everyday verbs:
  logs, consoles, and taking the stack down for maintenance.

*Not yet exercised against a live target. The steps are based on reading the source for
`cairn-adopt` and for Frappe 16.20.0's `bench restore`. Treat this page as
documented-but-unproven until a note here says it has been run.*
