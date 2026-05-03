from django.apps import AppConfig

_sqlite_connection_hook_registered = False


def _configure_sqlite_connection(sender, connection, **kwargs):
    """
    Mitigate SQLITE_BUSY without WAL: rollback journal only (single db.sqlite3 file).

    Never enables WAL, so no -wal / -shm sidecars. Uses long busy waits + checkpoint
    away from WAL if an older DB file still had WAL enabled.
    """
    if connection.vendor != 'sqlite':
        return
    try:
        with connection.cursor() as cursor:
            jm = cursor.execute('PRAGMA journal_mode;').fetchone()
            if jm and str(jm[0]).upper() == 'WAL':
                cursor.execute('PRAGMA wal_checkpoint(FULL);')
            cursor.execute('PRAGMA journal_mode=DELETE;')
            cursor.execute('PRAGMA busy_timeout=60000;')
    except Exception:
        pass


class BouRoutinesAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bou_routines_app'

    def ready(self):
        import bou_routines_app.signals

        global _sqlite_connection_hook_registered
        if _sqlite_connection_hook_registered:
            return
        _sqlite_connection_hook_registered = True

        from django.db.backends.signals import connection_created

        connection_created.connect(
            _configure_sqlite_connection,
            dispatch_uid='bou_routines_app.configure_sqlite_connection',
        )
