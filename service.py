#!/usr/bin/env python

import os
import io
import sys
import shutil
import subprocess
import tempfile
import time

import click
import ruamel.yaml as ryaml
import jinja2

import meta

HERE = os.path.abspath(os.path.dirname(__file__))


def print_error(*args):
    print('ERROR:', *args, file=sys.stderr)


def load_settings(service, config):
    service_descriptor_filepath = os.path.join(HERE, 'services', '{}.yaml'.format(service))
    yaml = ryaml.YAML()
    try:
        with io.open(service_descriptor_filepath, encoding='utf-8') as f:
            descriptor = yaml.load(f)
    except Exception as e:
        return None, 'Failed to load descriptor for service [{}]: {}'.format(service, e)
    else:
        if not descriptor or 'configs' not in descriptor:
            return None, 'Service descriptor invalid or empty'
        if config not in descriptor['configs']:
            return None, 'Config definition not found: {}'.format(config)

        def deep_format(obj):
            if isinstance(obj, dict):
                return {k: deep_format(v) for k, v in obj.items()}
            if isinstance(obj, str):
                return obj.format(service=service, config=config)
            return obj

        settings_common = descriptor.get('common', {})
        settings = deep_format(settings_common)
        settings.update(descriptor['configs'][config] or {})
        settings['PROJECT'] = meta.project
        settings['VERSION'] = meta.version
        settings['SERVICE'] = service
        settings['CONFIG'] = config
        settings['HOME'] = HERE
        settings['PYTHON_CMD'] = sys.executable
        settings['WORKING_DIR'] = settings['HOME']
        settings['LOGGING_DIR'] = os.path.join('/', 'var', 'log', meta.project)
        # settings['env']['LOG_CONFIG'] = os.path.join(os.getcwd(), 'services', 'logging', '{}.yaml'.format(settings['logconfig']))
        env_prefix = descriptor.get('env_prefix')
        if env_prefix:
            settings['env'] = {'{}_{}'.format(env_prefix, k): v for k, v in settings['env'].items()}
        settings['env'] = settings.get('env', {})
        return settings, None


def render_template(localpath, context):
    loader = jinja2.FileSystemLoader(HERE)
    env = jinja2.Environment(loader=loader)
    env.undefined = jinja2.StrictUndefined
    template = env.get_template(localpath)
    result = template.render(context)
    return result


def derive_systemd_name(service, config):
    return '{}.{}.{}'.format(meta.project, service, config)


def systemd_service_path(service_name, extension):
    service_filename = '{}.{}'.format(service_name, extension)
    return os.path.join('/etc/systemd/system', service_filename)


def systemd_install(service_name, extension, service_def):
    systemd_path = systemd_service_path(service_name, extension)
    try:
        with io.open(systemd_path, 'w', encoding='utf-8') as ostream:
            shutil.copyfileobj(io.StringIO(service_def), ostream)
        subprocess.run('systemctl daemon-reload'.split(), check=True)
        subprocess.run('systemctl enable {}'.format(service_name).split(), check=True)
        return None, None
    except Exception as e:
        return None, 'Failed to install [{}]: {}'.format(service_name, e)


def systemd_uninstall(service_name, extension):
    systemd_path = systemd_service_path(service_name, extension)
    try:
        if os.path.exists(systemd_path):
            subprocess.run('systemctl stop {}'.format(service_name).split(), check=True)
            subprocess.run('systemctl disable {}'.format(service_name).split(), check=True)
            os.remove(systemd_path)
        return None, None
    except FileNotFoundError:
        return None, None
    except Exception as e:
        return None, 'Failed to uninstall [{}]: {}'.format(service_name, e)


WAIT_FOR_STARTUP = 1.0  # second(s)


def systemd_start(service_name):
    job = subprocess.run('systemctl restart {}'.format(service_name).split())
    if job.returncode != 0:
        return None, 'Failed to start service: {}'.format(service_name)
    time.sleep(WAIT_FOR_STARTUP)
    job = subprocess.run('systemctl -q status {}'.format(service_name).split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if job.returncode != 0:
        # TODO: inconsistent behavior: service remains enabled
        subprocess.run('systemctl stop {}'.format(service_name).split())
        return None, 'Failed to get service status: {}'.format(service_name)
    return None, None


def systemd_stop(service_name):
    job = subprocess.run('systemctl stop {}'.format(service_name).split())
    if job.returncode != 0:
        return None, 'Failed to stop service: {}'.format(service_name)
    return None, None


def copy_files(srcdir, dstdir):
    shutil.rmtree(dstdir, ignore_errors=True)
    os.makedirs(dstdir)
    if not os.path.exists(srcdir):
        return None, 'Source directory not exists: {}'.format(srcdir)
    job = subprocess.run('rsync -r {}/ {}'.format(srcdir, dstdir).split())
    if job.returncode != 0:
        return None, 'Failed to copy files'
    return None, None


def ensure_dir_exists(path):
    if not os.path.exists(path):
        os.makedirs(path)
    else:
        if not os.path.isdir(path):
            raise Exception('Target path is not directory: {}'.format(path))


def backup_nginx_files(config, filepath):
    targetroot = '/etc/nginx'
    targetincludes = os.path.join(targetroot, 'includes', config)
    targetcerts = os.path.join(targetroot, 'certs', config)
    siteconf_dst = os.path.join(targetroot, 'sites-available', '{}.conf'.format(config))
    siteconf_linkname = os.path.join(targetroot, 'sites-enabled', os.path.basename(siteconf_dst))

    command = 'tar --create --file {} --files-from /dev/null'.format(filepath)
    subprocess.run(command.split(), check=True)

    tar_append_prefix = 'tar --append --directory {} --file {}'.format(targetroot, filepath)

    def append_to_archive(dst):
        if os.path.exists(os.path.join(targetroot, dst)):
            command = '{} {}'.format(tar_append_prefix, dst)
            subprocess.run(command.split(), check=True)

    append_to_archive('sites-available/{}.conf'.format(config))
    append_to_archive('sites-enabled/{}.conf'.format(config))
    append_to_archive('includes/{}'.format(config))
    append_to_archive('certs/{}'.format(config))


def restore_nginx_files(config, filepath):
    targetroot = '/etc/nginx'
    targetincludes = os.path.join(targetroot, 'includes', config)
    targetcerts = os.path.join(targetroot, 'certs', config)
    siteconf_dst = os.path.join(targetroot, 'sites-available', '{}.conf'.format(config))
    siteconf_linkname = os.path.join(targetroot, 'sites-enabled', os.path.basename(siteconf_dst))
    if os.path.exists(siteconf_linkname):
        os.remove(siteconf_linkname)
    if os.path.exists(siteconf_dst):
        os.remove(siteconf_dst)
    shutil.rmtree(targetincludes, ignore_errors=True)
    shutil.rmtree(targetcerts, ignore_errors=True)
    command = 'tar --extract --directory {} --file {}'.format(targetroot, filepath)
    subprocess.run(command.split(), check=True)


def install_nginx_files(config, settings):

    def copy_from_template(context, localtemplatepath, dstpath):
        result = render_template(localtemplatepath, context)
        with io.open(dstpath, 'w', encoding='utf-8') as ostream:
            shutil.copyfileobj(io.StringIO(result), ostream)

    targetroot = '/etc/nginx'
    targetincludes = os.path.join(targetroot, 'includes', config)
    targetcerts = os.path.join(targetroot, 'certs', config)
    ensure_dir_exists(targetcerts)
    certfiles = settings.get('certs', []) or []
    for filename in certfiles:
        src = os.path.join(HERE, 'nginxsite', 'certs', filename)
        shutil.copy(src, targetcerts)
    ensure_dir_exists(targetincludes)
    includefiles = settings.get('includes', []) or []
    for filename in includefiles:
        src = os.path.join('nginxsite', 'includes', filename)
        dst = os.path.join(targetincludes, filename)
        copy_from_template(settings, src, dst)
    mkdirs = settings.get('mkdirs', []) or []
    for dirpath in mkdirs:
        ensure_dir_exists(dirpath)
    siteconf_src = os.path.join('nginxsite', '{}.conf'.format(config))
    siteconf_dst = os.path.join(targetroot, 'sites-available', '{}.conf'.format(config))
    copy_from_template(settings, siteconf_src, siteconf_dst)
    siteconf_linkname = os.path.join(targetroot, 'sites-enabled', os.path.basename(siteconf_dst))
    if os.path.exists(siteconf_linkname):
        os.remove(siteconf_linkname)
    os.symlink(siteconf_dst, siteconf_linkname)


def uninstall_nginx_files(config, settings):
    targetroot = '/etc/nginx'
    targetincludes = os.path.join(targetroot, 'includes', config)
    targetcerts = os.path.join(targetroot, 'certs', config)
    siteconf_dst = os.path.join(targetroot, 'sites-available', '{}.conf'.format(config))
    siteconf_linkname = os.path.join(targetroot, 'sites-enabled', os.path.basename(siteconf_dst))
    if os.path.exists(siteconf_linkname):
        os.remove(siteconf_linkname)
    if os.path.exists(siteconf_dst):
        os.remove(siteconf_dst)
    if os.path.exists(targetincludes):
        shutil.rmtree(targetincludes)
    if os.path.exists(targetcerts):
        shutil.rmtree(targetcerts)


def test_nginx_config():
    command = 'nginx -t'
    subprocess.run(command.split(), check=True)


def reload_nginx_config():
    command = 'nginx -s reload'
    subprocess.run(command.split(), check=True)


@click.group()
def cli():
    """Tool for service control"""
    pass


@cli.command()
@click.argument('service')
@click.argument('config')
def install(service, config):
    """Install service configuration"""
    print('Setting up service [{}] for config [{}]...'.format(service, config))
    settings, error = load_settings(service, config)
    if error is not None:
        print_error(error)
        sys.exit(1)
    try:
        if service == 'nginxsite':
            with tempfile.TemporaryDirectory() as tempdir:
                backupfile = os.path.join(tempdir, 'nginx.backup.tar')
                backup_nginx_files(config, backupfile)
                try:
                    install_nginx_files(config, settings)
                    test_nginx_config()
                    reload_nginx_config()
                except Exception as e:
                    try:
                        print('Restoring Nginx configuration to previous state...')
                        restore_nginx_files(config, backupfile)
                        test_nginx_config()
                        reload_nginx_config()
                        print('Nginx previous configuration restored and loaded')
                    except Exception as e:
                        print_error('Failed to restore Nginx config:', e)
                        print_error('Nginx config left corrupted!')
                    raise
        elif service == 'nginxmain':
            targetfile = '/etc/nginx/nginx.conf'
            with tempfile.TemporaryDirectory() as tempdir:
                backupfile = os.path.join(tempdir, 'nginx.conf')
                shutil.copy(targetfile, backupfile)
                try:
                    srcfile = os.path.join(HERE, 'nginxmain', '{}.conf'.format(config))
                    shutil.copy(srcfile, targetfile)
                    test_nginx_config()
                    reload_nginx_config()
                except Exception as e:
                    try:
                        print('Restoring Nginx configuration to previous state...')
                        shutil.copy(backupfile, targetfile)
                        test_nginx_config()
                        reload_nginx_config()
                        print('Nginx previous configuration restored and loaded')
                    except Exception as e:
                        print_error('Failed to restore Nginx config:', e)
                        print_error('Nginx config left corrupted!')
                    raise
        elif service in ('djangosite',):
            settings['WORKING_DIR'] = os.path.join(settings['HOME'], 'djangosite')
            ensure_dir_exists(settings['LOGGING_DIR'])
            if config in ('gunicorn-dev',):
                settings['GUNICORN_CMD'] = os.path.join(os.path.dirname(settings['PYTHON_CMD']), 'gunicorn')
                settings['GUNICORN_CONFIG_PATH'] = os.path.join(settings['HOME'], 'services', 'gunicorn_config.py')
                service_template_path = os.path.join('services', 'templates', 'systemd.gunicorn.service')
                # socket_template_path = os.path.join('services', 'templates', 'systemd.gunicorn.socket')
                service_def = render_template(service_template_path, settings)
                # socket_def = render_template(socket_template_path, settings)
                targetroot = settings['targetroot']
                __, error = copy_files(os.path.join(HERE, 'djangosite', 'project_static'), targetroot)
                if error is not None:
                    print_error(error)
                    sys.exit(1)
                systemd_name = derive_systemd_name(service, config)
                __, error = systemd_install(systemd_name, 'service', service_def)
                # __, error = systemd_install(systemd_name, 'socket', socket_def)
                if error is not None:
                    print_error(error)
                    sys.exit(1)
            elif config in ('django-dev',):
                service_template_path = os.path.join('services', 'templates', 'systemd.django.service')
                service_def = render_template(service_template_path, settings)
                targetroot = settings['targetroot']
                __, error = copy_files(os.path.join(HERE, 'djangosite', 'project_static'), targetroot)
                if error is not None:
                    print_error(error)
                    sys.exit(1)
                systemd_name = derive_systemd_name(service, config)
                __, error = systemd_install(systemd_name, 'service', service_def)
                if error is not None:
                    print_error(error)
                    sys.exit(1)
        elif service in ('flasksite',):
            settings['WORKING_DIR'] = os.path.join(settings['HOME'])
            ensure_dir_exists(settings['LOGGING_DIR'])
            if config in ('gunicorn-dev',):
                settings['GUNICORN_CMD'] = os.path.join(os.path.dirname(settings['PYTHON_CMD']), 'gunicorn')
                settings['GUNICORN_CONFIG_PATH'] = os.path.join(settings['HOME'], 'services', 'gunicorn_config.py')
                service_template_path = os.path.join('services', 'templates', 'systemd.gunicorn.service')
                # socket_template_path = os.path.join('services', 'templates', 'systemd.gunicorn.socket')
                service_def = render_template(service_template_path, settings)
                # socket_def = render_template(socket_template_path, settings)
                # targetroot = settings['targetroot']
                # __, error = copy_files(os.path.join(HERE, 'djangosite', 'project_static'), targetroot)
                # if error is not None:
                #     print_error(error)
                #     sys.exit(1)
                systemd_name = derive_systemd_name(service, config)
                __, error = systemd_install(systemd_name, 'service', service_def)
                # __, error = systemd_install(systemd_name, 'socket', socket_def)
                if error is not None:
                    print_error(error)
                    sys.exit(1)
            elif config in ('uwsgi-dev',):
                settings['UWSGI_CMD'] = os.path.join(os.path.dirname(settings['PYTHON_CMD']), 'uwsgi')
                settings['UWSGI_CONFIG_PATH'] = os.path.join(settings['HOME'], 'test.ini')
                service_template_path = os.path.join('services', 'templates', 'systemd.uwsgi.service')
                # socket_template_path = os.path.join('services', 'templates', 'systemd.gunicorn.socket')
                service_def = render_template(service_template_path, settings)
                # socket_def = render_template(socket_template_path, settings)
                # targetroot = settings['targetroot']
                # __, error = copy_files(os.path.join(HERE, 'djangosite', 'project_static'), targetroot)
                # if error is not None:
                #     print_error(error)
                #     sys.exit(1)
                systemd_name = derive_systemd_name(service, config)
                __, error = systemd_install(systemd_name, 'service', service_def)
                # __, error = systemd_install(systemd_name, 'socket', socket_def)
                if error is not None:
                    print_error(error)
                    sys.exit(1)
            elif config in ('flask-dev',):
                service_template_path = os.path.join('services', 'templates', 'systemd.flask.service')
                service_def = render_template(service_template_path, settings)
                # targetroot = settings['targetroot']
                # __, error = copy_files(os.path.join(HERE, 'djangosite', 'project_static'), targetroot)
                # if error is not None:
                #     print_error(error)
                #     sys.exit(1)
                systemd_name = derive_systemd_name(service, config)
                __, error = systemd_install(systemd_name, 'service', service_def)
                if error is not None:
                    print_error(error)
                    sys.exit(1)
        elif service in ('taskplanner', 'taskworker'):
            settings['CELERY_CMD'] = os.path.join(os.path.dirname(settings['PYTHON_CMD']), 'celery')
            service_template_path = os.path.join('services', 'templates', 'systemd.celery.service')
            service_def = render_template(service_template_path, settings)
            systemd_name = derive_systemd_name(service, config)
            __, error = systemd_install(systemd_name, service_def)
            if error is not None:
                print_error(error)
                sys.exit(1)
        else:
            raise Exception('Unsupported service: {}'.format(service))
    except Exception as e:
        print_error('Failed to install service configuration:', e)
        sys.exit(1)
    print('Service [{}] configuration [{}] installed'.format(service, config))


@cli.command()
@click.argument('service')
@click.argument('config')
def uninstall(service, config):
    """Uninstall service configuration"""
    print('Removing service [{}] for config [{}]...'.format(service, config))
    settings, error = load_settings(service, config)
    if error is not None:
        print_error(error)
        sys.exit(1)
    try:
        if service == 'nginxsite':
            uninstall_nginx_files(config, settings)
            test_nginx_config()
            reload_nginx_config()
        elif service == 'nginxmain':
            print('Fake uninstall of nginxmain')
        elif service in ('flasksite', 'djangosite', 'taskplanner', 'taskworker'):
            systemd_name = derive_systemd_name(service, config)
            __, error = systemd_uninstall(systemd_name, 'service')
            __, error = systemd_uninstall(systemd_name, 'socket')
            if error is not None:
                print_error(error)
                sys.exit(1)
        else:
            raise Exception('Unsupported service: {}'.format(service))
    except Exception as e:
        print_error('Failed to uninstall service configuration:', e)
        sys.exit(1)
    print('Service [{}] configuration [{}] uninstalled'.format(service, config))


@cli.command()
@click.argument('service')
@click.argument('config')
def start(service, config):
    """Start systemd service"""
    print('Starting service [{}] for config [{}]...'.format(service, config))
    if service in ('flasksite', 'djangosite', 'taskplanner', 'taskworker'):
        systemd_name = derive_systemd_name(service, config)
        __, error = systemd_start(systemd_name)
        if error is not None:
            print_error(error)
            sys.exit(1)
        print('Service started:', systemd_name)


@cli.command()
@click.argument('service')
@click.argument('config')
def stop(service, config):
    """Stop systemd service"""
    print('Stopping service [{}] for config [{}]...'.format(service, config))
    if service in ('flasksite', 'djangosite', 'taskplanner', 'taskworker'):
        systemd_name = derive_systemd_name(service, config)
        __, error = systemd_stop(systemd_name)
        if error is not None:
            print_error(error)
            sys.exit(1)
        print('Service stopped:', systemd_name)


if __name__ == '__main__':
    cli()
