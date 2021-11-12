
# Ribosome examples

This repo contains examples of [Ribosome](https://github.com/alexandervpetrov/ribosome)
release process interface implementation for Nginx and Django.

## Prerequisites

    sudo apt install libpcre3 libpcre3-dev

Install [pyenv](https://github.com/pyenv/pyenv):
packages needed to build Python by [this guide](https://askubuntu.com/a/865644)
and then use [pyenv-installer](https://github.com/pyenv/pyenv-installer#installation--update--uninstallation).

Ensure that pyenv shims come first at PATH.
Place these lines

    export PATH="~/.pyenv/bin:$PATH"
    eval "$(pyenv init -)"
    eval "$(pyenv virtualenv-init -)"

as last ones in `.bashrc` for interactive sessions **and**
also in `.bash_profile` for non-interactive sessions.

Install Python: `pyenv install 3.8.0`.

For current project directory Python already configured via file `.python-version`,
if you want configure it for more convenient usage in console
you can run command `pyenv local 3.8.0` from you home directory for example.

Install [Pipenv](https://github.com/pypa/pipenv) and install/upgrade other basic libs
into Python distribution: `pip install --upgrade setuptools pip pipenv wheel twine awscli`.

## Getting started

Setup runtime and build environment:

    make devsetup

Setup Django:

    pipenv run ./manage.py migrate

Start main Django application:

    make run

and open [http://127.0.0.1:8000](http://127.0.0.1:8000) to ensure that all is working.

E.g. install configuration `dev` from service `webapp`:

    sudo $(pipenv --py) ./service.py install webapp dev

E.g. install configuration `dev` from service `nginxmain`:

    sudo $(pipenv --py) ./service.py install nginxmain dev

E.g. install configuration `dev` from service `nginxsite`:

    sudo $(pipenv --py) ./service.py install nginxsite dev


## Releasing, deploying, running

Set the S3 bucket name in `codons.yaml` to the one you own, also convenient to setup `aws_profile` name.
Ensure you
[configured](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/quickstart.html#configuration)
S3 access or configured
[shared credentials file](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html#shared-credentials-file).
Setup SSH daemon at localhost to test, or setup SSH access to any other host.
Configure host address in `/etc/hosts` to `example.com`.

Commit changes to your local copy of repo and tag it with a new tag.

Run from environment where Ribsome installed:

    ribosome release

    ribosome deploy <tag> localhost

    ribosome load <tag> nginxmain dev localhost
    ribosome load <tag> nginxsite dev localhost
    ribosome load <tag> webapp dev localhost
