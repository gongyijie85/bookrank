"""Check the release snapshot without importing the app or contacting any service."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Keep these seven business files aligned with publisher_data.STATIC_DATA_FILES.
# Importing that application module would load Flask and runtime configuration.
SOURCE_FILES = {
    'google_books': 'google_books_books.json',
    'open_library': 'open_library_books.json',
    'penguin_random_house': 'penguin_random_house_books.json',
    'simon_schuster': 'simon_schuster_books.json',
    'hachette': 'hachette_books.json',
    'harpercollins': 'harpercollins_books.json',
    'macmillan': 'macmillan_books.json',
}


class SnapshotValidationError(ValueError):
    """A file or field is unsafe to use as the release snapshot."""


def _reject_constant(_value):
    raise ValueError('Nonstandard JSON constant')


def _read(directory: Path, filename: str):
    try:
        return json.loads((directory / filename).read_text(encoding='utf-8'), parse_constant=_reject_constant)
    except (OSError, UnicodeError, ValueError):
        # Exception details can contain document fragments or sensitive paths.
        raise SnapshotValidationError(f'{filename}: missing or invalid JSON') from None


def _check_time(value, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SnapshotValidationError(f'{field}: expected an ISO datetime')
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise SnapshotValidationError(f'{field}: expected an ISO datetime') from None
    # Legacy timestamps may be naive. Parsing does not assign a timezone or
    # establish that the data is fresh enough for a particular release.


def _check_books(rows, field: str) -> None:
    if not isinstance(rows, list):
        raise SnapshotValidationError(f'{field}: expected a list')
    for book in rows:
        if not isinstance(book, dict):
            raise SnapshotValidationError(f'{field}: expected book objects')
        for key in ('title', 'author'):
            if not isinstance(book.get(key), str) or not book[key].strip():
                raise SnapshotValidationError(f'{field}: {key} must be nonempty text')


def validate_snapshot(data_dir: Path) -> int:
    """Return the book count, or reject the snapshot without changing any file."""
    directory = Path(data_dir)
    combined = _read(directory, 'all_books.json')
    if not isinstance(combined, dict) or set(combined) != set(SOURCE_FILES):
        raise SnapshotValidationError('all_books.json: sources must match the seven declared sources')

    total = 0
    for slug, filename in SOURCE_FILES.items():
        rows = _read(directory, filename)
        _check_books(rows, filename)
        _check_books(combined[slug], f'all_books.json: {slug}')
        if json.dumps(combined[slug], sort_keys=True) != json.dumps(rows, sort_keys=True):
            raise SnapshotValidationError(f'all_books.json: {slug} differs from {filename}')
        total += len(rows)
    if total == 0:
        raise SnapshotValidationError('all_books.json: total_books must be greater than zero')

    metadata = _read(directory, 'update_time.json')
    if not isinstance(metadata, dict):
        raise SnapshotValidationError('update_time.json: expected an object')
    count = metadata.get('total_books')
    if type(count) is not int or count != total:
        raise SnapshotValidationError('update_time.json: total_books must be an integer matching the snapshot')
    publishers = metadata.get('publishers')
    if (
        not isinstance(publishers, list)
        or any(not isinstance(item, str) for item in publishers)
        or len(publishers) != len(SOURCE_FILES)
        or set(publishers) != set(SOURCE_FILES)
    ):
        raise SnapshotValidationError('update_time.json: publishers must uniquely match the declared sources')

    has_success = False
    for field in ('timestamp', 'last_complete_success_at', 'published_at'):
        value = metadata.get(field)
        if value is not None:
            _check_time(value, f'update_time.json: {field}')
            if field != 'published_at':
                has_success = True
    source_success = metadata.get('source_success_at', {})
    if not isinstance(source_success, dict) or set(source_success) - set(SOURCE_FILES):
        raise SnapshotValidationError('update_time.json: source_success_at must contain declared sources only')
    for slug, value in source_success.items():
        _check_time(value, f'update_time.json: source_success_at.{slug}')
        if combined[slug]:
            has_success = True
    if not has_success:
        raise SnapshotValidationError('update_time.json: missing a valid crawl success timestamp')

    attempt_file = directory / 'sync_attempt.json'
    if attempt_file.exists():
        attempt = _read(directory, attempt_file.name)
        if not isinstance(attempt, dict) or not isinstance(attempt.get('sources'), dict):
            raise SnapshotValidationError('sync_attempt.json: expected an object with a sources object')
        if 'attempted_at' in attempt:
            _check_time(attempt['attempted_at'], 'sync_attempt.json: attempted_at')
        # A failed or partial latest attempt can leave a valid previous snapshot.
        # Its attempt/publication state cannot establish crawl success.

    return total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('static/data'))
    args = parser.parse_args(argv)
    try:
        count = validate_snapshot(args.data_dir)
    except SnapshotValidationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f'Static snapshot valid: {count} books across {len(SOURCE_FILES)} sources')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
