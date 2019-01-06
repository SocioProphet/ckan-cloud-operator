import sys
import json
import yaml
import traceback
import subprocess
import tempfile
import os
import click
from xml.etree import ElementTree
from ckan_cloud_operator.deis_ckan.instance import DeisCkanInstance
from ckan_cloud_operator.infra import CkanInfra
from ckan_cloud_operator import gcloud
from ckan_cloud_operator.gitlab import CkanGitlab


CLICK_CLI_MAX_CONTENT_WIDTH = 200


def great_success():
    print('Great Success!')
    exit(0)


@click.group(context_settings={'max_content_width': CLICK_CLI_MAX_CONTENT_WIDTH})
def main():
    """Manage, provision and configure CKAN Clouds and related infrastructure"""
    pass


@main.command()
@click.option('-f', '--full', is_flag=True)
def cluster_info(full):
    """Get information about the cluster"""
    subprocess.check_call('kubectl cluster-info && '
                          '( kubectl -n ckan-cloud get secret ckan-infra || true ) && '
                          'kubectl config get-contexts $(kubectl config current-context) && '
                          'kubectl get nodes', shell=True)
    if full:
        infra = CkanInfra()
        output = gcloud.check_output(f'sql instances describe {infra.GCLOUD_SQL_INSTANCE_NAME} --format=json',
                                     project=infra.GCLOUD_SQL_PROJECT)
        data = yaml.load(output)
        print(yaml.dump({'gcloud_sql': {'connectionName': data['connectionName'],
                                        'databaseVersion': data['databaseVersion'],
                                        'gceZone': data['gceZone'],
                                        'ipAddresses': data['ipAddresses'],
                                        'name': data['name'],
                                        'project': data['project'],
                                        'region': data['region'],
                                        'selfLink': data['selfLink'],
                                        'state': data['state']}}))
        output = subprocess.check_output(f'curl {infra.SOLR_HTTP_ENDPOINT}/admin/collections?action=LIST', shell=True)
        if output:
            root = ElementTree.fromstring(output.decode())
            print('solr-collections:')
            for e in root.find('arr').getchildren():
                print(f'- {e.text}')
        else:
            raise Exception()


@main.command()
def install_crds():
    """Install ckan-cloud-operator custom resource definitions"""
    DeisCkanInstance.install_crd()
    great_success()


@main.command()
@click.argument('GITLAB_PROJECT_NAME')
def initialize_gitlab(gitlab_project_name):
    """Initialize the gitlab integration"""
    CkanGitlab(CkanInfra()).initialize(gitlab_project_name)
    great_success()


@main.command()
def activate_gcloud_auth():
    """Authenticate with gcloud CLI using the ckan-cloud-operator credentials"""
    infra = CkanInfra()
    gcloud_project = infra.GCLOUD_AUTH_PROJECT
    service_account_email = infra.GCLOUD_SERVICE_ACCOUNT_EMAIL
    service_account_json = infra.GCLOUD_SERVICE_ACCOUNT_JSON
    if all([gcloud_project, service_account_email, service_account_json]):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            f.write(service_account_json.encode())
        try:
            gcloud.check_call(
                f'auth activate-service-account {service_account_email} --key-file={f.name}',
                with_activate=False
            )
        except Exception:
            traceback.print_exc()
        os.unlink(f.name)
        exit(0)
    else:
        print('missing gcloud auth details')
        exit(1)


@main.group()
def ckan_infra():
    """Manage the centralized infrastructure"""
    pass


@ckan_infra.command('clone')
def ckan_infra_clone():
    """Clone the infrastructure secret from an existing secret piped on stdin

    Example: KUBECONFIG=/other/.kube-config kubectl -n ckan-cloud get secret ckan-infra -o yaml | ckan-cloud-operator ckan-infra clone
    """
    CkanInfra.clone(yaml.load(sys.stdin.read()))
    great_success()


@ckan_infra.group('set')
def ckan_infra_set():
    """Set or overwrite infrastructure secrets"""
    pass


@ckan_infra_set.command('gcloud')
@click.argument('GCLOUD_SERVICE_ACCOUNT_JSON_FILE')
@click.argument('GCLOUD_SERVICE_ACCOUNT_EMAIL')
@click.argument('GCLOUD_AUTH_PROJECT')
def ckan_infra_set_gcloud(*args):
    """Sets the Google cloud authentication details, should run locally or mount the json file into the container"""
    CkanInfra.set('gcloud', *args)
    great_success()


@ckan_infra_set.command('docker-registry')
@click.argument('DOCKER_REGISTRY_SERVER')
@click.argument('DOCKER_REGISTRY_USERNAME')
@click.argument('DOCKER_REGISTRY_PASSWORD')
@click.argument('DOCKER_REGISTRY_EMAIL')
def ckan_infra_set_docker_registry(*args):
    """Sets the Docker registry details for getting private images for CKAN pods in the cluster"""
    CkanInfra.set('docker-registry', *args)
    great_success()


@ckan_infra.command('get')
def ckan_infra_get():
    """Get the ckan-infra secrets"""
    print(yaml.dump(CkanInfra.get(), default_flow_style=False))


@ckan_infra.command('admin-db-connection-string')
def ckan_infra_admin_db_connection_string():
    """Get a DB connection string for administration

    Example: psql -d $(ckan-cloud-operator admin-db-connection-string)
    """
    infra = CkanInfra()
    postgres_user = infra.POSTGRES_USER
    postgres_password = infra.POSTGRES_PASSWORD
    postgres_host = infra.POSTGRES_HOST
    postgres_port = '5432'
    db = sys.argv[3] if len(sys.argv) > 3 else ''
    print(f'postgresql://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/{db}')


@main.group()
def deis_instance():
    """Manage Deis CKAN instance resources"""
    pass


@deis_instance.command('list')
@click.option('-f', '--full', is_flag=True)
def deis_instance_list(full):
    """List the Deis instances"""
    DeisCkanInstance.list(full)


@deis_instance.command('get')
@click.argument('INSTANCE_ID')
@click.argument('ATTR', required=False)
def deis_instance_get(instance_id, attr):
    """Get detailed information about an instance, optionally returning only a single get attribute

    Example: ckan-cloud-operator get <INSTANCE_ID> deployment
    """
    print(yaml.dump(DeisCkanInstance(instance_id).get(attr), default_flow_style=False))


@deis_instance.group('create')
def deis_instance_create():
    """Create and update an instance"""
    pass


@deis_instance_create.command('from-gitlab')
@click.argument('GITLAB_REPO_NAME')
@click.argument('SOLR_CONFIG_NAME')
@click.argument('NEW_INSTANCE_ID')
def deis_instance_create_from_gitlab(*args):
    """Create and update a new instance from a GitLab repo containing Dockerfile and .env

    Example: ckan-cloud-operator deis-isntance create --from-gitlab viderum/cloud-demo2 ckan_27_default <NEW_INSTANCE_ID>
    """
    DeisCkanInstance.create('from-gitlab', *args).update()
    great_success()


@deis_instance_create.command('from-gcloud-envvars')
@click.argument('PATH_TO_INSTANCE_ENV_YAML')
@click.argument('IMAGE> <SOLR_CONFIG')
@click.argument('GCLOUD_DB_URL')
@click.argument('GCLOUD_DATASTORE_URL')
@click.argument('NEW_INSTANCE_ID')
def deis_instance_create_from_gcloud_envvars(*args):
    """Create and update an instance from existing DB dump stored in gcloud sql format on google cloud storage."""
    DeisCkanInstance.create('from-gcloud-envvars', *args).update()
    great_success()


@deis_instance.command('edit')
@click.argument('INSTANCE_ID')
@click.argument('EDITOR', default='nano')
def deis_instance_edit(instance_id, editor):
    """Launch an editor to modify and update an instance"""
    subprocess.call(f'EDITOR={editor} kubectl -n ckan-cloud edit DeisCkanInstance/{instance_id}', shell=True)
    DeisCkanInstance(instance_id).update()
    great_success()


@deis_instance.command('update')
@click.argument('INSTANCE_ID')
@click.argument('OVERRIDE_SPEC_JSON', required=False)
@click.option('--persist-overrides', is_flag=True)
@click.option('--wait-ready', is_flag=True)
def deis_instance_update(instance_id, override_spec_json, persist_overrides, wait_ready):
    """Update an instance to the latest resource spec, optionally applying the given json override to the resource spec

    Examples:

    ckan-cloud-operator update <INSTANCE_ID> '{"envvars":{"CKAN_SITE_URL":"http://localhost:5000"}}' --wait-ready

    ckan-cloud-operator update <INSTANCE_ID> '{"flags":{"skipDbPermissions":false}}' --persist-overrides
    """
    override_spec = json.loads(override_spec_json) if override_spec_json else None
    DeisCkanInstance(instance_id, override_spec=override_spec, persist_overrides=persist_overrides).update(wait_ready=wait_ready)
    great_success()


@deis_instance.command('delete')
@click.argument('INSTANCE_ID', nargs=-1)
@click.option('--force', is_flag=True)
def deis_instance_delete(instance_id, force):
    """Permanently delete the instances and all related infrastructure"""
    for id in instance_id:
        try:
            DeisCkanInstance(id).delete(force)
        except Exception:
            traceback.print_exc()
    great_success()


@deis_instance.group('ckan')
def deis_instance_ckan():
    """Manage a running CKAN instance"""
    pass


@deis_instance_ckan.command('paster')
@click.argument('INSTANCE_ID')
@click.argument('PASTER_ARGS', nargs=-1)
def deis_instance_ckan_paster(instance_id, args):
    """Run CKAN Paster commands

    Run without PASTER_ARGS to get the available paster commands from the server

    Examples:

      ckan-cloud-operator deis-instance ckan-paster <INSTANCE_ID> sysadmin add admin name=admin email=admin@ckan

      ckan-cloud-operator deis-instance ckan-paster <INSTANCE_ID> search-index rebuild
    """
    DeisCkanInstance(instance_id).ckan.run('paster', *args)


@deis_instance_ckan.command('port-forward')
@click.argument('INSTANCE_ID')
@click.argument('PORT', default='5000')
def deis_instance_port_forward(instance_id, port):
    """Start a port-forward to the CKAN instance pod"""
    DeisCkanInstance(instance_id).ckan.run('port-forward', port)


@deis_instance_ckan.command('exec')
@click.argument('INSTANCE_ID')
@click.argument('KUBECTL_EXEC_ARGS', nargs=-1)
def deis_instance_ckan_exec(instance_id, kubectl_exec_args):
    """Run kubectl exec on the first CKAN instance pod"""
    DeisCkanInstance(instance_id).ckan.run('exec', *kubectl_exec_args)


@deis_instance_ckan.command('logs')
@click.argument('INSTANCE_ID')
@click.argument('KUBECTL_LOGS_ARGS', nargs=-1)
def deis_instance_ckan_logs(instance_id, kubectl_logs_args):
    """Run kubectl logs on the first CKAN instance pod"""
    DeisCkanInstance(instance_id).ckan.run('logs', *kubectl_logs_args)