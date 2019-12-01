
# Self-Documented Makefile approach, borrowed from: https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html

.DEFAULT_GOAL := help

help:
	@grep -E '^[a-zA-Z_.-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'


setup:  ## Make runtime environment
	@echo "Making runtime environment..."
	-@pipenv --rm
	@pipenv sync --bare
	-@pipenv check


devsetup:  ## Make runtime environment for development
	@echo "Making runtime environment for development..."
	-@pipenv --rm
	@pipenv sync --bare --dev
	-@pipenv check


updateversion:  ## Update version info
	@echo "Updating version info ..."
	@pipenv run ribosome version update


rund: clean updateversion  ## Run Django application
	@echo "Running Django application ..."
	@pipenv run ./djangosite/manage.py runserver


runf: clean updateversion  ## Run Flask application
	@echo "Running Flask application ..."
	@FLASK_APP=flasksite.site:app FLASK_DEBUG=1 pipenv run flask run --host=0.0.0.0


clean:  ## Remove bytecode, cache, build and run files
	@echo "Removing bytecode, cache, build and run files..."
	@rm -rf `find . -name __pycache__`
	@rm -f `find . -type f -name '*.py[co]' `
	@rm -rf .cache
	@rm -rf .pytest_cache
	@rm -rf dist
	@rm -rf build
	@rm -rf *.egg-info
	@rm -rf *.log


codestyle:  ## Check code style
	@echo "Checking code style..."
	@pipenv run pycodestyle djangosite --ignore=E501
	@pipenv run pycodestyle *.py --ignore=E501


collectstatic:  ## Collect static files
	@pipenv run ./djangosite/manage.py collectstatic --noinput


cleanstatic:  ## Remove collected static files
	@echo "Removing collected static files..."
	@rm -rf djangosite/project_static


build: cleanstatic clean collectstatic  ## Build project
	@echo "Project built"


test:  ## Run tests
	@echo "Running tests..."
	@pipenv run pytest
