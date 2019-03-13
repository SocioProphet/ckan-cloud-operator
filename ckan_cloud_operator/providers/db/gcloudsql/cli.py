import click

from ckan_cloud_operator import logs
from ckan_cloud_operator.providers.db.gcloudsql import manager


@click.group('gcloudsql')
def gcloudsql_group():
    """Manage Google Cloud SQL instances for centralized DB services"""
    pass


@gcloudsql_group.command()
@click.option('--interactive', is_flag=True)
@click.option('--db-prefix')
def initialize(interactive, db_prefix):
    """Enable Google Cloud SQL as the main DB provider"""
    manager.initialize(interactive=interactive, db_prefix=db_prefix)
    logs.exit_great_success()



@gcloudsql_group.command()
@click.argument('OPERATION_ID')
def operation_status(operation_id):
    logs.print_yaml_dump(manager.get_operation_status(operation_id))


@gcloudsql_group.command()
@click.argument('DATABASE')
@click.argument('CONNECTION_STRING', required=False)
def create_backup(database, connection_string):
    manager.create_backup(database, connection_string)
    logs.exit_great_success()


@gcloudsql_group.command()
@click.option('--missing', is_flag=True)
@click.option('--one', is_flag=True)
def create_all_backups(missing, one):
    manager.create_all_backups(missing, one)
    logs.exit_great_success()
