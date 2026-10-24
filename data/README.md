# Local runtime state

`trafficeye.sqlite3` is the initialized SQLite database. The release ZIP contains a clean, empty schema, not private results or credentials. At startup TrafficEye creates the database if missing, a unique `access.key`, and folders for uploads, previews, evidence and latest frames. `settings.json` stores validated defaults for future jobs.

Never commit this directory's runtime contents. All private HTTP media requests require authentication. Files are not encrypted at rest: restrict Windows ACLs to your own account and use disk encryption if necessary. Stop the backend before making a complete backup of this directory. The UI's Delete action removes only files and records owned by that job.
