"""Patch the HuggingFace Space so the first homepage request cannot stall Gunicorn."""

from __future__ import annotations

import os
from pathlib import Path

from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download


def _require(needle: str, haystack: str, label: str) -> None:
    if needle not in haystack:
        raise SystemExit(f"{label} patch target not found")


def patch_run_py(source: str) -> str:
    old = (
        "        if result:\n"
        "            from flask_migrate import upgrade as _upgrade\n"
        "\n"
        "            _upgrade()\n"
        "            logger.info(f'数据库迁移已是最新版本: {result[0]}')\n"
        "            return True"
    )
    new = (
        "        if result:\n"
        "            logger.info(f'数据库已有迁移版本 {result[0]}，跳过 upgrade 以免阻塞请求')\n"
        "            return True"
    )
    _require(old, source, "run.py")
    return source.replace(old, new, 1)


def patch_book_service(source: str) -> str:
    if "import os\n" not in source.split("from ", 1)[0]:
        source = source.replace("import logging\n", "import logging\nimport os\n", 1)

    flag_old = "        cache_key = f'books_{category_id}'\n"
    flag_new = (
        "        if os.environ.get('SPACE_ID'):\n"
        "            auto_translate = False\n"
        "            notify_refresh = False\n"
        "\n"
        "        cache_key = f'books_{category_id}'\n"
    )
    _require(flag_old, source, "book_service.py cache_key")
    if "if os.environ.get('SPACE_ID'):" not in source:
        source = source.replace(flag_old, flag_new, 1)

    supp_old = (
        "        isbns = [b.get('primary_isbn13') or b.get('primary_isbn10', '') for b in raw_books]\n"
        "        translations = self._batch_get_translations(isbns)\n"
        "        supplements = self._batch_get_supplements(isbns)\n"
    )
    supp_new = (
        "        isbns = [b.get('primary_isbn13') or b.get('primary_isbn10', '') for b in raw_books]\n"
        "        if os.environ.get('SPACE_ID'):\n"
        "            translations, supplements = {}, {}\n"
        "        else:\n"
        "            translations = self._batch_get_translations(isbns)\n"
        "            supplements = self._batch_get_supplements(isbns)\n"
    )
    _require(supp_old, source, "book_service.py supplements")
    return source.replace(supp_old, supp_new, 1)


def main() -> None:
    token = os.environ["HF_TOKEN"]
    repo = os.environ["HF_SPACE_REPO"]
    api = HfApi(token=token)

    run_src = Path(
        hf_hub_download(repo_id=repo, repo_type="space", filename="run.py", token=token)
    ).read_text(encoding="utf-8")
    book_src = Path(
        hf_hub_download(
            repo_id=repo,
            repo_type="space",
            filename="app/services/book_service.py",
            token=token,
        )
    ).read_text(encoding="utf-8")

    Path("run.py").write_text(patch_run_py(run_src), encoding="utf-8")
    Path("book_service.py").write_text(patch_book_service(book_src), encoding="utf-8")

    api.create_commit(
        repo_id=repo,
        repo_type="space",
        operations=[
            CommitOperationAdd(path_in_repo="run.py", path_or_fileobj=Path("run.py").read_bytes()),
            CommitOperationAdd(
                path_in_repo="app/services/book_service.py",
                path_or_fileobj=Path("book_service.py").read_bytes(),
            ),
        ],
        commit_message="fix: do not block the only Gunicorn worker on first page load",
    )
    print("Uploaded startup patches to the Space.")


if __name__ == "__main__":
    main()
