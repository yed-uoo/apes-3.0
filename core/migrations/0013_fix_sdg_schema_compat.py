from django.db import migrations


def forward_fix_sdg_schema(apps, schema_editor):
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        tables = connection.introspection.table_names(cursor)
        if "core_sustainabledevelopmentgoal" not in tables:
            return

        cursor.execute("PRAGMA table_info(core_sustainabledevelopmentgoal)")
        columns = {row[1] for row in cursor.fetchall()}

        if "content" not in columns:
            cursor.execute(
                "ALTER TABLE core_sustainabledevelopmentgoal "
                "ADD COLUMN content text NOT NULL DEFAULT ''"
            )

        if "submitted_by_id" not in columns:
            cursor.execute(
                "ALTER TABLE core_sustainabledevelopmentgoal "
                "ADD COLUMN submitted_by_id bigint NULL "
                "REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED"
            )

        # Best-effort backfill from legacy schema if available.
        cursor.execute("PRAGMA table_info(core_sustainabledevelopmentgoal)")
        columns_after = {row[1] for row in cursor.fetchall()}
        if "sdg_justification" in columns_after:
            cursor.execute(
                "UPDATE core_sustainabledevelopmentgoal "
                "SET content = sdg_justification "
                "WHERE COALESCE(content, '') = ''"
            )


def backward_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_abstract_coordinator_status_abstract_guide_status_and_more"),
    ]

    operations = [
        migrations.RunPython(forward_fix_sdg_schema, backward_noop),
    ]
