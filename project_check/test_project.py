"""Тести частини Б: розгортання проєкту й паралельний прогін конкурентної операції. Запуск: pytest project_check (з кореня стартового проєкту)."""
import os
from pathlib import Path

import pytest

import check_project

PROJECT = Path(os.environ.get("PROJECT_DIR", Path(__file__).resolve().parent.parent / "project"))


@pytest.fixture(scope="module")
def deployed():
    return check_project.deploy_and_check(PROJECT)


def test_project_deploys_and_operation_keeps_invariant(deployed):
    problems = deployed[1]
    assert not problems, "\n" + "\n".join(problems)


def test_git_history():
    problems = check_project.check_git(PROJECT)
    assert not problems, "\n" + "\n".join(problems)
