# View refactor

The original 4,000-line `main/views.py` has been retained as `main/views_legacy.py` for reference.

Active code is split under `main/view_modules/` by feature. `main/views.py` is now a compatibility facade, so `main/urls.py` and existing imports continue to work.

Run `python manage.py check` after installing the project dependencies.
