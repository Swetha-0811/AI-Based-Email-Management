from django.db import migrations, connection

class Migration(migrations.Migration):

    dependencies = [
        ('inbox', '0001_initial'),
    ]

    def rename_column(apps, schema_editor):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("""
                ALTER TABLE inbox_importantemail 
                RENAME COLUMN message_id TO email_id
            """)

    def reverse_rename_column(apps, schema_editor):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("""
                ALTER TABLE inbox_importantemail 
                RENAME COLUMN email_id TO message_id
            """)

    operations = [
        migrations.RunPython(rename_column, reverse_rename_column),
    ]